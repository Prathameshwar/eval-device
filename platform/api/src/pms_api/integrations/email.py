import asyncio
import smtplib
from email.message import EmailMessage
from urllib.parse import urlencode


async def send_invitation(settings, email: str, token: str) -> bool:
    if not settings.smtp_host or not settings.smtp_sender:
        return False
    message = EmailMessage()
    message["From"] = settings.smtp_sender
    message["To"] = email
    message["Subject"] = "Device Platform invitation"
    message.set_content(
        "Accept your invitation: " + settings.invitation_base_url + "#" + urlencode({"token": token})
    )

    def send():
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            if settings.smtp_starttls:
                import ssl

                smtp.starttls(context=ssl.create_default_context())
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password.get_secret_value())
            smtp.send_message(message)

    try:
        await asyncio.to_thread(send)
        return True
    except (OSError, smtplib.SMTPException):
        return False


async def send_account_action(settings, email: str, purpose: str, token: str) -> bool:
    if not settings.smtp_host or not settings.smtp_sender:
        return False
    labels = {
        "setup": "Set up your Device Platform account",
        "password_reset": "Reset your Device Platform password",
        "email_verify": "Verify your Device Platform email",
        "email_change": "Confirm your Device Platform email change",
    }
    if purpose not in labels:
        return False
    message = EmailMessage()
    message["From"] = settings.smtp_sender
    message["To"] = email
    message["Subject"] = labels[purpose]
    message.set_content(
        labels[purpose]
        + ": "
        + settings.account_action_base_url.rstrip("/")
        + "/"
        + purpose.replace("_", "-")
        + "#"
        + urlencode({"token": token})
    )

    def send():
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            if settings.smtp_starttls:
                import ssl

                smtp.starttls(context=ssl.create_default_context())
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password.get_secret_value())
            smtp.send_message(message)

    try:
        await asyncio.to_thread(send)
        return True
    except (OSError, smtplib.SMTPException):
        return False
