
from fastapi import APIRouter, HTTPException, Depends
from app.models.user import UserCreate, UserUpdate
from app.auth.auth import get_current_user, require_admin
from database import dynamodb
from passlib.context import CryptContext
from botocore.exceptions import ClientError
import uuid
from datetime import datetime, timezone


router = APIRouter(
    prefix="/api/users",
    tags=["Users"]
)


# ==================================================
# Password Hashing
# ==================================================

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
)


# ==================================================
# DynamoDB Table
# ==================================================

TABLE_NAME = "Users_Table"

table = dynamodb.Table(TABLE_NAME)


# ==================================================
# GET - Get all users
# Authenticated users can access
# ==================================================

@router.get("")
def get_users(
    current_user: dict = Depends(get_current_user)
):
    try:
        response = table.scan()
        users = response.get("Items", [])

        # Retrieve all pages from DynamoDB.
        while response.get("LastEvaluatedKey"):
            response = table.scan(
                ExclusiveStartKey=response["LastEvaluatedKey"]
            )
            users.extend(response.get("Items", []))

        # Never return password hashes.
        for user in users:
            user.pop("password_hash", None)

        return {
            "message": "Users retrieved successfully",
            "users": users
        }

    except ClientError:
        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve users"
        )


# ==================================================
# GET - Get current logged-in user's profile
# Authenticated users can access their own profile
# ==================================================

@router.get("/me")
def get_my_profile(
    current_user: dict = Depends(get_current_user)
):
    # Get the user ID from the authenticated token context.
    user_id = current_user.get("user_id")

    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="User ID not found in authentication token"
        )

    try:
        response = table.get_item(
            Key={
                "user_id": user_id
            }
        )

        user = response.get("Item")

        if not user:
            raise HTTPException(
                status_code=404,
                detail="User profile not found"
            )

        # Return only the required profile fields.
        # Never expose password_hash.
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

    except ClientError:
        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve user profile"
        )


# ==================================================
# POST - Create a user
# Public - No authentication required
# ==================================================

@router.post("")
def create_user(
    user: UserCreate
):
    try:
        # Check whether email already exists.
        response = table.scan(
            FilterExpression="#email = :email",
            ExpressionAttributeNames={
                "#email": "email"
            },
            ExpressionAttributeValues={
                ":email": user.email
            }
        )

        if response.get("Items"):
            raise HTTPException(
                status_code=400,
                detail="User with this email already exists"
            )

        # Generate user ID.
        user_id = str(uuid.uuid4())

        current_time = datetime.now(
            timezone.utc
        ).isoformat()

        # Hash password.
        password_hash = pwd_context.hash(
            user.password
        )

        item = {
            "user_id": user_id,
            "name": user.name,
            "email": user.email,
            "phone": user.phone,
            "password_hash": password_hash,
            "role": user.role,
            "created_at": current_time,
            "updated_at": current_time
        }

        table.put_item(
            Item=item
        )

        # Do not return password hash.
        response_user = item.copy()
        response_user.pop("password_hash", None)

        return {
            "message": "User created successfully",
            "user": response_user
        }

    except HTTPException:
        raise

    except ClientError:
        raise HTTPException(
            status_code=500,
            detail="Unable to create user"
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
        # Check whether user exists.
        response = table.get_item(
            Key={
                "user_id": user_id
            }
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
                update_data["password"]
            )
            del update_data["password"]

        # Update timestamp.
        update_data["updated_at"] = datetime.now(
            timezone.utc
        ).isoformat()

        expression_parts = []
        expression_values = {}
        expression_names = {}

        for index, (key, value) in enumerate(
            update_data.items()
        ):
            field_name = f"#field{index}"
            value_name = f":value{index}"

            expression_parts.append(
                f"{field_name} = {value_name}"
            )

            expression_names[field_name] = key
            expression_values[value_name] = value

        table.update_item(
            Key={
                "user_id": user_id
            },
            UpdateExpression="SET " + ", ".join(
                expression_parts
            ),
            ExpressionAttributeNames=expression_names,
            ExpressionAttributeValues=expression_values
        )

        # Get updated user.
        updated_response = table.get_item(
            Key={
                "user_id": user_id
            }
        )

        updated_user = updated_response.get(
            "Item",
            {}
        )

        # Never return password hash.
        updated_user.pop("password_hash", None)

        return {
            "message": "User updated successfully",
            "user": updated_user
        }

    except HTTPException:
        raise

    except ClientError:
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
            Key={
                "user_id": user_id
            },
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

    except ClientError:
        raise HTTPException(
            status_code=500,
            detail="Unable to delete user"
        )
