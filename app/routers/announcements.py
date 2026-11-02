
import os
import uuid
import time
from datetime import datetime, timezone
from pathlib import Path

import boto3
from fastapi import (
    APIRouter,
    HTTPException,
    Depends,
    UploadFile,
    File,
    Form,
)
from botocore.exceptions import ClientError

from app.models.announcement import AnnouncementCreate, AnnouncementUpdate
from app.auth.dependencies import require_admin
from database import dynamodb


# ==================================================
# Router
# ==================================================

router = APIRouter(
    prefix="/api/announcements",
    tags=["Announcements"],
)


# ==================================================
# DynamoDB and S3 Configuration
# ==================================================

TABLE_NAME = os.getenv(
    "ANNOUNCEMENTS_TABLE_NAME",
    "Announcements_Table",
)

table = dynamodb.Table(TABLE_NAME)

S3_BUCKET_NAME = os.getenv(
    "MEDIA_S3_BUCKET_NAME",
    "images1245",
)

S3_REGION_NAME = os.getenv(
    "AWS_S3_REGION_NAME",
    "eu-north-1",
)

s3_client = boto3.client(
    "s3",
    region_name=S3_REGION_NAME,
)

ALLOWED_IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
}

MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB


def build_permanent_s3_url(object_key: str) -> str:
    """Build the S3 URL used to store the announcement photo reference."""
    return (
        f"https://{S3_BUCKET_NAME}.s3."
        f"{S3_REGION_NAME}.amazonaws.com/{object_key}"
    )


# ==================================================
# GET - Public announcements
# ==================================================

@router.get("")
def get_announcements():
    try:
        response = table.scan()
        announcements = response.get("Items", [])

        while "LastEvaluatedKey" in response:
            response = table.scan(
                ExclusiveStartKey=response["LastEvaluatedKey"]
            )
            announcements.extend(response.get("Items", []))

        # Keep published announcements visible on the public page.
        # Existing records without is_published default to published.
        published = [
            item for item in announcements
            if item.get("is_published", True) is True
        ]

        published.sort(
            key=lambda item: item.get("announcement_date", ""),
            reverse=True,
        )

        return {
            "message": "Announcements retrieved successfully",
            "announcements": published,
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
# GET - All announcements for Admin
# ==================================================

@router.get("/admin/all")
def get_all_announcements(
    current_user: dict = Depends(require_admin),
):
    try:
        response = table.scan()
        announcements = response.get("Items", [])

        while "LastEvaluatedKey" in response:
            response = table.scan(
                ExclusiveStartKey=response["LastEvaluatedKey"]
            )
            announcements.extend(response.get("Items", []))

        announcements.sort(
            key=lambda item: item.get("announcement_date", ""),
            reverse=True,
        )

        return {
            "message": "All announcements retrieved successfully",
            "announcements": announcements,
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
# POST - Upload announcement photo to S3
# ADMIN ONLY
# ==================================================

@router.post("/upload-photo")
def upload_announcement_photo(
    file: UploadFile = File(...),
    current_user: dict = Depends(require_admin),
):
    object_key = None

    try:
        original_filename = Path(file.filename or "").name
        extension = Path(original_filename).suffix.lower()

        if extension not in ALLOWED_IMAGE_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail="Only JPG, JPEG, PNG, and WEBP images are allowed.",
            )

        content_type = (file.content_type or "").lower()

        allowed_content_types = {
            ".jpg": {"image/jpeg"},
            ".jpeg": {"image/jpeg"},
            ".png": {"image/png"},
            ".webp": {"image/webp"},
        }

        if content_type not in allowed_content_types[extension]:
            raise HTTPException(
                status_code=400,
                detail="The uploaded file content type does not match its image extension.",
            )

        # Read at most 10 MB plus one byte to enforce the size limit.
        image_bytes = file.file.read(MAX_IMAGE_SIZE + 1)

        if not image_bytes:
            raise HTTPException(
                status_code=400,
                detail="The uploaded image is empty.",
            )

        if len(image_bytes) > MAX_IMAGE_SIZE:
            raise HTTPException(
                status_code=413,
                detail="Image size must not exceed 10 MB.",
            )

        # Create a unique filename to avoid overwriting existing photos.
        object_key = (
            f"announcements/{int(time.time())}_"
            f"{uuid.uuid4().hex}{extension}"
        )

        s3_client.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=object_key,
            Body=image_bytes,
            ContentType=content_type,
            Metadata={
                "original-filename": original_filename[:200],
            },
        )

        image_url = build_permanent_s3_url(object_key)

        return {
            "message": "Announcement photo uploaded successfully",
            "image_url": image_url,
            "s3_key": object_key,
        }

    except HTTPException:
        raise

    except ClientError as error:
        error_message = error.response.get(
            "Error", {}
        ).get("Message", "Unknown S3 error")

        raise HTTPException(
            status_code=500,
            detail=f"S3 upload failed: {error_message}",
        )

    finally:
        file.file.close()


# ==================================================
# POST - Create announcement
# ADMIN ONLY
# ==================================================

@router.post("")
def create_announcement(
    announcement: AnnouncementCreate,
    current_user: dict = Depends(require_admin),
):
    try:
        announcement_id = str(uuid.uuid4())
        current_time = datetime.now(timezone.utc).isoformat()

        item = {
            "announcement_id": announcement_id,
            **announcement.model_dump(),
            "created_at": current_time,
            "updated_at": current_time,
        }

        table.put_item(Item=item)

        return {
            "message": "Announcement created successfully",
            "announcement": item,
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
# PUT - Update announcement
# ADMIN ONLY
# ==================================================

@router.put("/{announcement_id}")
def update_announcement(
    announcement_id: str,
    announcement: AnnouncementUpdate,
    current_user: dict = Depends(require_admin),
):
    announcement_id = announcement_id.strip()

    try:
        response = table.get_item(
            Key={"announcement_id": announcement_id}
        )

        if "Item" not in response:
            raise HTTPException(
                status_code=404,
                detail=(
                    "Announcement not found for "
                    f"announcement_id: {announcement_id}"
                ),
            )

        update_data = announcement.model_dump(exclude_unset=True)

        if not update_data:
            raise HTTPException(
                status_code=400,
                detail="No fields provided for update",
            )

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
            Key={"announcement_id": announcement_id},
            UpdateExpression="SET " + ", ".join(expression_parts),
            ExpressionAttributeNames=expression_names,
            ExpressionAttributeValues=expression_values,
        )

        updated_response = table.get_item(
            Key={"announcement_id": announcement_id}
        )

        return {
            "message": "Announcement updated successfully",
            "announcement": updated_response.get("Item"),
        }

    except HTTPException:
        raise

    except ClientError as error:
        raise HTTPException(
            status_code=500,
            detail=(
                "DynamoDB error: "
                f"{error.response['Error']['Message']}"
            ),
        )


# ==================================================
# DELETE - Delete announcement
# ADMIN ONLY
# ==================================================

@router.delete("/{announcement_id}")
def delete_announcement(
    announcement_id: str,
    current_user: dict = Depends(require_admin),
):
    announcement_id = announcement_id.strip()

    try:
        response = table.delete_item(
            Key={"announcement_id": announcement_id},
            ReturnValues="ALL_OLD",
        )

        if "Attributes" not in response:
            raise HTTPException(
                status_code=404,
                detail=(
                    "Announcement not found for "
                    f"announcement_id: {announcement_id}"
                ),
            )

        return {
            "message": "Announcement deleted successfully",
            "announcement_id": announcement_id,
        }

    except HTTPException:
        raise

    except ClientError as error:
        raise HTTPException(
            status_code=500,
            detail=(
                "DynamoDB error: "
                f"{error.response['Error']['Message']}"
            ),
        )
