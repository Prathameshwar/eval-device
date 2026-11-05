"""Durable encrypted bulk invitation emails; uncertain sends require manual resend."""

import asyncio
import json
import logging
import os
from datetime import timedelta
from uuid import uuid4

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import delete, select, update

from pms_api.core.common import canonical, now
from pms_api.database.models import Department, InvitationEmailOutbox, MemberImport, Membership, Organization
from pms_api.integrations.email import send_invitation
from pms_api.integrations.vault import CredentialVault

logger = logging.getLogger("pms_api.invitation_delivery")


def queue_invitation(session, settings, membership, token):
    row_id = uuid4()
    nonce = os.urandom(12)
    encrypted = AESGCM(CredentialVault(settings).key(settings.active_credential_key)).encrypt(
        nonce,
        canonical({"token": token}).encode(),
        f"pms:invitation-email:v1:{membership.id}:{row_id}".encode(),
    )
    row = InvitationEmailOutbox(
        id=row_id,
        membership_id=membership.id,
        token_hash=membership.invitation_token_hash,
        encrypted_payload=nonce + encrypted,
        key_id=settings.active_credential_key,
        created_at=now(),
        expires_at=membership.invitation_expires_at,
    )
    session.add(row)


async def deliver_once(sessions, settings):
    timestamp = now()
    async with sessions() as session:
        # Never automatically retry a submission whose outcome could be unknown.
        await session.execute(
            update(InvitationEmailOutbox)
            .where(
                InvitationEmailOutbox.status == "sending",
                InvitationEmailOutbox.lease_expires_at <= timestamp,
            )
            .values(status="unknown", lease_token=None, lease_expires_at=None)
        )
        await session.execute(delete(MemberImport).where(MemberImport.expires_at <= timestamp))
        await session.execute(
            delete(InvitationEmailOutbox).where(InvitationEmailOutbox.expires_at <= timestamp)
        )
        await session.commit()
    if not settings.smtp_host or not settings.smtp_sender:
        return 0
    # Claim one at a time: queued messages never spend their lease waiting on other SMTP calls.
    delivered_count = 0
    for _ in range(10):
        async with sessions() as session:
            row = await session.scalar(
                select(InvitationEmailOutbox)
                .where(
                    InvitationEmailOutbox.status == "pending",
                    InvitationEmailOutbox.expires_at > now(),
                )
                .order_by(InvitationEmailOutbox.created_at, InvitationEmailOutbox.id)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if not row:
                break
            member = await session.get(Membership, row.membership_id, populate_existing=True)
            org = await session.get(Organization, member.organization_id) if member else None
            department = (
                await session.get(Department, member.department_id)
                if member and member.department_id
                else None
            )
            if (
                (department is not None and (not department.is_active or department.archived_at is not None))
                or not member
                or not org
                or not org.is_active
                or org.archived_at is not None
                or member.archived_at is not None
                or member.invitation_status != "pending"
                or member.invitation_token_hash != row.token_hash
                or member.invitation_expires_at <= now()
            ):
                row.status = "cancelled"
                await session.commit()
                continue
            try:
                raw = AESGCM(CredentialVault(settings).key(row.key_id)).decrypt(
                    row.encrypted_payload[:12],
                    row.encrypted_payload[12:],
                    f"pms:invitation-email:v1:{row.membership_id}:{row.id}".encode(),
                )
                token = json.loads(raw)["token"]
            except (InvalidTag, ValueError, KeyError):
                # One damaged payload must not block unrelated pending invitations.
                row.status = "failed"
                await session.commit()
                continue
            row_id, recipient, lease = row.id, member.invited_email, uuid4()
            row.status = "sending"
            row.lease_token = lease
            row.lease_expires_at = now() + timedelta(seconds=120)
            await session.commit()
        try:
            sent = await send_invitation(settings, recipient, token)
        except Exception:
            sent = False
        async with sessions() as session:
            row = await session.get(InvitationEmailOutbox, row_id, with_for_update=True)
            if row and row.status == "sending" and row.lease_token == lease:
                row.status = "sent" if sent else "failed"
                row.lease_token = None
                row.lease_expires_at = None
                await session.commit()
        delivered_count += 1
    return delivered_count


async def delivery_loop(sessions, settings):
    while True:
        try:
            await deliver_once(sessions, settings)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.warning("Invitation delivery cycle failed (%s)", type(error).__name__)
        await asyncio.sleep(5)
