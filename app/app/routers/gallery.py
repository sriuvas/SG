
from fastapi import APIRouter, HTTPException, Depends
from botocore.exceptions import ClientError

from app.models.gallery import GalleryCreate, GalleryUpdate
from app.auth.dependencies import require_admin

from database import dynamodb

import uuid
from datetime import datetime, timezone


router = APIRouter(
    prefix="/api/gallery",
    tags=["Gallery"]
)


# ==================================================
# DynamoDB Table
# ==================================================

TABLE_NAME = "Gallery_Table"

table = dynamodb.Table(TABLE_NAME)


# ==================================================
# Clean media URLs
# ==================================================

def clean_media_url(url: str | None) -> str | None:
    if not url or not isinstance(url, str):
        return url

    trimmed = url.strip()

    if "images1245" in trimmed:
        clean = trimmed.split("?")[0]
        clean = clean.replace(
            "images1245.s3.amazonaws.com",
            "images1245.s3.eu-north-1.amazonaws.com"
        )
        return clean

    if "X-Amz-Algorithm" in trimmed and "s3" in trimmed:
        return trimmed.split("?")[0]

    return trimmed


# ==================================================
# GET - Get all gallery images
# PUBLIC: No login required
# ==================================================

@router.get("")
def get_gallery():

    try:
        response = table.scan()
        items = response.get("Items", [])

        # Handle DynamoDB pagination
        while "LastEvaluatedKey" in response:
            response = table.scan(
                ExclusiveStartKey=response["LastEvaluatedKey"]
            )
            items.extend(response.get("Items", []))

        for item in items:
            if "image_url" in item:
                item["image_url"] = clean_media_url(
                    item["image_url"]
                )

        return {
            "message": "Gallery retrieved successfully",
            "gallery": items
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
# POST - Create gallery image
# ADMIN ONLY
# ==================================================

@router.post("")
def create_gallery(
    gallery: GalleryCreate,
    current_user: dict = Depends(require_admin)
):

    try:
        image_id = str(uuid.uuid4())

        current_time = datetime.now(
            timezone.utc
        ).isoformat()

        data = gallery.model_dump()

        if "image_url" in data:
            data["image_url"] = clean_media_url(
                data["image_url"]
            )

        item = {
            "image_id": image_id,
            **data,
            "created_at": current_time,
            "updated_at": current_time
        }

        table.put_item(Item=item)

        return {
            "message": "Gallery image created successfully",
            "gallery": item
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
# PUT - Update gallery image
# ADMIN ONLY
# ==================================================

@router.put("/{image_id}")
def update_gallery(
    image_id: str,
    gallery: GalleryUpdate,
    current_user: dict = Depends(require_admin)
):

    image_id = image_id.strip()

    try:
        response = table.get_item(
            Key={"image_id": image_id}
        )

        if "Item" not in response:
            raise HTTPException(
                status_code=404,
                detail=(
                    "Gallery image not found for "
                    f"image_id: {image_id}"
                )
            )

        update_data = gallery.model_dump(
            exclude_unset=True
        )

        if not update_data:
            raise HTTPException(
                status_code=400,
                detail="No fields provided for update"
            )

        if "image_url" in update_data:
            update_data["image_url"] = clean_media_url(
                update_data["image_url"]
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
            Key={"image_id": image_id},
            UpdateExpression=(
                "SET " + ", ".join(expression_parts)
            ),
            ExpressionAttributeNames=expression_names,
            ExpressionAttributeValues=expression_values
        )

        updated_response = table.get_item(
            Key={"image_id": image_id}
        )

        updated_item = updated_response.get("Item")

        if updated_item and "image_url" in updated_item:
            updated_item["image_url"] = clean_media_url(
                updated_item["image_url"]
            )

        return {
            "message": "Gallery image updated successfully",
            "gallery": updated_item
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
# DELETE - Delete gallery image
# ADMIN ONLY
# ==================================================

@router.delete("/{image_id}")
def delete_gallery(
    image_id: str,
    current_user: dict = Depends(require_admin)
):

    image_id = image_id.strip()

    try:
        response = table.get_item(
            Key={"image_id": image_id}
        )

        if "Item" not in response:
            raise HTTPException(
                status_code=404,
                detail=(
                    "Gallery image not found for "
                    f"image_id: {image_id}"
                )
            )

        table.delete_item(
            Key={"image_id": image_id}
        )

        return {
            "message": "Gallery image deleted successfully",
            "image_id": image_id
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
