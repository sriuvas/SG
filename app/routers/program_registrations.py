from fastapi import APIRouter, HTTPException, Depends, Query

from botocore.exceptions import ClientError

from boto3.dynamodb.conditions import Key, Attr

from decimal import Decimal



import os

import uuid



from datetime import datetime, timezone

from pathlib import Path



from app.models.program_registration import (

    ProgramRegistrationCreate,

    ProgramRegistrationPaymentVerify

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

    generate_program_receipt_pdf,

    upload_receipt_to_s3,

    generate_receipt_presigned_url

)



from database import dynamodb





# ==================================================

# Router

# ==================================================



router = APIRouter(

    prefix="/api/program-registrations",

    tags=["Program Registrations"]

)





# ==================================================

# DynamoDB Tables

# ==================================================



PROGRAMS_TABLE_NAME = os.getenv(

    "PROGRAMS_TABLE_NAME",

    "Programs_table"

)



REGISTRATIONS_TABLE_NAME = os.getenv(

    "PROGRAM_REGISTRATIONS_TABLE_NAME",

    "Program_Registrations_Table"

)



programs_table = dynamodb.Table(

    PROGRAMS_TABLE_NAME

)



registrations_table = dynamodb.Table(

    REGISTRATIONS_TABLE_NAME

)





# ==================================================

# Receipt Directory

# ==================================================

#

# AWS Lambda's /var/task directory is read-only.

# /tmp is the writable temporary directory.

#

# Locally this will also work correctly.

# ==================================================



RECEIPTS_DIRECTORY = Path(

    "/tmp/generated_receipts"

)



RECEIPTS_DIRECTORY.mkdir(

    parents=True,

    exist_ok=True

)





# ==================================================

# Helper - Generate Transaction ID

# ==================================================



def generate_transaction_id():



    token = uuid.uuid4().hex[:12].upper()



    return f"TXN-EVT-{token}"





# ==================================================

# Helper - Generate Receipt Number

# ==================================================



def get_current_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def generate_receipt_number():
    token = uuid.uuid4().hex[:12].upper()
    return f"RCP-PRG-{token}"






# ==================================================

# Helper - Generate Local PDF Receipt

# ==================================================



def generate_local_receipt(

    registration: dict

):



    pdf_bytes = generate_program_receipt_pdf(

        registration

    )



    receipt_number = str(

        registration.get(

            "receipt_number",

            uuid.uuid4().hex

        )

    )



    safe_receipt_number = (
        receipt_number
        .replace("/", "_")
        .replace("\\", "_")
    )



    receipt_file = (

        RECEIPTS_DIRECTORY

        / f"{safe_receipt_number}.pdf"

    )



    with open(

        receipt_file,

        "wb"

    ) as file:



        file.write(pdf_bytes)



    return str(receipt_file)





# ==================================================

# Helper - Generate PDF Bytes

# ==================================================



def generate_receipt_bytes(

    registration: dict

):



    return generate_program_receipt_pdf(

        registration

    )





# ==================================================

# Helper - Upload Receipt to S3

# ==================================================



def upload_registration_receipt(registration: dict):
    receipt_number = str(
        registration.get("receipt_number", "")
    ).strip()

    if not receipt_number:
        raise RuntimeError("Receipt number is missing")

    pdf_bytes = generate_receipt_bytes(registration)

    receipt_result = upload_receipt_to_s3(
        pdf_bytes=pdf_bytes,
        receipt_number=receipt_number,
    )

    if not isinstance(receipt_result, dict):
        raise RuntimeError(
            "Receipt upload returned an unexpected result"
        )

    receipt_s3_key = receipt_result.get("receipt_s3_key")
    receipt_s3_url = receipt_result.get("receipt_s3_url")

    if not receipt_s3_key or not receipt_s3_url:
        raise RuntimeError(
            "Receipt upload did not return a valid S3 key and URL"
        )

    return receipt_s3_key, receipt_s3_url


# ==================================================

# GET

# Admin - Get Program Registrations

#

# Supports:

# 1. Get all registrations

# 2. Filter by program_id

# 3. Filter by status

# 4. Filter by program_id + status

# ==================================================



@router.get("")

def get_program_registrations(

    program_id: str | None = Query(

        default=None,

        description="Filter registrations by program ID"

    ),

    status: str | None = Query(

        default=None,

        description="Filter by status: PENDING, SUCCESS, or FAILED"

    ),

    current_user: dict = Depends(require_admin)

):



    try:



        # ------------------------------------------

        # Clean filter values

        # ------------------------------------------



        if program_id:



            program_id = program_id.strip()



            if not program_id:

                program_id = None



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



        # ------------------------------------------

        # Query / Scan DynamoDB

        # ------------------------------------------



        registrations = []



        # ==================================================

        # Filter by program_id + status

        # ==================================================



        if program_id and status:



            response = registrations_table.query(

                IndexName="program_id-index",

                KeyConditionExpression=

                    Key("program_id").eq(program_id),

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

                    IndexName="program_id-index",

                    KeyConditionExpression=

                        Key("program_id").eq(program_id),

                    FilterExpression=

                        Attr("status").eq(status),

                    ExclusiveStartKey=

                        response["LastEvaluatedKey"]

                )



                registrations.extend(

                    response.get("Items", [])

                )



        # ==================================================

        # Filter by program_id only

        # ==================================================



        elif program_id:



            response = registrations_table.query(

                IndexName="program_id-index",

                KeyConditionExpression=

                    Key("program_id").eq(program_id)

            )



            registrations.extend(

                response.get("Items", [])

            )



            while response.get(

                "LastEvaluatedKey"

            ):



                response = registrations_table.query(

                    IndexName="program_id-index",

                    KeyConditionExpression=

                        Key("program_id").eq(program_id),

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

                "Program registrations retrieved successfully",



            "count":

                len(registrations),



            "filters": {

                "program_id":

                    program_id,



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

                "Failed to retrieve program registrations: "

                f"{str(error)}"

            )

        )





# ==================================================

# POST

# Create Program Registration / Razorpay Order

#

# User + Admin

# ==================================================




# ==================================================
# GET
# Logged-in User - Program Payment History
# ==================================================

@router.get("/my-history")
def get_my_program_payment_history(
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
        registrations.extend(response.get("Items", []))

        while response.get("LastEvaluatedKey"):
            response = registrations_table.query(
                IndexName="user_id-index",
                KeyConditionExpression=Key("user_id").eq(user_id),
                ScanIndexForward=False,
                ExclusiveStartKey=response["LastEvaluatedKey"]
            )
            registrations.extend(response.get("Items", []))

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
                and receipt_s3_key.strip().lower()
                not in {"", "receipt_s3_key", "receipt_s3_url", "none", "null"}
            )

            if has_valid_key:
                try:
                    presigned = generate_receipt_presigned_url(receipt_s3_key.strip())
                    registration["receipt_presigned_url"] = presigned
                    registration["receipt_url"] = presigned
                    registration["receipt_s3_url"] = presigned
                    registration["s3_url"] = presigned
                    registration["pdf_url"] = presigned
                except Exception as receipt_error:
                    print(
                        "Failed to generate program receipt URL:",
                        str(receipt_error)
                    )
            else:
                try:
                    receipt_number = registration.get("receipt_number") or generate_receipt_number()
                    registration["receipt_number"] = receipt_number
                    key, url = upload_registration_receipt(registration)
                    presigned = generate_receipt_presigned_url(key)
                    registration["receipt_s3_key"] = key
                    registration["receipt_s3_url"] = url
                    registration["receipt_presigned_url"] = presigned
                    registration["receipt_url"] = presigned
                    registration["s3_url"] = presigned
                    registration["pdf_url"] = presigned

                    registrations_table.update_item(
                        Key={"registration_id": registration["registration_id"]},
                        UpdateExpression="SET receipt_s3_key = :k, receipt_s3_url = :u, receipt_number = :r, updated_at = :upd",
                        ExpressionAttributeValues={
                            ":k": key,
                            ":u": url,
                            ":r": receipt_number,
                            ":upd": get_current_timestamp()
                        }
                    )
                except Exception as repair_err:
                    print("Auto-repair error for program receipt:", repair_err)

        return {
            "message": "Program payment history retrieved successfully",
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
                "Failed to retrieve program payment history: "
                f"{str(error)}"
            )
        )


# ==================================================
# GET
# Logged-in User - Single Program Registration Receipt
# ==================================================

@router.get("/{registration_id}/receipt")
def get_program_registration_receipt(
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
                detail="Program registration not found"
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
            key, url = upload_registration_receipt(registration)
            presigned_url = generate_receipt_presigned_url(key)

            registrations_table.update_item(
                Key={"registration_id": registration_id},
                UpdateExpression="SET receipt_s3_key = :k, receipt_s3_url = :u, receipt_number = :r, updated_at = :upd",
                ExpressionAttributeValues={
                    ":k": key,
                    ":u": url,
                    ":r": receipt_number,
                    ":upd": get_current_timestamp()
                }
            )

        return {
            "message": "Program registration receipt retrieved successfully",
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
            detail=f"Failed to retrieve program receipt: {str(error)}"
        )


@router.post("/create-order")

def create_program_registration_order(

    registration: ProgramRegistrationCreate,

    current_user: dict = Depends(get_current_user)

):



    try:



        # ------------------------------------------

        # Get authenticated user

        # ------------------------------------------



        user_id = str(

            current_user["user_id"]

        )



        # ------------------------------------------

        # Get Program

        # ------------------------------------------



        program_id = (

            registration.program_id.strip()

        )



        program_response = programs_table.get_item(

            Key={

                "program_id":

                    program_id

            }

        )



        program = program_response.get(

            "Item"

        )



        if not program:



            raise HTTPException(

                status_code=404,

                detail=(

                    "Program not found for "

                    f"program_id: {program_id}"

                )

            )



        # ------------------------------------------

        # Get Admin-defined Program Price

        # ------------------------------------------



        program_price = program.get(

            "price",

            Decimal("0.00")

        )



        program_price = Decimal(

            str(program_price)

        )



        # ------------------------------------------

        # Validate Price

        # ------------------------------------------



        if program_price < Decimal("0.00"):



            raise HTTPException(

                status_code=500,

                detail=(

                    "Invalid program price configured "

                    "by administrator"

                )

            )



        # ------------------------------------------

        # Get Attendees

        # ------------------------------------------



        attendees_count = (

            registration.attendees_count

        )



        # ------------------------------------------

        # SERVER-SIDE TOTAL CALCULATION

        #

        # Never trust amount from frontend

        # ------------------------------------------



        total_amount = (

            program_price *

            Decimal(attendees_count)

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

            datetime.now(

                timezone.utc

            ).isoformat()

        )



        # ==================================================

        # FREE PROGRAM

        # ==================================================



        if program_price == Decimal("0.00"):



            item = {



                "registration_id":

                    registration_id,



                "program_id":

                    program_id,



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

                    attendees_count,



                "unit_price":

                    program_price,



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

                    current_time

            }



            registrations_table.put_item(

                Item=item

            )



            # ------------------------------------------

            # Generate Local PDF Receipt

            # ------------------------------------------



            receipt_file = (

                generate_local_receipt(

                    item

                )

            )



            # ------------------------------------------

            # Upload Receipt to S3

            # ------------------------------------------



            try:



                receipt_s3_key, receipt_s3_url = (

                    upload_registration_receipt(

                        item

                    )

                )



            except Exception as error:



                raise HTTPException(

                    status_code=500,

                    detail=(

                        "Free registration was created "

                        "successfully, but receipt upload "

                        f"to S3 failed: {str(error)}"

                    )

                )



            # ------------------------------------------

            # Save S3 Receipt Information

            # ------------------------------------------



            registrations_table.update_item(



                Key={

                    "registration_id":

                        registration_id

                },



                UpdateExpression=(

                    "SET receipt_s3_key = "

                    ":receipt_s3_key, "

                    "receipt_s3_url = "

                    ":receipt_s3_url, "

                    "updated_at = "

                    ":updated_at"

                ),



                ExpressionAttributeValues={



                    ":receipt_s3_key":

                        receipt_s3_key,



                    ":receipt_s3_url":

                        receipt_s3_url,



                    ":updated_at":

                        datetime.now(

                            timezone.utc

                        ).isoformat()

                }

            )



            # ------------------------------------------

            # Generate temporary viewing URL

            # ------------------------------------------



            try:



                receipt_view_url = (

                    generate_receipt_presigned_url(

                        receipt_s3_key

                    )

                )



            except Exception:



                receipt_view_url = None



            # ------------------------------------------

            # Return Free Registration

            # ------------------------------------------



            return {



                "message":

                    "Free program registration successful",



                "registration_id":

                    registration_id,



                "program_id":

                    program_id,



                "program_name":

                    program.get(

                        "program_name"

                    ),



                "attendees_count":

                    attendees_count,



                "unit_price":

                    0,



                "total_amount":

                    0,



                "status":

                    "SUCCESS",



                "transaction_id":

                    transaction_id,



                "receipt_number":

                    receipt_number,



                "receipt_file":

                    receipt_file,



                "receipt_s3_key":

                    receipt_s3_key,



                "receipt_s3_url":

                    receipt_s3_url,



                "receipt_view_url":

                    receipt_view_url,



                "razorpay_required":

                    False

            }



        # ==================================================

        # PAID PROGRAM

        # ==================================================



        amount_paise = int(

            total_amount *

            Decimal("100")

        )



        if amount_paise <= 0:



            raise HTTPException(

                status_code=400,

                detail="Invalid payment amount"

            )



        # ------------------------------------------

        # Create Razorpay Order

        # ------------------------------------------



        razorpay_order = (

            create_razorpay_order(

                amount_paise=amount_paise,

                receipt=receipt_number

            )

        )



        razorpay_order_id = (

            razorpay_order.get(

                "id"

            )

        )



        if not razorpay_order_id:



            raise HTTPException(

                status_code=500,

                detail=(

                    "Razorpay order ID was not "

                    "returned"

                )

            )



        # ------------------------------------------

        # Save PENDING Registration

        # ------------------------------------------



        item = {



            "registration_id":

                registration_id,



            "program_id":

                program_id,



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

                attendees_count,



            "unit_price":

                program_price,



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

                current_time

        }



        registrations_table.put_item(

            Item=item

        )



        # ------------------------------------------

        # Return Payment Information

        # ------------------------------------------



        return {



            "message":

                "Razorpay order created successfully",



            "registration_id":

                registration_id,



            "program_id":

                program_id,



            "program_name":

                program.get(

                    "program_name"

                ),



            "unit_price":

                float(program_price),



            "attendees_count":

                attendees_count,



            "total_amount":

                float(total_amount),



            "amount_paise":

                amount_paise,



            "currency":

                "INR",



            "razorpay_required":

                True,



            "razorpay_key_id":

                os.getenv(

                    "RAZORPAY_KEY_ID"

                ),



            "razorpay_order_id":

                razorpay_order_id,



            "transaction_id":

                transaction_id,



            "receipt_number":

                receipt_number,



            "status":

                "PENDING"

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

                "Payment order creation failed: "

                f"{str(error)}"

            )

        )





# ==================================================

# POST

# Verify Razorpay Payment

#

# User + Admin

# ==================================================



@router.post("/verify-payment")

def verify_program_payment(

    payment: ProgramRegistrationPaymentVerify,

    current_user: dict = Depends(get_current_user)

):



    try:



        # ------------------------------------------

        # Get authenticated user

        # ------------------------------------------



        user_id = str(

            current_user["user_id"]

        )



        # ------------------------------------------

        # Get Registration

        # ------------------------------------------



        registration_id = (

            payment.registration_id.strip()

        )



        response = registrations_table.get_item(

            Key={

                "registration_id":

                    registration_id

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

        # Security:

        # Registration must belong to user

        # ------------------------------------------



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

        # Prevent duplicate verification

        # ------------------------------------------



        if registration.get(

            "status"

        ) == "SUCCESS":



            raise HTTPException(

                status_code=400,

                detail=(

                    "Payment has already been "

                    "successfully verified"

                )

            )



        # ------------------------------------------

        # Compare Razorpay Order IDs

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

                    "Razorpay order ID does not "

                    "match the registration"

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

            # Signature verification failed

            # --------------------------------------



            failed_time = (

                datetime.now(

                    timezone.utc

                ).isoformat()

            )



            registrations_table.update_item(



                Key={

                    "registration_id":

                        registration_id

                },



                UpdateExpression=(

                    "SET #status = :status, "

                    "razorpay_payment_id = "

                    ":payment_id, "

                    "razorpay_signature = "

                    ":signature, "

                    "updated_at = :updated_at"

                ),



                ExpressionAttributeNames={

                    "#status":

                        "status"

                },



                ExpressionAttributeValues={



                    ":status":

                        "FAILED",



                    ":payment_id":

                        payment.razorpay_payment_id,



                    ":signature":

                        payment.razorpay_signature,



                    ":updated_at":

                        failed_time

                }

            )



            raise HTTPException(

                status_code=400,

                detail=(

                    "Payment signature verification "

                    "failed"

                )

            )



        # ==================================================

        # Signature Verified

        # ==================================================



        success_time = (

            datetime.now(

                timezone.utc

            ).isoformat()

        )



        # ------------------------------------------

        # Prepare receipt data

        # ------------------------------------------



        receipt_data = dict(

            registration

        )



        receipt_data[

            "status"

        ] = "SUCCESS"



        receipt_data[

            "razorpay_payment_id"

        ] = payment.razorpay_payment_id



        receipt_data[

            "razorpay_signature"

        ] = payment.razorpay_signature



        receipt_data[

            "updated_at"

        ] = success_time



        # ------------------------------------------

        # Update registration to SUCCESS

        # ------------------------------------------



        registrations_table.update_item(



            Key={

                "registration_id":

                    registration_id

            },



            UpdateExpression=(

                "SET #status = :status, "

                "razorpay_payment_id = "

                ":payment_id, "

                "razorpay_signature = "

                ":signature, "

                "updated_at = :updated_at"

            ),



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

                    success_time

            }

        )



        # ==================================================

        # Generate Local PDF Receipt

        # ==================================================



        receipt_file = (

            generate_local_receipt(

                receipt_data

            )

        )



        # ==================================================

        # Upload PDF Receipt to S3

        # ==================================================



        try:



            receipt_s3_key, receipt_s3_url = (

                upload_registration_receipt(

                    receipt_data

                )

            )



        except Exception as error:



            # ------------------------------------------

            # Payment is already SUCCESS.

            #

            # Do NOT change it back to FAILED.

            # ------------------------------------------



            raise HTTPException(

                status_code=500,

                detail=(

                    "Payment was verified successfully, "

                    "but receipt upload to S3 failed: "

                    f"{str(error)}"

                )

            )



        # ==================================================

        # Save S3 Information in DynamoDB

        # ==================================================



        registrations_table.update_item(



            Key={

                "registration_id":

                    registration_id

            },



            UpdateExpression=(

                "SET receipt_s3_key = "

                ":receipt_s3_key, "

                "receipt_s3_url = "

                ":receipt_s3_url, "

                "updated_at = "

                ":updated_at"

            ),



            ExpressionAttributeValues={



                ":receipt_s3_key":

                    receipt_s3_key,



                ":receipt_s3_url":

                    receipt_s3_url,



                ":updated_at":

                    datetime.now(

                        timezone.utc

                    ).isoformat()

            }

        )



        # ==================================================

        # Generate Temporary S3 View URL

        # ==================================================



        try:



            receipt_view_url = (

                generate_receipt_presigned_url(

                    receipt_s3_key

                )

            )



        except Exception:



            receipt_view_url = None



        # ==================================================

        # Return Successful Registration

        # ==================================================



        return {



            "message":

                "Payment verified successfully",



            "registration_id":

                registration_id,



            "program_id":

                registration.get(

                    "program_id"

                ),



            "transaction_id":

                registration.get(

                    "transaction_id"

                ),



            "receipt_number":

                registration.get(

                    "receipt_number"

                ),



            "razorpay_order_id":

                payment.razorpay_order_id,



            "razorpay_payment_id":

                payment.razorpay_payment_id,



            "status":

                "SUCCESS",



            "receipt_file":

                receipt_file,



            "receipt_s3_key":

                receipt_s3_key,



            "receipt_s3_url":

                receipt_s3_url,



            "receipt_view_url":

                receipt_view_url

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