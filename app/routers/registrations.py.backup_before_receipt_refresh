from fastapi import APIRouter, HTTPException, Depends, Query

from botocore.exceptions import ClientError

from boto3.dynamodb.conditions import Key, Attr

from decimal import Decimal, InvalidOperation



from app.models.registration import (

    EventRegistrationCreate,

    EventRegistrationPaymentVerify,

)



from app.auth.dependencies import (

    get_current_user,

    require_admin,

)



from app.services.razorpay_service import (

    create_razorpay_order,

    verify_razorpay_payment,

)



from app.services.receipt_service import (

    generate_event_receipt_pdf,

    generate_receipt_presigned_url,

)



from database import dynamodb



import boto3

import os

import uuid



from datetime import datetime, timezone





# ==================================================

# Router

# ==================================================



router = APIRouter(

    prefix="/api/event-registrations",

    tags=["Event Registrations"]

)





# ==================================================

# DynamoDB Tables

# ==================================================



EVENTS_TABLE_NAME = os.getenv(

    "EVENTS_TABLE_NAME",

    "Events_table"

)



REGISTRATIONS_TABLE_NAME = os.getenv(

    "EVENT_REGISTRATIONS_TABLE_NAME",

    "Event_Registrations_Table"

)



events_table = dynamodb.Table(

    EVENTS_TABLE_NAME

)



registrations_table = dynamodb.Table(

    REGISTRATIONS_TABLE_NAME

)





# ==================================================

# S3 Configuration

# ==================================================



S3_BUCKET_NAME = os.getenv(

    "AWS_STORAGE_BUCKET_NAME"

)



S3_REGION_NAME = os.getenv(

    "AWS_S3_REGION_NAME",

    "eu-north-1"

)



if not S3_BUCKET_NAME:

    raise RuntimeError(

        "AWS_STORAGE_BUCKET_NAME is not configured"

    )



s3_client = boto3.client(

    "s3",

    region_name=S3_REGION_NAME

)





# ==================================================

# Helper Functions

# ==================================================



def generate_transaction_id():



    token = uuid.uuid4().hex[:12].upper()



    return f"TXN-EVT-{token}"





def generate_receipt_number():



    token = uuid.uuid4().hex[:12].upper()



    return f"RCP-EVT-{token}"





def get_current_timestamp():



    return datetime.now(

        timezone.utc

    ).isoformat()





# ==================================================

# Generate and Upload Event Receipt

# ==================================================



def generate_and_upload_event_receipt(

    registration: dict

):



    try:



        # ------------------------------------------

        # Generate PDF

        # ------------------------------------------



        pdf_bytes = generate_event_receipt_pdf(

            registration

        )



        # ------------------------------------------

        # S3 file name

        # ------------------------------------------



        receipt_number = registration.get(

            "receipt_number"

        )



        s3_key = (

            f"receipts/{receipt_number}.pdf"

        )



        # ------------------------------------------

        # Upload PDF to S3

        # ------------------------------------------



        s3_client.put_object(

            Bucket=S3_BUCKET_NAME,

            Key=s3_key,

            Body=pdf_bytes,

            ContentType="application/pdf"

        )



        # ------------------------------------------

        # Generate presigned URL

        # ------------------------------------------



        receipt_s3_url = s3_client.generate_presigned_url(

            "get_object",

            Params={

                "Bucket": S3_BUCKET_NAME,

                "Key": s3_key

            },

            ExpiresIn=3600

        )



        return {

            "receipt_s3_key": s3_key,

            "receipt_s3_url": receipt_s3_url

        }



    except Exception as error:



        raise HTTPException(

            status_code=500,

            detail=(

                "Receipt generation/upload failed: "

                f"{str(error)}"

            )

        )





# ==================================================

# GET

# Admin - Get Event Registrations

#

# Supports:

# 1. Get all registrations

# 2. Filter by event_id

# 3. Filter by status

# 4. Filter by event_id + status

# ==================================================



@router.get("")

def get_event_registrations(

    event_id: str | None = Query(

        default=None,

        description="Filter registrations by event ID"

    ),

    status: str | None = Query(

        default=None,

        description="Filter by status: PENDING, SUCCESS, or FAILED"

    ),

    current_user: dict = Depends(require_admin)

):



    try:



        # ------------------------------------------

        # Clean event_id

        # ------------------------------------------



        if event_id:



            event_id = event_id.strip()



            if not event_id:

                event_id = None



        # ------------------------------------------

        # Clean and validate status

        # ------------------------------------------



        if status:



            status = status.strip().upper()



            allowed_statuses = {

                "PENDING",

                "SUCCESS",

                "FAILED"

            }



            if status not in allowed_statuses:



                raise HTTPException(

                    status_code=400,

                    detail=(

                        "Invalid status. Use "

                        "PENDING, SUCCESS, or FAILED"

                    )

                )



        registrations = []



        # ==================================================

        # Filter by event_id + status

        # ==================================================



        if event_id and status:



            response = registrations_table.query(

                IndexName="event_id-index",

                KeyConditionExpression=

                    Key("event_id").eq(event_id),

                FilterExpression=

                    Attr("status").eq(status)

            )



            registrations.extend(

                response.get("Items", [])

            )



            while response.get(

                "LastEvaluatedKey"

            ):



                response = registrations_table.query(

                    IndexName="event_id-index",

                    KeyConditionExpression=

                        Key("event_id").eq(event_id),

                    FilterExpression=

                        Attr("status").eq(status),

                    ExclusiveStartKey=

                        response["LastEvaluatedKey"]

                )



                registrations.extend(

                    response.get("Items", [])

                )



        # ==================================================

        # Filter by event_id only

        # ==================================================



        elif event_id:



            response = registrations_table.query(

                IndexName="event_id-index",

                KeyConditionExpression=

                    Key("event_id").eq(event_id)

            )



            registrations.extend(

                response.get("Items", [])

            )



            while response.get(

                "LastEvaluatedKey"

            ):



                response = registrations_table.query(

                    IndexName="event_id-index",

                    KeyConditionExpression=

                        Key("event_id").eq(event_id),

                    ExclusiveStartKey=

                        response["LastEvaluatedKey"]

                )



                registrations.extend(

                    response.get("Items", [])

                )



        # ==================================================

        # Filter by status only

        # ==================================================



        elif status:



            response = registrations_table.query(

                IndexName="status-index",

                KeyConditionExpression=

                    Key("status").eq(status)

            )



            registrations.extend(

                response.get("Items", [])

            )



            while response.get(

                "LastEvaluatedKey"

            ):



                response = registrations_table.query(

                    IndexName="status-index",

                    KeyConditionExpression=

                        Key("status").eq(status),

                    ExclusiveStartKey=

                        response["LastEvaluatedKey"]

                )



                registrations.extend(

                    response.get("Items", [])

                )



        # ==================================================

        # No filters - Get all

        # ==================================================



        else:



            response = registrations_table.scan()



            registrations.extend(

                response.get("Items", [])

            )



            while response.get(

                "LastEvaluatedKey"

            ):



                response = registrations_table.scan(

                    ExclusiveStartKey=

                        response["LastEvaluatedKey"]

                )



                registrations.extend(

                    response.get("Items", [])

                )



        # ------------------------------------------

        # Sort newest registrations first

        # ------------------------------------------



        registrations.sort(

            key=lambda item:

                item.get(

                    "created_at",

                    ""

                ),

            reverse=True

        )



        return {

            "message":

                "Event registrations retrieved successfully",



            "count":

                len(registrations),



            "filters": {

                "event_id":

                    event_id,



                "status":

                    status

            },



            "registrations":

                registrations

        }



    except HTTPException:

        raise



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

                "Failed to retrieve event registrations: "

                f"{str(error)}"

            )

        )





# ==================================================
# GET
# Logged-in User - Event Payment History
# ==================================================

@router.get("/my-history")
def get_my_event_payment_history(
    current_user: dict = Depends(get_current_user)
):

    try:

        user_id = str(current_user["user_id"])

        registrations = []

        response = registrations_table.query(
            IndexName="user_id-index",
            KeyConditionExpression=Key("user_id").eq(user_id),
            ScanIndexForward=False
        )

        registrations.extend(
            response.get("Items", [])
        )

        while response.get("LastEvaluatedKey"):

            response = registrations_table.query(
                IndexName="user_id-index",
                KeyConditionExpression=Key("user_id").eq(user_id),
                ScanIndexForward=False,
                ExclusiveStartKey=response["LastEvaluatedKey"]
            )

            registrations.extend(
                response.get("Items", [])
            )

        for registration in registrations:
            registration["receipt_presigned_url"] = None
            status = str(registration.get("status") or registration.get("payment_status") or "").upper()
            is_confirmed = (
                status in {"SUCCESS", "CONFIRMED", "COMPLETED", "PAID"}
                or registration.get("payment_required") is False
            )
            if not is_confirmed:
                continue

            receipt_s3_key = registration.get("receipt_s3_key")
            has_valid_key = (
                isinstance(receipt_s3_key, str)
                and receipt_s3_key.strip().startswith("receipts/")
                and receipt_s3_key.strip().lower() not in {"", "receipt_s3_key", "receipt_s3_url", "none", "null"}
            )

            if has_valid_key:
                try:
                    presigned = generate_receipt_presigned_url(receipt_s3_key.strip())
                    registration["receipt_presigned_url"] = presigned
                    registration["receipt_url"] = presigned
                    registration["receipt_s3_url"] = presigned
                    registration["s3_url"] = presigned
                    registration["pdf_url"] = presigned
                except Exception as e:
                    print("Error generating presigned URL for event receipt:", e)
            else:
                try:
                    receipt_number = registration.get("receipt_number") or generate_receipt_number()
                    registration["receipt_number"] = receipt_number
                    receipt_result = generate_and_upload_event_receipt(registration)
                    clean_key = receipt_result["receipt_s3_key"]
                    clean_url = receipt_result["receipt_s3_url"]
                    registration["receipt_s3_key"] = clean_key
                    registration["receipt_s3_url"] = clean_url
                    registration["receipt_presigned_url"] = clean_url
                    registration["receipt_url"] = clean_url
                    registration["s3_url"] = clean_url
                    registration["pdf_url"] = clean_url

                    registrations_table.update_item(
                        Key={"registration_id": registration["registration_id"]},
                        UpdateExpression="SET receipt_s3_key = :k, receipt_s3_url = :u, receipt_number = :r, updated_at = :upd",
                        ExpressionAttributeValues={
                            ":k": clean_key,
                            ":u": clean_url,
                            ":r": receipt_number,
                            ":upd": get_current_timestamp()
                        }
                    )
                except Exception as e:
                    print("Auto-repair error for event registration receipt:", e)

        return {
            "message": "Event payment history retrieved successfully",
            "count": len(registrations),
            "registrations": registrations
        }

    except HTTPException:
        raise

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
                "Failed to retrieve event payment history: "
                f"{str(error)}"
            )
        )

# ==================================================
# GET
# Logged-in User - Single Event Registration Receipt
# ==================================================

@router.get("/{registration_id}/receipt")
def get_event_registration_receipt(
    registration_id: str,
    current_user: dict = Depends(get_current_user)
):
    try:
        user_id = str(current_user["user_id"])
        is_admin = current_user.get("role") == "admin"

        response = registrations_table.get_item(
            Key={"registration_id": registration_id}
        )
        registration = response.get("Item")
        if not registration:
            raise HTTPException(
                status_code=404,
                detail="Event registration not found"
            )

        if str(registration.get("user_id")) != user_id and not is_admin:
            raise HTTPException(
                status_code=403,
                detail="You do not have permission to view this receipt"
            )

        status = str(registration.get("status") or registration.get("payment_status") or "").upper()
        is_confirmed = (
            status in {"SUCCESS", "CONFIRMED", "COMPLETED", "PAID"}
            or registration.get("payment_required") is False
        )
        if not is_confirmed:
            raise HTTPException(
                status_code=400,
                detail="Receipt is only available for successful or confirmed registrations"
            )

        receipt_s3_key = registration.get("receipt_s3_key")
        has_valid_key = (
            isinstance(receipt_s3_key, str)
            and receipt_s3_key.strip().startswith("receipts/")
            and receipt_s3_key.strip().lower() not in {"", "receipt_s3_key", "receipt_s3_url", "none", "null"}
        )

        if has_valid_key:
            presigned_url = generate_receipt_presigned_url(receipt_s3_key.strip())
        else:
            receipt_number = registration.get("receipt_number") or generate_receipt_number()
            registration["receipt_number"] = receipt_number
            receipt_result = generate_and_upload_event_receipt(registration)
            clean_key = receipt_result["receipt_s3_key"]
            clean_url = receipt_result["receipt_s3_url"]
            presigned_url = clean_url

            registrations_table.update_item(
                Key={"registration_id": registration_id},
                UpdateExpression="SET receipt_s3_key = :k, receipt_s3_url = :u, receipt_number = :r, updated_at = :upd",
                ExpressionAttributeValues={
                    ":k": clean_key,
                    ":u": clean_url,
                    ":r": receipt_number,
                    ":upd": get_current_timestamp()
                }
            )

        return {
            "message": "Event registration receipt retrieved successfully",
            "registration_id": registration_id,
            "receipt_number": registration.get("receipt_number"),
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
            detail=f"Failed to retrieve event receipt: {str(error)}"
        )


# ==================================================
# POST
# Create Event Registration / Razorpay Order
# ==================================================



@router.post("/create-order")

def create_registration_order(

    registration: EventRegistrationCreate,

    current_user: dict = Depends(get_current_user)

):



    try:



        # ------------------------------------------

        # Get Event

        # ------------------------------------------



        event_response = events_table.get_item(

            Key={

                "event_id":

                    registration.event_id

            }

        )



        event = event_response.get(

            "Item"

        )



        if not event:



            raise HTTPException(

                status_code=404,

                detail="Event not found"

            )



        # ------------------------------------------

        # Get Event Price

        # ------------------------------------------



        try:



            unit_price = Decimal(

                str(

                    event.get(

                        "price",

                        "0"

                    )

                )

            )



        except (

            InvalidOperation,

            ValueError

        ):



            raise HTTPException(

                status_code=500,

                detail="Invalid event price configured"

            )



        # ------------------------------------------

        # Validate Price

        # ------------------------------------------



        if unit_price < Decimal("0"):



            raise HTTPException(

                status_code=500,

                detail="Event price cannot be negative"

            )



        # ------------------------------------------

        # Calculate Total Amount

        # ------------------------------------------



        total_amount = (

            unit_price *

            registration.attendees_count

        )



        total_amount = total_amount.quantize(

            Decimal("0.01")

        )



        # ------------------------------------------

        # Generate IDs

        # ------------------------------------------



        registration_id = str(

            uuid.uuid4()

        )



        transaction_id = (

            generate_transaction_id()

        )



        receipt_number = (

            generate_receipt_number()

        )



        current_time = (

            get_current_timestamp()

        )



        # ------------------------------------------

        # Get User ID

        # ------------------------------------------



        user_id = str(

            current_user["user_id"]

        )



        # ==================================================

        # FREE EVENT

        # ==================================================



        if total_amount == Decimal("0.00"):



            item = {



                "registration_id":

                    registration_id,



                "event_id":

                    registration.event_id,



                "event_name":

                    event.get(

                        "event_name",

                        ""

                    ),



                "user_id":

                    user_id,



                "devotee_name":

                    registration.name,



                "email":

                    registration.email,



                "phone":

                    registration.phone,



                "gothram":

                    registration.gothram,



                "nakshatram":

                    registration.nakshatram,



                "attendees_count":

                    registration.attendees_count,



                "unit_price":

                    unit_price,



                "total_amount":

                    total_amount,



                "status":

                    "SUCCESS",



                "transaction_id":

                    transaction_id,



                "receipt_number":

                    receipt_number,



                "razorpay_order_id":

                    None,



                "razorpay_payment_id":

                    None,



                "razorpay_signature":

                    None,



                "receipt_s3_key":

                    None,



                "receipt_s3_url":

                    None,



                "created_at":

                    current_time,



                "updated_at":

                    current_time,

            }



            # ------------------------------------------

            # Generate FREE receipt

            # ------------------------------------------



            receipt_result = (

                generate_and_upload_event_receipt(

                    item

                )

            )



            item["receipt_s3_key"] = (

                receipt_result[

                    "receipt_s3_key"

                ]

            )



            item["receipt_s3_url"] = (

                receipt_result[

                    "receipt_s3_url"

                ]

            )



            registrations_table.put_item(

                Item=item

            )



            return {



                "message":

                    "Free event registration successful",



                "registration_id":

                    registration_id,



                "event_id":

                    registration.event_id,



                "event_name":

                    event.get(

                        "event_name",

                        ""

                    ),



                "status":

                    "SUCCESS",



                "transaction_id":

                    transaction_id,



                "receipt_number":

                    receipt_number,



                "unit_price":

                    float(unit_price),



                "total_amount":

                    float(total_amount),



                "payment_required":

                    False,



                "receipt_s3_key":

                    item["receipt_s3_key"],



                "receipt_s3_url":

                    item["receipt_s3_url"],



                "razorpay_order_id":

                    None,

            }



        # ==================================================

        # PAID EVENT

        # ==================================================



        # Razorpay expects amount in paise.

        amount_paise = int(

            total_amount * Decimal("100")

        )



        razorpay_order = (

            create_razorpay_order(

                amount_paise=amount_paise,

                receipt=receipt_number

            )

        )



        razorpay_order_id = (

            razorpay_order["id"]

        )



        # ------------------------------------------

        # Save Pending Registration

        # ------------------------------------------



        item = {



            "registration_id":

                registration_id,



            "event_id":

                registration.event_id,



            "event_name":

                event.get(

                    "event_name",

                    ""

                ),



            "user_id":

                user_id,



            "devotee_name":

                registration.name,



            "email":

                registration.email,



            "phone":

                registration.phone,



            "gothram":

                registration.gothram,



            "nakshatram":

                registration.nakshatram,



            "attendees_count":

                registration.attendees_count,



            "unit_price":

                unit_price,



            "total_amount":

                total_amount,



            "status":

                "PENDING",



            "transaction_id":

                transaction_id,



            "receipt_number":

                receipt_number,



            "razorpay_order_id":

                razorpay_order_id,



            "razorpay_payment_id":

                None,



            "razorpay_signature":

                None,



            "receipt_s3_key":

                None,



            "receipt_s3_url":

                None,



            "created_at":

                current_time,



            "updated_at":

                current_time,

        }



        registrations_table.put_item(

            Item=item

        )



        # ------------------------------------------

        # Return Razorpay Order

        # ------------------------------------------



        return {



            "message":

                "Registration created and Razorpay order created",



            "registration_id":

                registration_id,



            "event_id":

                registration.event_id,



            "event_name":

                event.get(

                    "event_name",

                    ""

                ),



            "status":

                "PENDING",



            "transaction_id":

                transaction_id,



            "receipt_number":

                receipt_number,



            "unit_price":

                float(unit_price),



            "attendees_count":

                registration.attendees_count,



            "total_amount":

                float(total_amount),



            "amount_paise":

                amount_paise,



            "payment_required":

                True,



            "razorpay_order_id":

                razorpay_order_id,



            "razorpay_key_id":

                os.getenv(

                    "RAZORPAY_KEY_ID"

                ),

        }



    except HTTPException:

        raise



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

                "Registration creation failed: "

                f"{str(error)}"

            )

        )





# ==================================================

# POST

# Verify Razorpay Payment

# ==================================================



@router.post("/verify-payment")

def verify_payment(

    payment: EventRegistrationPaymentVerify,



    current_user: dict = Depends(get_current_user)

):



    try:



        # ------------------------------------------

        # Get Registration

        # ------------------------------------------



        response = registrations_table.get_item(

            Key={

                "registration_id":

                    payment.registration_id

            }

        )



        registration = response.get(

            "Item"

        )



        if not registration:



            raise HTTPException(

                status_code=404,

                detail="Registration not found"

            )



        # ------------------------------------------

        # Verify User Ownership

        # ------------------------------------------



        user_id = str(

            current_user["user_id"]

        )



        if str(

            registration.get(

                "user_id"

            )

        ) != user_id:



            raise HTTPException(

                status_code=403,

                detail=(

                    "You are not authorized "

                    "to verify this registration"

                )

            )



        # ------------------------------------------

        # Check Registration Status

        # ------------------------------------------



        if registration.get(

            "status"

        ) == "SUCCESS":



            return {



                "message":

                    "Payment already verified",



                "registration_id":

                    payment.registration_id,



                "status":

                    "SUCCESS",



                "transaction_id":

                    registration.get(

                        "transaction_id"

                    ),



                "receipt_number":

                    registration.get(

                        "receipt_number"

                    ),



                "receipt_s3_key":

                    registration.get(

                        "receipt_s3_key"

                    ),



                "receipt_s3_url":

                    registration.get(

                        "receipt_s3_url"

                    ),

            }



        # ------------------------------------------

        # Check Razorpay Order ID

        # ------------------------------------------



        stored_order_id = (

            registration.get(

                "razorpay_order_id"

            )

        )



        if stored_order_id != (

            payment.razorpay_order_id

        ):



            raise HTTPException(

                status_code=400,

                detail=(

                    "Razorpay order ID does "

                    "not match the registration"

                )

            )



        # ------------------------------------------

        # Verify Razorpay Signature

        # ------------------------------------------



        try:



            verify_razorpay_payment(



                razorpay_order_id=

                    payment.razorpay_order_id,



                razorpay_payment_id=

                    payment.razorpay_payment_id,



                razorpay_signature=

                    payment.razorpay_signature

            )



        except Exception:



            # --------------------------------------

            # Mark Payment Failed

            # --------------------------------------



            registrations_table.update_item(



                Key={

                    "registration_id":

                        payment.registration_id

                },



                UpdateExpression="""

                    SET #status = :status,

                        updated_at = :updated_at

                """,



                ExpressionAttributeNames={

                    "#status":

                        "status"

                },



                ExpressionAttributeValues={



                    ":status":

                        "FAILED",



                    ":updated_at":

                        get_current_timestamp()

                }

            )



            raise HTTPException(

                status_code=400,

                detail="Payment verification failed"

            )



        # ------------------------------------------

        # Payment Verified Successfully

        # ------------------------------------------



        updated_time = (

            get_current_timestamp()

        )



        # ------------------------------------------

        # Update Payment Information

        # ------------------------------------------



        registrations_table.update_item(



            Key={

                "registration_id":

                    payment.registration_id

            },



            UpdateExpression="""

                SET #status = :status,

                    razorpay_payment_id = :payment_id,

                    razorpay_signature = :signature,

                    updated_at = :updated_at

            """,



            ExpressionAttributeNames={

                "#status":

                    "status"

            },



            ExpressionAttributeValues={



                ":status":

                    "SUCCESS",



                ":payment_id":

                    payment.razorpay_payment_id,



                ":signature":

                    payment.razorpay_signature,



                ":updated_at":

                    updated_time

            }

        )



        # ------------------------------------------

        # Get Updated Registration

        # ------------------------------------------



        updated_response = (

            registrations_table.get_item(

                Key={

                    "registration_id":

                        payment.registration_id

                }

            )

        )



        updated_registration = (

            updated_response.get(

                "Item"

            )

        )



        if not updated_registration:



            raise HTTPException(

                status_code=500,

                detail=(

                    "Registration could not be "

                    "retrieved after payment verification"

                )

            )



        # ------------------------------------------

        # Generate and Upload Receipt

        # ------------------------------------------



        receipt_result = (

            generate_and_upload_event_receipt(

                updated_registration

            )

        )



        # ------------------------------------------

        # Save Receipt S3 Information

        # ------------------------------------------



        registrations_table.update_item(



            Key={

                "registration_id":

                    payment.registration_id

            },



            UpdateExpression="""

                SET receipt_s3_key = :receipt_s3_key,

                    receipt_s3_url = :receipt_s3_url,

                    updated_at = :updated_at

            """,



            ExpressionAttributeValues={



                ":receipt_s3_key":

                    receipt_result[

                        "receipt_s3_key"

                    ],



                ":receipt_s3_url":

                    receipt_result[

                        "receipt_s3_url"

                    ],



                ":updated_at":

                    get_current_timestamp()

            }

        )



        # ------------------------------------------

        # Return Final Registration Information

        # ------------------------------------------



        return {



            "message":

                "Payment verified successfully",



            "registration_id":

                payment.registration_id,



            "status":

                "SUCCESS",



            "transaction_id":

                updated_registration.get(

                    "transaction_id"

                ),



            "receipt_number":

                updated_registration.get(

                    "receipt_number"

                ),



            "total_amount":

                float(

                    Decimal(

                        str(

                            updated_registration.get(

                                "total_amount",

                                "0"

                            )

                        )

                    )

                ),



            "razorpay_payment_id":

                payment.razorpay_payment_id,



            "receipt_s3_key":

                receipt_result[

                    "receipt_s3_key"

                ],



            "receipt_s3_url":

                receipt_result[

                    "receipt_s3_url"

                ],

        }



    except HTTPException:

        raise



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

                "Payment verification failed: "

                f"{str(error)}"

            )

        )
