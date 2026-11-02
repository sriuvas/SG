
from fastapi import APIRouter, HTTPException, Depends
from botocore.exceptions import ClientError

from app.models.announcement import AnnouncementCreate, AnnouncementUpdate
from app.auth.dependencies import require_admin
from database import dynamodb

import os
import uuid
from datetime import datetime, timezone


# ==================================================
# Router
# ==================================================

router = APIRouter(
    prefix="/api/announcements",
    tags=["Announcements"]
)


# ==================================================
# DynamoDB Table
# ==================================================

TABLE_NAME = os.getenv(
    "ANNOUNCEMENTS_TABLE_NAME",
    "Announcements_Table"
)

table = dynamodb.Table(TABLE_NAME)


# ==================================================
# GET - Get all announcements
# PUBLIC: Login is not required
# ==================================================

@router.get("")
def get_announcements():

    try:
        response = table.scan()

        # Retrieve announcements across all scan pages.
        announcements = response.get("Items", [])

        while "LastEvaluatedKey" in response:
            response = table.scan(
                ExclusiveStartKey=response["LastEvaluatedKey"]
            )
            announcements.extend(
                response.get("Items", [])
            )

        return {
            "message": "Announcements retrieved successfully",
            "announcements": announcements
        }

    except ClientError as error:
        raise HTTPException(
            status_code=500,
            detail=(
                "DynamoDB error: "
                f"{error.response['Error']['Message']}"
            )
        )


# ==================================================
# POST - Create announcement
# ADMIN ONLY
# ==================================================

@router.post("")
def create_announcement(
    announcement: AnnouncementCreate,
    current_user: dict = Depends(require_admin)
):

    try:
        announcement_id = str(uuid.uuid4())

        current_time = datetime.now(
            timezone.utc
        ).isoformat()

        item = {
            "announcement_id": announcement_id,
            **announcement.model_dump(),
            "created_at": current_time,
            "updated_at": current_time
        }

        table.put_item(
            Item=item
        )

        return {
            "message": "Announcement created successfully",
            "announcement": item
        }

    except ClientError as error:
        raise HTTPException(
            status_code=500,
            detail=(
                "DynamoDB error: "
                f"{error.response['Error']['Message']}"
            )
        )


# ==================================================
# PUT - Update announcement
# ADMIN ONLY
# ==================================================

@router.put("/{announcement_id}")
def update_announcement(
    announcement_id: str,
    announcement: AnnouncementUpdate,
    current_user: dict = Depends(require_admin)
):

    announcement_id = announcement_id.strip()

    try:
        response = table.get_item(
            Key={
                "announcement_id": announcement_id
            }
        )

        if "Item" not in response:
            raise HTTPException(
                status_code=404,
                detail=(
                    "Announcement not found for "
                    f"announcement_id: {announcement_id}"
                )
            )

        update_data = announcement.model_dump(
            exclude_unset=True
        )

        if not update_data:
            raise HTTPException(
                status_code=400,
                detail="No fields provided for update"
            )

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
                "announcement_id": announcement_id
            },
            UpdateExpression="SET " + ", ".join(
                expression_parts
            ),
            ExpressionAttributeNames=expression_names,
            ExpressionAttributeValues=expression_values
        )

        updated_response = table.get_item(
            Key={
                "announcement_id": announcement_id
            }
        )

        return {
            "message": "Announcement updated successfully",
            "announcement": updated_response.get("Item")
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


# ==================================================
# DELETE - Delete announcement
# ADMIN ONLY
# ==================================================

@router.delete("/{announcement_id}")
def delete_announcement(
    announcement_id: str,
    current_user: dict = Depends(require_admin)
):

    announcement_id = announcement_id.strip()

    try:
        response = table.delete_item(
            Key={
                "announcement_id": announcement_id
            },
            ReturnValues="ALL_OLD"
        )

        if "Attributes" not in response:
            raise HTTPException(
                status_code=404,
                detail=(
                    "Announcement not found for "
                    f"announcement_id: {announcement_id}"
                )
            )

        return {
            "message": "Announcement deleted successfully",
            "announcement_id": announcement_id
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
