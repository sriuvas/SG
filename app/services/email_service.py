import os
import smtplib
import ssl
from email.message import EmailMessage
from dotenv import load_dotenv

load_dotenv()

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL") or SMTP_USERNAME


def send_otp_email(recipient_email: str, otp: str, purpose: str = "registration") -> None:
    """Send an OTP email using Gmail SMTP."""
    if not SMTP_USERNAME or not SMTP_PASSWORD or not SMTP_FROM_EMAIL:
        raise RuntimeError(
            "SMTP_USERNAME, SMTP_PASSWORD and SMTP_FROM_EMAIL must be configured."
        )

    if purpose == "password_reset":
        subject = "SN PEETAM - Password Reset OTP"
        message_text = (
            f"Your password reset OTP is {otp}.\n\n"
            "This OTP expires in 60 seconds.\n"
            "If you did not request a password reset, ignore this email.\n"
            "Do not share this code with anyone."
        )
    else:
        subject = "SN PEETAM - Email Verification OTP"
        message_text = (
            f"Your email verification OTP is {otp}.\n\n"
            "This OTP expires in 60 seconds.\n"
            "Do not share this code with anyone."
        )

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = SMTP_FROM_EMAIL
    message["To"] = recipient_email
    message.set_content(message_text)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
        server.ehlo()
        server.starttls(context=ssl.create_default_context())
        server.ehlo()
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.send_message(message)
