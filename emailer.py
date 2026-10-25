"""Email: compose the complaint, build the message and send it through Gmail SMTP."""
import os
import smtplib
from email.message import EmailMessage
from email.utils import formatdate

PLACEHOLDER_GMAIL = {"", "you@gmail.com"}
PLACEHOLDER_PASSWORD = {"", "xxxx xxxx xxxx xxxx"}


class EmailError(Exception):
    """A send failure whose message can be shown to the user as-is."""


def gmail_configured() -> bool:
    return (
        os.getenv("GMAIL_ADDRESS", "").strip() not in PLACEHOLDER_GMAIL
        and os.getenv("GMAIL_APP_PASSWORD", "").strip() not in PLACEHOLDER_PASSWORD
    )


def compose_body(
    letter: str, location_block: str, translation: str, language: str, photo_name: str, ref_id: str
) -> str:
    """Full email text: letter, fixed location block, optional translation, attachment and reference."""
    parts = [letter.strip(), location_block]
    if translation:
        parts.append(f"──────── {language} version ────────\n{translation.strip()}")
    parts.append(f"Photo attached: {photo_name}\nReference: {ref_id}")
    return "\n\n".join(parts) + "\n"


def build_email(
    to: str, cc: str | None, subject: str, body: str, photo_bytes: bytes, photo_name: str
) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = os.getenv("GMAIL_ADDRESS", "").strip()
    msg["To"] = to
    if cc:
        msg["Cc"] = cc
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg.set_content(body)
    msg.add_attachment(photo_bytes, maintype="image", subtype="jpeg", filename=photo_name)
    return msg


def send_email(msg: EmailMessage) -> None:
    """Send via Gmail SMTP (SSL, port 465). Raises EmailError on failure."""
    address = os.getenv("GMAIL_ADDRESS", "").strip()
    password = os.getenv("GMAIL_APP_PASSWORD", "").replace(" ", "")
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as smtp:
            smtp.login(address, password)
            smtp.send_message(msg)
    except smtplib.SMTPAuthenticationError as e:
        raise EmailError("Gmail login failed. Check GMAIL_APP_PASSWORD (2-Step Verification must be on).") from e
    except (smtplib.SMTPException, OSError) as e:
        raise EmailError(f"Could not send the email: {e}") from e
