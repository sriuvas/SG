from fastapi import APIRouter, HTTPException, Depends

from botocore.exceptions import ClientError

from app.models.donation import (

    DonationCreateOrder,

    DonationPaymentVerify

)

from app.auth.dependencies import (

    get_current_user,

    require_admin

)

from app.services.razorpay_service import (

    create_razorpay_order,

    verify_razorpay_payment

)

from app.services.receipt_service import (

    generate_donation_receipt_pdf,

    upload_receipt_to_s3,

    generate_receipt_presigned_url

)

from database import dynamodb

import uuid

import os

from datetime import datetime, timezone

from decimal import Decimal

# ==================================================

# ROUTER

# ==================================================

router = APIRouter(

    prefix="/api/donations",

    tags=["Donations"]

)

# ==================================================

# DynamoDB Table

# ==================================================

TABLE_NAME = os.getenv(

    "DONATIONS_TABLE_NAME",

    "Donations_Table"

)

table = dynamodb.Table(TABLE_NAME)
donations_table = table

# ==================================================

# USER - CREATE RAZORPAY DONATION ORDER

# ==================================================

@router.post("/create-order")

def create_donation_order(

    donation: DonationCreateOrder,

    current_user: dict = Depends(get_current_user)

):

    try:

        donation_id = str(uuid.uuid4())

        current_time = datetime.now(

            timezone.utc

        ).isoformat()

        amount = Decimal(

            str(donation.amount)

        ).quantize(

            Decimal("0.01")

        )

        # Convert INR to paise

        amount_paise = int(

            amount * 100

        )

        receipt_number = (

            f"RCP-DON-"

            f"{uuid.uuid4().hex[:8].upper()}"

        )

        transaction_id = (

            f"TXN-DON-"

            f"{uuid.uuid4().hex[:8].upper()}"

        )

        # Create Razorpay order

        razorpay_order = create_razorpay_order(

            amount_paise=amount_paise,

            receipt=receipt_number

        )

        item = {

            "donation_id": donation_id,

            "user_id": str(

                current_user.get("user_id")

            ),

            "donor_name": donation.donor_name,

            "email": donation.email,

            "phone": donation.phone,

            "place": donation.place,

            "amount": amount,

            "payment_status": "PENDING",

            "transaction_id": transaction_id,

            "receipt_number": receipt_number,

            "razorpay_order_id": razorpay_order[

                "id"

            ],

            "razorpay_payment_id": None,

            "razorpay_signature": None,

            "receipt_s3_key": None,

            "receipt_s3_url": None,

            "created_at": current_time,

            "updated_at": current_time

        }

        table.put_item(

            Item=item

        )

        return {

            "message": "Donation order created successfully",

            "donation_id": donation_id,

            "amount": float(amount),

            "currency": "INR",

            "razorpay_order_id": razorpay_order[

                "id"

            ],

            "razorpay_key_id": os.getenv(

                "RAZORPAY_KEY_ID"

            ),

            "transaction_id": transaction_id,

            "receipt_number": receipt_number

        }

    except ClientError as error:

        raise HTTPException(

            status_code=500,

            detail=(

                "DynamoDB error: "

                f"{error.response['Error']['Message']}"

            )

        )

    except Exception as error:

        raise HTTPException(

            status_code=500,

            detail=f"Donation order creation failed: {str(error)}"

        )

# ==================================================

# USER - VERIFY RAZORPAY PAYMENT

# ==================================================

@router.post("/verify-payment")

def verify_donation_payment(

    payment: DonationPaymentVerify,

    current_user: dict = Depends(get_current_user)

):

    try:

        # ------------------------------------------

        # Get donation

        # ------------------------------------------

        response = table.get_item(

            Key={

                "donation_id": payment.donation_id

            }

        )

        donation = response.get("Item")

        if not donation:

            raise HTTPException(

                status_code=404,

                detail="Donation not found"

            )

        # ------------------------------------------

        # Verify ownership

        # ------------------------------------------

        if str(

            donation.get("user_id")

        ) != str(

            current_user.get("user_id")

        ):

            raise HTTPException(

                status_code=403,

                detail="You are not authorized to verify this donation"

            )

        # ------------------------------------------

        # Prevent duplicate verification

        # ------------------------------------------

        if donation.get("payment_status") == "SUCCESS":

            raise HTTPException(

                status_code=400,

                detail="Donation payment is already successful"

            )

        # ------------------------------------------

        # Verify Razorpay order ID

        # ------------------------------------------

        if (

            donation.get("razorpay_order_id")

            != payment.razorpay_order_id

        ):

            raise HTTPException(

                status_code=400,

                detail="Razorpay order ID does not match"

            )

        # ------------------------------------------

        # Verify Razorpay signature

        # ------------------------------------------

        verify_razorpay_payment(

            razorpay_order_id=payment.razorpay_order_id,

            razorpay_payment_id=payment.razorpay_payment_id,

            razorpay_signature=payment.razorpay_signature

        )

        current_time = datetime.now(

            timezone.utc

        ).isoformat()

        # ------------------------------------------

        # Generate receipt number if needed

        # ------------------------------------------

        receipt_number = donation.get(

            "receipt_number"

        )

        if not receipt_number:

            receipt_number = (

                f"RCP-DON-"

                f"{uuid.uuid4().hex[:8].upper()}"

            )

        # ------------------------------------------

        # Update successful payment

        # ------------------------------------------

        table.update_item(

            Key={

                "donation_id": payment.donation_id

            },

            UpdateExpression="""

                SET payment_status = :status,

                    razorpay_payment_id = :payment_id,

                    razorpay_signature = :signature,

                    receipt_number = :receipt_number,

                    updated_at = :updated_at

            """,

            ExpressionAttributeValues={

                ":status": "SUCCESS",

                ":payment_id":

                    payment.razorpay_payment_id,

                ":signature":

                    payment.razorpay_signature,

                ":receipt_number":

                    receipt_number,

                ":updated_at":

                    current_time

            }

        )

        # ------------------------------------------

        # Get updated donation

        # ------------------------------------------

        updated_response = table.get_item(

            Key={

                "donation_id": payment.donation_id

            }

        )

        updated_donation = updated_response.get(

            "Item"

        )

        # ------------------------------------------

        # Generate DONATION receipt PDF

        # ------------------------------------------

        pdf_bytes = generate_donation_receipt_pdf(

            updated_donation

        )

        # ------------------------------------------

        # Upload receipt to S3

        # ------------------------------------------

        s3_result = upload_receipt_to_s3(

            pdf_bytes=pdf_bytes,

            receipt_number=receipt_number

        )

        receipt_s3_key = s3_result.get(

            "receipt_s3_key"

        )

        receipt_s3_url = s3_result.get(

            "receipt_s3_url"

        )

        # ------------------------------------------

        # Save S3 information

        # ------------------------------------------

        table.update_item(

            Key={

                "donation_id": payment.donation_id

            },

            UpdateExpression="""

                SET receipt_s3_key = :key,

                    receipt_s3_url = :url,

                    updated_at = :updated_at

            """,

            ExpressionAttributeValues={

                ":key": receipt_s3_key,

                ":url": receipt_s3_url,

                ":updated_at": datetime.now(

                    timezone.utc

                ).isoformat()

            }

        )

        # ------------------------------------------

        # Generate temporary private URL

        # ------------------------------------------

        presigned_url = generate_receipt_presigned_url(

            receipt_s3_key

        )

        # ------------------------------------------

        # Return successful response

        # ------------------------------------------

        return {

            "message":

                "Donation payment verified successfully",

            "donation_id":

                payment.donation_id,

            "amount":

                float(

                    updated_donation["amount"]

                ),

            "payment_status":

                "SUCCESS",

            "transaction_id":

                updated_donation.get(

                    "transaction_id"

                ),

            "receipt_number":

                receipt_number,

            "receipt_s3_key":

                receipt_s3_key,

            "receipt_s3_url":

                receipt_s3_url,

            "receipt_presigned_url":

                presigned_url

        }

    except HTTPException:

        raise

    except Exception as error:

        raise HTTPException(

            status_code=400,

            detail=f"Payment verification failed: {str(error)}"

        )

# ==================================================

# USER - GET MY PAYMENT HISTORY

# Most recent payment first

# ==================================================

@router.get("/my-history")

def get_my_payment_history(

    current_user: dict = Depends(get_current_user)

):

    try:

        # ------------------------------------------

        # Get current logged-in user's ID

        # ------------------------------------------

        current_user_id = str(

            current_user.get("user_id")

        )

        # ------------------------------------------

        # Get first page from DynamoDB

        # ------------------------------------------

        response = table.scan()

        donations = response.get(

            "Items",

            []

        )

        # ------------------------------------------

        # Get remaining DynamoDB pages

        # ------------------------------------------

        while "LastEvaluatedKey" in response:

            response = table.scan(

                ExclusiveStartKey=response[

                    "LastEvaluatedKey"

                ]

            )

            donations.extend(

                response.get(

                    "Items",

                    []

                )

            )

        # ------------------------------------------

        # Only this user's successful payments

        # ------------------------------------------

        donations = [

            donation

            for donation in donations

            if str(

                donation.get("user_id")

            ) == current_user_id

            and donation.get(

                "payment_status"

            ) == "SUCCESS"

        ]

        # ------------------------------------------
        # Generate fresh receipt URL & auto-repair if needed
        # ------------------------------------------
        for donation in donations:
            donation["receipt_presigned_url"] = None
            donation["receipt_url"] = None
            receipt_s3_key = donation.get("receipt_s3_key")
            has_valid_key = (
                isinstance(receipt_s3_key, str)
                and receipt_s3_key.strip().startswith("receipts/")
                and receipt_s3_key.strip().lower() not in {"", "receipt_s3_key", "receipt_s3_url", "none", "null"}
            )
            if has_valid_key:
                try:
                    presigned = generate_receipt_presigned_url(receipt_s3_key.strip())
                    donation["receipt_presigned_url"] = presigned
                    donation["receipt_url"] = presigned
                    donation["receipt_s3_url"] = presigned
                    donation["s3_url"] = presigned
                    donation["pdf_url"] = presigned
                except Exception as receipt_err:
                    print("Failed to generate donation receipt URL:", receipt_err)
            else:
                try:
                    receipt_number = donation.get("receipt_number") or f"RCP-DON-{uuid.uuid4().hex[:8].upper()}"
                    donation["receipt_number"] = receipt_number
                    pdf_bytes = generate_donation_receipt_pdf(donation)
                    s3_res = upload_receipt_to_s3(pdf_bytes, receipt_number)
                    clean_key = s3_res["receipt_s3_key"]
                    clean_url = s3_res["receipt_s3_url"]
                    presigned = generate_receipt_presigned_url(clean_key)
                    donation["receipt_s3_key"] = clean_key
                    donation["receipt_s3_url"] = clean_url
                    donation["receipt_presigned_url"] = presigned
                    donation["receipt_url"] = presigned
                    donation["receipt_s3_url"] = presigned
                    donation["s3_url"] = presigned
                    donation["pdf_url"] = presigned
                    donations_table.update_item(
                        Key={"donation_id": donation["donation_id"]},
                        UpdateExpression="SET receipt_s3_key = :k, receipt_s3_url = :u, receipt_number = :r",
                        ExpressionAttributeValues={
                            ":k": clean_key,
                            ":u": clean_url,
                            ":r": receipt_number
                        }
                    )
                except Exception as repair_err:
                    print("Auto-repair error for donation receipt:", repair_err)
        # ------------------------------------------

        # Sort most recent payment first

        # ------------------------------------------

        donations.sort(

            key=lambda donation: donation.get(

                "created_at",

                ""

            ),

            reverse=True

        )

        # ------------------------------------------

        # Convert Decimal to float

        # ------------------------------------------

        for donation in donations:

            if "amount" in donation:

                donation["amount"] = float(

                    donation["amount"]

                )

        # ------------------------------------------

        # Return payment history

        # ------------------------------------------

        return {

            "message":

                "Payment history retrieved successfully",

            "total_payments":

                len(donations),

            "payments":

                donations

        }

    except ClientError as error:

        raise HTTPException(

            status_code=500,

            detail=(

                "DynamoDB error: "

                f"{error.response['Error']['Message']}"

            )

        )

    except Exception as error:

        raise HTTPException(

            status_code=500,

            detail=(

                "Failed to retrieve payment history: "

                f"{str(error)}"

            )

        )


# ==================================================
# GET
# Logged-in User - Single Donation Receipt
# ==================================================

@router.get("/{donation_id}/receipt")
def get_donation_receipt(
    donation_id: str,
    current_user: dict = Depends(get_current_user)
):
    try:
        user_id = str(current_user["user_id"])
        is_admin = current_user.get("role") == "admin"

        response = donations_table.get_item(
            Key={"donation_id": donation_id}
        )
        donation = response.get("Item")
        if not donation:
            raise HTTPException(
                status_code=404,
                detail="Donation not found"
            )

        if str(donation.get("user_id")) != user_id and not is_admin:
            raise HTTPException(
                status_code=403,
                detail="You do not have permission to view this receipt"
            )

        status = str(donation.get("payment_status") or donation.get("status") or "").upper()
        if status != "SUCCESS":
            raise HTTPException(
                status_code=400,
                detail="Receipt is only available for successful donations"
            )

        receipt_s3_key = donation.get("receipt_s3_key")
        has_valid_key = (
            isinstance(receipt_s3_key, str)
            and receipt_s3_key.strip().startswith("receipts/")
            and receipt_s3_key.strip().lower() not in {"", "receipt_s3_key", "receipt_s3_url", "none", "null"}
        )

        if has_valid_key:
            presigned_url = generate_receipt_presigned_url(receipt_s3_key.strip())
        else:
            receipt_number = donation.get("receipt_number") or f"RCP-DON-{uuid.uuid4().hex[:8].upper()}"
            donation["receipt_number"] = receipt_number
            pdf_bytes = generate_donation_receipt_pdf(donation)
            s3_res = upload_receipt_to_s3(pdf_bytes, receipt_number)
            clean_key = s3_res["receipt_s3_key"]
            clean_url = s3_res["receipt_s3_url"]
            presigned_url = generate_receipt_presigned_url(clean_key)

            donations_table.update_item(
                Key={"donation_id": donation_id},
                UpdateExpression="SET receipt_s3_key = :k, receipt_s3_url = :u, receipt_number = :r",
                ExpressionAttributeValues={
                    ":k": clean_key,
                    ":u": clean_url,
                    ":r": receipt_number
                }
            )

        return {
            "message": "Donation receipt retrieved successfully",
            "donation_id": donation_id,
            "receipt_number": donation.get("receipt_number"),
            "receipt_url": presigned_url,
            "receipt_presigned_url": presigned_url,
            "receipt_s3_url": presigned_url,
            "s3_url": presigned_url,
            "pdf_url": presigned_url
        }

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve donation receipt: {str(error)}"
        )

# ==================================================
# ADMIN - DONATION LEADERBOARD
# Successful donations, highest amount first
# ==================================================

@router.get("/leaderboard")
def get_donation_leaderboard():
    try:
        # Retrieve every page of donation records from DynamoDB.
        response = table.scan()
        all_donations = response.get("Items", [])

        while response.get("LastEvaluatedKey"):
            response = table.scan(
                ExclusiveStartKey=response["LastEvaluatedKey"]
            )
            all_donations.extend(response.get("Items", []))

        # Only include donations whose payments were successfully verified.
        successful_donations = [
            donation
            for donation in all_donations
            if donation.get("payment_status") == "SUCCESS"
        ]

        # Sort from the largest amount to the smallest amount.
        successful_donations.sort(
            key=lambda donation: Decimal(str(donation.get("amount", 0))),
            reverse=True,
        )

        # Return only the fields required by the leaderboard.
        leaderboard = [
            {
                "donor_name": donation.get("donor_name") or "",
                "amount": float(donation.get("amount", 0)),
                "place": donation.get("place") or "-",
            }
            for donation in successful_donations
        ]

        return {
            "message": "Donation leaderboard retrieved successfully",
            "total_donations": len(leaderboard),
            "donations": leaderboard,
        }

    except ClientError as error:
        raise HTTPException(
            status_code=500,
            detail=(
                "DynamoDB error: "
                f"{error.response['Error']['Message']}"
            ),
        )

# ==================================================

# ADMIN - GET DONATIONS

# Highest amount first

# ==================================================

@router.get("")

def get_donations(

    current_user: dict = Depends(require_admin)

):

    try:

        # ------------------------------------------

        # Get first page

        # ------------------------------------------

        response = table.scan()

        donations = response.get(

            "Items",

            []

        )

        # ------------------------------------------

        # Get remaining pages

        # ------------------------------------------

        while "LastEvaluatedKey" in response:

            response = table.scan(

                ExclusiveStartKey=response[

                    "LastEvaluatedKey"

                ]

            )

            donations.extend(

                response.get(

                    "Items",

                    []

                )

            )

        # ------------------------------------------

        # Only successful donations

        # ------------------------------------------

        donations = [

            donation

            for donation in donations

            if donation.get(

                "payment_status"

            ) == "SUCCESS"

        ]

        # ------------------------------------------

        # Generate fresh presigned URL

        # for every successful donation

        # ------------------------------------------

        for donation in donations:

            receipt_s3_key = donation.get(

                "receipt_s3_key"

            )

            if receipt_s3_key:

                try:

                    donation[

                        "receipt_presigned_url"

                    ] = generate_receipt_presigned_url(

                        receipt_s3_key

                    )

                except Exception:

                    donation[

                        "receipt_presigned_url"

                    ] = None

            else:

                donation[

                    "receipt_presigned_url"

                ] = None

        # ------------------------------------------

        # Sort highest donation first

        # ------------------------------------------

        donations.sort(

            key=lambda donation: Decimal(

                str(

                    donation.get(

                        "amount",

                        0

                    )

                )

            ),

            reverse=True

        )

        # ------------------------------------------

        # Convert Decimal for JSON response

        # ------------------------------------------

        for donation in donations:

            if "amount" in donation:

                donation["amount"] = float(

                    donation["amount"]

                )

        # ------------------------------------------

        # Return response

        # ------------------------------------------

        return {

            "message":

                "Donations retrieved successfully",

            "total_donations":

                len(donations),

            "donations":

                donations

        }

    except ClientError as error:

        raise HTTPException(

            status_code=500,

            detail=(

                "DynamoDB error: "

                f"{error.response['Error']['Message']}"

            )

        )