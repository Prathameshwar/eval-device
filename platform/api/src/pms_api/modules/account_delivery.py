import asyncio
import logging
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import delete, or_, select

from pms_api.core.common import now
from pms_api.database.models import (
    AccountActionToken,
    AccountEmailOutbox,
    AuthRateLimit,
    LocalSession,
)
from pms_api.integrations.email import send_account_action
from pms_api.security.local_auth import decrypt_outbox_payload

logger = logging.getLogger("pms_api.account_delivery")


async def deliver_once(sessions, settings) -> int:
    timestamp = now()
    claims: list[tuple] = []
    async with sessions() as session:
        rows = list(
            (
                await session.scalars(
                    select(AccountEmailOutbox)
                    .where(
                        AccountEmailOutbox.expires_at > timestamp,
                        AccountEmailOutbox.attempt_count < 10,
                        AccountEmailOutbox.available_at <= timestamp,
                        or_(
                            AccountEmailOutbox.status.in_(["pending", "failed"]),
                            (AccountEmailOutbox.status == "sending")
                            & (AccountEmailOutbox.lease_expires_at <= timestamp),
                        ),
                    )
                    .order_by(AccountEmailOutbox.available_at, AccountEmailOutbox.id)
                    .with_for_update(skip_locked=True)
                    .limit(10)
                )
            ).all()
        )
        for row in rows:
            lease = uuid4()
            row.status = "sending"
            row.lease_token = lease
            row.lease_expires_at = timestamp + timedelta(seconds=30)
            claims.append((row.id, lease, row.recipient, row.purpose, decrypt_outbox_payload(row, settings)))
        await session.commit()
    for row_id, lease, recipient, purpose, payload in claims:
        delivered = await send_account_action(settings, recipient, purpose, payload["token"])
        async with sessions() as session:
            row = await session.get(AccountEmailOutbox, row_id, with_for_update=True)
            if not row or row.status != "sending" or row.lease_token != lease:
                continue
            row.attempt_count += 1
            row.lease_token = None
            row.lease_expires_at = None
            if delivered:
                row.status = "sent"
                row.sent_at = now()
            else:
                row.status = "failed"
                row.available_at = now() + timedelta(seconds=min(300, 2**row.attempt_count))
            await session.commit()
    return len(claims)


async def cleanup_expired(sessions) -> None:
    timestamp = now()
    async with sessions() as session:
        await session.execute(delete(LocalSession).where(LocalSession.expires_at <= timestamp))
        await session.execute(delete(AccountActionToken).where(AccountActionToken.expires_at <= timestamp))
        await session.execute(delete(AuthRateLimit).where(AuthRateLimit.expires_at <= timestamp))
        await session.execute(delete(AccountEmailOutbox).where(AccountEmailOutbox.expires_at <= timestamp))
        await session.commit()


async def delivery_loop(sessions, settings):
    iterations = 0
    while True:
        try:
            await deliver_once(sessions, settings)
            iterations += 1
            if iterations % 720 == 0:
                await cleanup_expired(sessions)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.warning("Account delivery cycle failed (%s)", type(error).__name__)
        await asyncio.sleep(5)
