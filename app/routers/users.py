
import time
import uuid
from datetime import datetime, timezone

from boto3.dynamodb.conditions import Attr
from botocore.exceptions import ClientError
from fastapi import APIRouter, HTTPException, Depends
from passlib.context import CryptContext

from app.models.user import UserCreate, UserUpdate, ChangePasswordRequest
from app.auth.auth import get_current_user, require_admin
from database import dynamodb


router = APIRouter(
    prefix="/api/users",
    tags=["Users"]
)

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
)

TABLE_NAME = "Users_Table"
OTP_TABLE_NAME = "EmailOTP_Table"

table = dynamodb.Table(TABLE_NAME)
otp_table = dynamodb.Table(OTP_TABLE_NAME)


# ==================================================
# GET - Get all users
# Authenticated users
# ==================================================

@router.get("")
def get_users(
    current_user: dict = Depends(get_current_user)
):
    try:
        response = table.scan()
        users = response.get("Items", [])

        while response.get("LastEvaluatedKey"):
            response = table.scan(
                ExclusiveStartKey=response["LastEvaluatedKey"]
            )
            users.extend(response.get("Items", []))

        # Never expose password hashes.
        for user in users:
            user.pop("password_hash", None)

        return {
            "message": "Users retrieved successfully",
            "users": users
        }

    except ClientError as exc:
        print(
            "Get users error:",
            exc.response.get("Error", {}).get("Code", "Unknown")
        )
        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve users"
        )


# ==================================================
# GET - Get current user's profile
# Authenticated users
# ==================================================

@router.get("/me")
def get_my_profile(
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user.get("user_id")

    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="User ID not found in authentication token"
        )

    try:
        response = table.get_item(
            Key={"user_id": user_id}
        )

        user = response.get("Item")

        if not user:
            raise HTTPException(
                status_code=404,
                detail="User profile not found"
            )

        return {
            "message": "User profile retrieved successfully",
            "user": {
                "user_id": user.get("user_id"),
                "name": user.get("name"),
                "email": user.get("email"),
                "phone": user.get("phone"),
                "role": user.get("role")
            }
        }

    except HTTPException:
        raise

    except ClientError as exc:
        print(
            "Get profile error:",
            exc.response.get("Error", {}).get("Code", "Unknown")
        )
        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve user profile"
        )


# ==================================================
# POST - Register a user
# Requires verified email OTP.
# Public registration always assigns role "User".
# User creation and OTP consumption are atomic.
# ==================================================

@router.post("")
def create_user(
    user: UserCreate
):
    email = str(user.email).strip().lower()
    now = int(time.time())

    # 1. Retrieve the email verification record.
    try:
        otp_response = otp_table.get_item(
            Key={"email": email},
            ConsistentRead=True
        )
        otp_item = otp_response.get("Item")

    except ClientError as exc:
        print(
            "OTP lookup error:",
            exc.response.get("Error", {}).get("Code", "Unknown")
        )
        raise HTTPException(
            status_code=500,
            detail="Unable to check email verification"
        )

    if (
        not otp_item
        or otp_item.get("purpose") != "registration"
        or otp_item.get("verified") is not True
    ):
        raise HTTPException(
            status_code=403,
            detail="Please verify your email with OTP before registering"
        )

    try:
        verified_until = int(otp_item.get("verified_until", 0))
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=403,
            detail="Email verification is invalid. Please verify again"
        )

    if verified_until <= now:
        raise HTTPException(
            status_code=403,
            detail="Email verification expired. Please verify again"
        )

    # 2. Check whether the email is already registered.
    # The transaction below also prevents concurrent requests from
    # consuming the same OTP more than once.
    try:
        existing_users = []

        scan_response = table.scan(
            FilterExpression="#email = :email",
            ExpressionAttributeNames={
                "#email": "email"
            },
            ExpressionAttributeValues={
                ":email": email
            }
        )

        existing_users.extend(scan_response.get("Items", []))

        while scan_response.get("LastEvaluatedKey"):
            scan_response = table.scan(
                FilterExpression="#email = :email",
                ExpressionAttributeNames={
                    "#email": "email"
                },
                ExpressionAttributeValues={
                    ":email": email
                },
                ExclusiveStartKey=scan_response["LastEvaluatedKey"]
            )
            existing_users.extend(scan_response.get("Items", []))

        if existing_users:
            raise HTTPException(
                status_code=400,
                detail="User with this email already exists"
            )

    except HTTPException:
        raise

    except ClientError as exc:
        print(
            "Existing user lookup error:",
            exc.response.get("Error", {}).get("Code", "Unknown")
        )
        raise HTTPException(
            status_code=500,
            detail="Unable to check existing users"
        )

    # 3. Prepare the user record.
    user_id = str(uuid.uuid4())
    current_time = datetime.now(timezone.utc).isoformat()

    item = {
        "user_id": user_id,
        "name": user.name,
        "email": email,
        "phone": user.phone,
        "password_hash": pwd_context.hash(user.password),
        # Never trust the public request's role field.
        "role": "User",
        "created_at": current_time,
        "updated_at": current_time
    }

    # 4. Create the user using the DynamoDB resource API.
    # The resource API accepts normal Python values, avoiding manual
    # AttributeValue serialization for user_id.
    user_created = False

    try:
        table.put_item(
            Item=item,
            ConditionExpression=Attr("user_id").not_exists()
        )
        user_created = True

        # Consume the verified OTP only if it is still the registration OTP
        # and its verification window matches the one checked above.
        otp_table.delete_item(
            Key={"email": email},
            ConditionExpression=(
                Attr("purpose").eq("registration")
                & Attr("verified").eq(True)
                & Attr("verified_until").eq(verified_until)
            )
        )

    except ClientError as exc:
        error = exc.response.get("Error", {})
        error_code = error.get("Code", "")
        print("Registration database error code:", error_code)
        print("Registration database error message:", error.get("Message", ""))

        # If the OTP could not be consumed after inserting the user, roll back
        # the inserted user so an unverified/inconsistent registration is not
        # left behind. Only delete the record created by this request.
        if user_created:
            try:
                table.delete_item(
                    Key={"user_id": user_id},
                    ConditionExpression=Attr("email").eq(email)
                )
            except ClientError as rollback_exc:
                print(
                    "Registration rollback error:",
                    rollback_exc.response.get("Error", {}).get("Code", "Unknown")
                )

        if error_code in (
            "ConditionalCheckFailedException",
            "TransactionCanceledException"
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Registration could not be completed. "
                    "Please verify your email again and retry."
                )
            )

        raise HTTPException(
            status_code=500,
            detail="Unable to complete registration"
        )

    except (TypeError, ValueError) as exc:
        print("Registration data error:", str(exc))

        if user_created:
            try:
                table.delete_item(
                    Key={"user_id": user_id},
                    ConditionExpression=Attr("email").eq(email)
                )
            except ClientError as rollback_exc:
                print(
                    "Registration rollback error:",
                    rollback_exc.response.get("Error", {}).get("Code", "Unknown")
                )

        raise HTTPException(
            status_code=500,
            detail="Unable to prepare registration data"
        )

    # 6. Return the new user without its password hash.
    response_user = item.copy()
    response_user.pop("password_hash", None)

    return {
        "message": "User created successfully",
        "user": response_user
    }


# ==================================================
# POST - Change current user's password
# Authenticated users can change only their own password.
# ==================================================

@router.post("/change-password")
def change_password(
    request: ChangePasswordRequest,
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user.get("user_id")

    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="User ID not found in authentication token"
        )

    old_password = request.old_password.get_secret_value()
    new_password = request.new_password.get_secret_value()

    try:
        # Resolve the user only from the authenticated access token.
        response = table.get_item(
            Key={"user_id": user_id},
            ConsistentRead=True
        )
        user = response.get("Item")

        if not user:
            raise HTTPException(
                status_code=404,
                detail="User profile not found"
            )

        stored_password_hash = user.get("password_hash")
        if not stored_password_hash:
            raise HTTPException(
                status_code=400,
                detail="Password change is unavailable for this account"
            )

        if not pwd_context.verify(old_password, stored_password_hash):
            raise HTTPException(
                status_code=400,
                detail="Current password is incorrect"
            )

        if old_password == new_password:
            # Also validated by ChangePasswordRequest; keep this check here
            # as a defense-in-depth safeguard.
            raise HTTPException(
                status_code=400,
                detail="New password must be different from old password"
            )

        new_password_hash = pwd_context.hash(new_password)
        updated_at = datetime.now(timezone.utc).isoformat()

        # Prevent overwriting a password that another request changed after
        # this request read the account. Never store plaintext passwords.
        table.update_item(
            Key={"user_id": user_id},
            UpdateExpression="SET #password_hash = :new_hash, #updated_at = :updated_at",
            ConditionExpression=Attr("password_hash").eq(stored_password_hash),
            ExpressionAttributeNames={
                "#password_hash": "password_hash",
                "#updated_at": "updated_at"
            },
            ExpressionAttributeValues={
                ":new_hash": new_password_hash,
                ":updated_at": updated_at
            }
        )

        return {"message": "Password changed successfully"}

    except HTTPException:
        raise

    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "Unknown")
        print("Change password database error code:", error_code)

        if error_code == "ConditionalCheckFailedException":
            raise HTTPException(
                status_code=409,
                detail="Password was changed by another request. Please retry."
            )

        raise HTTPException(
            status_code=500,
            detail="Unable to change password"
        )


# ==================================================
# PUT - Update a user
# Admin only
# ==================================================

@router.put("/{user_id}")
def update_user(
    user_id: str,
    user: UserUpdate,
    current_user: dict = Depends(require_admin)
):
    user_id = user_id.strip()

    try:
        response = table.get_item(
            Key={"user_id": user_id}
        )

        if "Item" not in response:
            raise HTTPException(
                status_code=404,
                detail=f"User not found for user_id: {user_id}"
            )

        update_data = user.model_dump(
            exclude_unset=True
        )

        if not update_data:
            raise HTTPException(
                status_code=400,
                detail="No fields provided for update"
            )

        # Hash a new password if supplied.
        if "password" in update_data:
            update_data["password_hash"] = pwd_context.hash(
                update_data.pop("password")
            )

        # Update timestamp.
        update_data["updated_at"] = datetime.now(
            timezone.utc
        ).isoformat()

        expression_parts = []
        expression_values = {}
        expression_names = {}

        for index, (key, value) in enumerate(update_data.items()):
            field_name = f"#field{index}"
            value_name = f":value{index}"

            expression_parts.append(
                f"{field_name} = {value_name}"
            )
            expression_names[field_name] = key
            expression_values[value_name] = value

        table.update_item(
            Key={"user_id": user_id},
            UpdateExpression="SET " + ", ".join(expression_parts),
            ExpressionAttributeNames=expression_names,
            ExpressionAttributeValues=expression_values
        )

        updated_response = table.get_item(
            Key={"user_id": user_id}
        )

        updated_user = updated_response.get("Item", {})
        updated_user.pop("password_hash", None)

        return {
            "message": "User updated successfully",
            "user": updated_user
        }

    except HTTPException:
        raise

    except ClientError as exc:
        print(
            "Update user error:",
            exc.response.get("Error", {}).get("Code", "Unknown")
        )
        raise HTTPException(
            status_code=500,
            detail="Unable to update user"
        )


# ==================================================
# DELETE - Delete a user
# Admin only
# ==================================================

@router.delete("/{user_id}")
def delete_user(
    user_id: str,
    current_user: dict = Depends(require_admin)
):
    user_id = user_id.strip()

    try:
        response = table.delete_item(
            Key={"user_id": user_id},
            ReturnValues="ALL_OLD"
        )

        if "Attributes" not in response:
            raise HTTPException(
                status_code=404,
                detail=f"User not found for user_id: {user_id}"
            )

        return {
            "message": "User deleted successfully",
            "user_id": user_id
        }

    except HTTPException:
        raise

    except ClientError as exc:
        print(
            "Delete user error:",
            exc.response.get("Error", {}).get("Code", "Unknown")
        )
        raise HTTPException(
            status_code=500,
            detail="Unable to delete user"
        )
