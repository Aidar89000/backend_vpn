import asyncio
import logging
import smtplib
from email.message import EmailMessage

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


class EmailDeliveryError(Exception):
    pass


def _send_email_sync(recipient: str, subject: str, body_text: str, body_html: str | None = None):
    if not settings.EMAIL_DELIVERY_ENABLED:
        raise EmailDeliveryError('SMTP is not configured')

    message = EmailMessage()
    message['Subject'] = subject
    message['From'] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
    message['To'] = recipient
    message.set_content(body_text)
    if body_html:
        message.add_alternative(body_html, subtype='html')

    if settings.SMTP_USE_SSL:
        server = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20)
    else:
        server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20)

    try:
        server.ehlo()
        if settings.SMTP_USE_TLS and not settings.SMTP_USE_SSL:
            server.starttls()
            server.ehlo()
        if settings.SMTP_USERNAME:
            server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        server.send_message(message)
    except Exception as exc:
        raise EmailDeliveryError(str(exc)) from exc
    finally:
        try:
            server.quit()
        except Exception:
            pass


async def send_login_code_email(recipient: str, code: str):
    expires = settings.LOGIN_CODE_EXPIRE_MINUTES
    if settings.DEBUG and settings.EMAIL_DEV_LOG_ONLY:
        logger.warning(
            'DEV EMAIL MODE: login code for %s is %s (expires in %s min)',
            recipient,
            code,
            expires,
        )
        return

    subject = f'Login code for {settings.APP_NAME}'
    body_text = (
        f'Your login code: {code}\n\n'
        f'The code expires in {expires} minutes.\n'
        'If this was not you, ignore this email.'
    )
    body_html = (
        f'<h2>Login code</h2>'
        f'<p>Your login code for <b>{settings.APP_NAME}</b>:</p>'
        f"<p style='font-size:28px;font-weight:700;letter-spacing:6px'>{code}</p>"
        f'<p>The code expires in {expires} minutes.</p>'
        '<p>If this was not you, ignore this email.</p>'
    )
    await asyncio.to_thread(_send_email_sync, recipient, subject, body_text, body_html)
