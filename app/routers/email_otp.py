
import hashlib
import hmac
import os
import secrets
import time
import uuid
from datetime import datetime, timezone

from botocore.exceptions import ClientError
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr, Field
from passlib.context import CryptContext

from database import dynamodb
from app.services.email_service import send_otp_email


router = APIRouter(
    prefix="/api/auth",
    tags=["Email OTP"]
)

# DynamoDB tables
OTP_TABLE_NAME = "EmailOTP_Table"
USERS_TABLE_NAME = "Users_Table"

otp_table = dynamodb.Table(OTP_TABLE_NAME)
users_table = dynamodb.Table(USERS_TABLE_NAME)

# Password hashing: retain the existing bcrypt approach
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
)

# OTP configuration
OTP_VALIDITY_SECONDS = 60
OTP_MAX_ATTEMPTS = 5
OTP_RESEND_COOLDOWN_SECONDS = 30
VERIFIED_REGISTRATION_WINDOW_SECONDS = 600

OTP_HASH_SECRET = os.getenv("JWT_SECRET_KEY")

if not OTP_HASH_SECRET:
    raise RuntimeError(
        "JWT_SECRET_KEY must be configured before starting the API"
    )


# ==================================================
# Request models
# ==================================================

class SendOTPRequest(BaseModel):
    email: EmailStr


class VerifyOTPRequest(BaseModel):
    email: EmailStr
    otp: str = Field(pattern=r"^\d{6}$")


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    otp: str = Field(pattern=r"^\d{6}$")
    new_password: str = Field(min_length=8, max_length=128)


# ==================================================
# Helper functions
# ==================================================

def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_otp(email_key: str, otp: str) -> str:
    message = f"{email_key.lower()}:{otp}".encode("utf-8")

    return hmac.new(
        OTP_HASH_SECRET.encode("utf-8"),
        message,
        hashlib.sha256
    ).hexdigest()


def get_user_by_email(email: str):
    """Find a user using the existing Users_Table structure."""
    response = users_table.scan(
        FilterExpression="#email = :email",
        ExpressionAttributeNames={
            "#email": "email"
        },
        ExpressionAttributeValues={
            ":email": email
        }
    )

    matches = response.get("Items", [])

    while response.get("LastEvaluatedKey"):
        response = users_table.scan(
            ExclusiveStartKey=response["LastEvaluatedKey"],
            FilterExpression="#email = :email",
            ExpressionAttributeNames={
                "#email": "email"
            },
            ExpressionAttributeValues={
                ":email": email
            }
        )
        matches.extend(response.get("Items", []))

    if matches:
        return matches[0]

    # Support records whose email casing differs.
    response = users_table.scan()
    items = response.get("Items", [])

    while response.get("LastEvaluatedKey"):
        response = users_table.scan(
            ExclusiveStartKey=response["LastEvaluatedKey"]
        )
        items.extend(response.get("Items", []))

    for user in items:
        if normalize_email(str(user.get("email", ""))) == email:
            return user

    return None


def check_resend_cooldown(email_key: str, now: int) -> None:
    existing = otp_table.get_item(
        Key={"email": email_key},
        ConsistentRead=True
    ).get("Item")

    if existing:
        last_sent = int(existing.get("last_sent_at", 0))

        if now - last_sent < OTP_RESEND_COOLDOWN_SECONDS:
            raise HTTPException(
                status_code=429,
                detail="Please wait before requesting another OTP"
            )


def create_and_send_otp(
    email_key: str,
    recipient_email: str,
    purpose: str
) -> None:
    now = int(time.time())

    check_resend_cooldown(email_key, now)

    otp = f"{secrets.randbelow(1_000_000):06d}"

    item = {
        "email": email_key,
        "otp_hash": hash_otp(email_key, otp),
        "expires_at": now + OTP_VALIDITY_SECONDS,
        "last_sent_at": now,
        "attempts": 0,
        "verified": False,
        "verified_until": 0,
        "purpose": purpose
    }

    otp_table.put_item(Item=item)

    try:
        send_otp_email(
            recipient_email=recipient_email,
            otp=otp,
            purpose=purpose
        )
    except Exception:
        # Do not leave a usable OTP when delivery fails.
        otp_table.delete_item(
            Key={"email": email_key}
        )
        raise HTTPException(
            status_code=502,
            detail="Unable to send OTP email. Check SMTP configuration."
        )


def validate_reset_otp(email_key: str, otp: str):
    now = int(time.time())

    response = otp_table.get_item(
        Key={"email": email_key},
        ConsistentRead=True
    )
    item = response.get("Item")

    if not item or item.get("purpose") != "password_reset":
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired OTP. Request a new OTP."
        )

    if now >= int(item.get("expires_at", 0)):
        otp_table.delete_item(Key={"email": email_key})
        raise HTTPException(
            status_code=400,
            detail="OTP expired. Request a new OTP."
        )

    attempts = int(item.get("attempts", 0))

    if attempts >= OTP_MAX_ATTEMPTS:
        otp_table.delete_item(Key={"email": email_key})
        raise HTTPException(
            status_code=429,
            detail="Too many attempts. Request a new OTP."
        )

    supplied_hash = hash_otp(email_key, otp)
    stored_hash = item.get("otp_hash", "")

    if not hmac.compare_digest(supplied_hash, stored_hash):
        new_attempts = attempts + 1

        if new_attempts >= OTP_MAX_ATTEMPTS:
            otp_table.delete_item(Key={"email": email_key})
            raise HTTPException(
                status_code=429,
                detail="Too many attempts. Request a new OTP."
            )

        otp_table.update_item(
            Key={"email": email_key},
            UpdateExpression="SET attempts = :attempts",
            ExpressionAttributeValues={
                ":attempts": new_attempts
            }
        )

        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid OTP. Attempts remaining: "
                f"{OTP_MAX_ATTEMPTS - new_attempts}"
            )
        )

    return item


# ==================================================
# Registration: Send OTP
# POST /api/auth/send-otp
# ==================================================

@router.post("/send-otp")
def send_otp(request: SendOTPRequest):
    email = normalize_email(str(request.email))
    now = int(time.time())

    try:
        create_and_send_otp(
            email_key=email,
            recipient_email=email,
            purpose="registration"
        )

        return {
            "message": "OTP sent successfully",
            "email": email,
            "expires_in_seconds": OTP_VALIDITY_SECONDS
        }

    except HTTPException:
        raise
    except ClientError:
        raise HTTPException(
            status_code=500,
            detail="Unable to access the OTP table"
        )


# ==================================================
# Registration: Verify OTP
# POST /api/auth/verify-otp
# ==================================================

@router.post("/verify-otp")
def verify_otp(request: VerifyOTPRequest):
    email = normalize_email(str(request.email))
    now = int(time.time())

    try:
        response = otp_table.get_item(
            Key={"email": email},
            ConsistentRead=True
        )
        item = response.get("Item")

        if not item or item.get("purpose") != "registration":
            raise HTTPException(
                status_code=400,
                detail="OTP not found. Request a new OTP."
            )

        if item.get("verified") is True:
            if int(item.get("verified_until", 0)) > now:
                return {
                    "message": "Email already verified",
                    "email": email
                }

            raise HTTPException(
                status_code=400,
                detail="Verification expired. Request a new OTP."
            )

        if now >= int(item.get("expires_at", 0)):
            otp_table.delete_item(Key={"email": email})
            raise HTTPException(
                status_code=400,
                detail="OTP expired. Request a new OTP."
            )

        attempts = int(item.get("attempts", 0))

        if attempts >= OTP_MAX_ATTEMPTS:
            otp_table.delete_item(Key={"email": email})
            raise HTTPException(
                status_code=429,
                detail="Too many attempts. Request a new OTP."
            )

        supplied_hash = hash_otp(email, request.otp)
        stored_hash = item.get("otp_hash", "")

        if not hmac.compare_digest(supplied_hash, stored_hash):
            new_attempts = attempts + 1

            if new_attempts >= OTP_MAX_ATTEMPTS:
                otp_table.delete_item(Key={"email": email})
                raise HTTPException(
                    status_code=429,
                    detail="Too many attempts. Request a new OTP."
                )

            otp_table.update_item(
                Key={"email": email},
                UpdateExpression="SET attempts = :attempts",
                ExpressionAttributeValues={
                    ":attempts": new_attempts
                }
            )

            raise HTTPException(
                status_code=400,
                detail=(
                    "Invalid OTP. Attempts remaining: "
                    f"{OTP_MAX_ATTEMPTS - new_attempts}"
                )
            )

        otp_table.update_item(
            Key={"email": email},
            UpdateExpression=(
                "SET verified = :verified, "
                "verified_until = :verified_until "
                "REMOVE otp_hash, expires_at, attempts"
            ),
            ExpressionAttributeValues={
                ":verified": True,
                ":verified_until": (
                    now + VERIFIED_REGISTRATION_WINDOW_SECONDS
                )
            }
        )

        return {
            "message": "Email verified successfully",
            "email": email,
            "registration_window_seconds": (
                VERIFIED_REGISTRATION_WINDOW_SECONDS
            )
        }

    except HTTPException:
        raise
    except ClientError:
        raise HTTPException(
            status_code=500,
            detail="Unable to verify OTP"
        )


# ==================================================
# Forgot Password: Send OTP
# POST /api/auth/forgot-password
# ==================================================

@router.post("/forgot-password")
def forgot_password(request: ForgotPasswordRequest):
    email = normalize_email(str(request.email))
    reset_key = f"reset#{email}"

    try:
        user = get_user_by_email(email)

        # Use the same response for registered and unregistered emails
        # to avoid revealing whether an account exists.
        if user:
            create_and_send_otp(
                email_key=reset_key,
                recipient_email=email,
                purpose="password_reset"
            )

        return {
            "message": (
                "If an account exists for this email, "
                "a password reset OTP has been sent."
            )
        }

    except HTTPException as exc:
        if exc.status_code == 429:
            raise
        raise
    except ClientError:
        raise HTTPException(
            status_code=500,
            detail="Unable to process password reset request"
        )


# ==================================================
# Reset Password: Verify OTP and update password
# POST /api/auth/reset-password
# ==================================================

@router.post("/reset-password")
def reset_password(request: ResetPasswordRequest):
    email = normalize_email(str(request.email))
    reset_key = f"reset#{email}"

    try:
        # Validate the OTP before changing the password.
        validate_reset_otp(reset_key, request.otp)

        user = get_user_by_email(email)

        if not user:
            raise HTTPException(
                status_code=400,
                detail="Unable to reset password"
            )

        user_id = user.get("user_id")

        if not user_id:
            raise HTTPException(
                status_code=500,
                detail="User record is missing its user_id"
            )

        new_password_hash = pwd_context.hash(
            request.new_password
        )

        now = datetime.now(timezone.utc).isoformat()

        # Update the existing user record using its primary key.
        users_table.update_item(
            Key={"user_id": user_id},
            UpdateExpression=(
                "SET password_hash = :password_hash, "
                "updated_at = :updated_at"
            ),
            ExpressionAttributeValues={
                ":password_hash": new_password_hash,
                ":updated_at": now
            }
        )

        # Consume the reset OTP after the password update succeeds.
        otp_table.delete_item(
            Key={"email": reset_key}
        )

        return {
            "message": "Password reset successfully"
        }

    except HTTPException:
        raise
    except ClientError:
        raise HTTPException(
            status_code=500,
            detail="Unable to reset password"
        )
