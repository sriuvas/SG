
import hashlib
import hmac
import os
import secrets
import time

import boto3
from botocore.exceptions import ClientError
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr, Field

from database import dynamodb


router = APIRouter(
    prefix="/api/auth",
    tags=["Email OTP"]
)

# AWS configuration
AWS_REGION = os.getenv("AWS_REGION", "eu-north-1")
OTP_TABLE_NAME = "EmailOTP_Table"
SES_FROM_EMAIL = os.getenv(
    "SES_FROM_EMAIL",
    "srinivasboddu3614@gmail.com"
)

# OTP configuration
OTP_VALIDITY_SECONDS = 60
OTP_MAX_ATTEMPTS = 5
OTP_RESEND_COOLDOWN_SECONDS = 30
VERIFIED_REGISTRATION_WINDOW_SECONDS = 600

# Use the existing JWT secret to hash OTPs.
OTP_HASH_SECRET = os.getenv("JWT_SECRET_KEY")

if not OTP_HASH_SECRET:
    raise RuntimeError(
        "JWT_SECRET_KEY must be configured before starting the API"
    )

ses_client = boto3.client(
    "ses",
    region_name=AWS_REGION
)

otp_table = dynamodb.Table(OTP_TABLE_NAME)


class SendOTPRequest(BaseModel):
    email: EmailStr


class VerifyOTPRequest(BaseModel):
    email: EmailStr
    otp: str = Field(pattern=r"^\d{6}$")


def hash_otp(email: str, otp: str) -> str:
    message = f"{email.lower()}:{otp}".encode("utf-8")

    return hmac.new(
        OTP_HASH_SECRET.encode("utf-8"),
        message,
        hashlib.sha256
    ).hexdigest()


@router.post("/send-otp")
def send_otp(request: SendOTPRequest):
    email = str(request.email).strip().lower()
    now = int(time.time())

    try:
        existing = otp_table.get_item(
            Key={"email": email},
            ConsistentRead=True
        ).get("Item")

        if existing:
            last_sent = int(existing.get("last_sent_at", 0))

            if now - last_sent < OTP_RESEND_COOLDOWN_SECONDS:
                raise HTTPException(
                    status_code=429,
                    detail="Please wait before requesting another OTP"
                )

        otp = f"{secrets.randbelow(1_000_000):06d}"

        item = {
            "email": email,
            "otp_hash": hash_otp(email, otp),
            "expires_at": now + OTP_VALIDITY_SECONDS,
            "last_sent_at": now,
            "attempts": 0,
            "verified": False,
            "verified_until": 0
        }

        # Store OTP before sending the email.
        otp_table.put_item(Item=item)

        try:
            ses_client.send_email(
                Source=SES_FROM_EMAIL,
                Destination={
                    "ToAddresses": [email]
                },
                Message={
                    "Subject": {
                        "Data": "Temple Application - Email Verification OTP",
                        "Charset": "UTF-8"
                    },
                    "Body": {
                        "Text": {
                            "Data": (
                                f"Your email verification OTP is {otp}.\n\n"
                                "This OTP expires in 60 seconds.\n"
                                "Do not share this code with anyone."
                            ),
                            "Charset": "UTF-8"
                        }
                    }
                }
            )

        except ClientError:
            # Invalidate the OTP if SES cannot send the message.
            otp_table.delete_item(
                Key={"email": email}
            )

            raise HTTPException(
                status_code=502,
                detail=(
                    "Unable to send OTP. Check SES permissions, "
                    "verified recipient status and AWS configuration."
                )
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


@router.post("/verify-otp")
def verify_otp(request: VerifyOTPRequest):
    email = str(request.email).strip().lower()
    now = int(time.time())

    try:
        response = otp_table.get_item(
            Key={"email": email},
            ConsistentRead=True
        )

        item = response.get("Item")

        if not item:
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
                detail=f"Invalid OTP. Attempts remaining: {OTP_MAX_ATTEMPTS - new_attempts}"
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
