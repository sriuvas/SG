
from fastapi import APIRouter, HTTPException, Depends
from botocore.exceptions import ClientError

from app.models.goshala import GoshalaCreate, GoshalaUpdate
from app.auth.dependencies import require_admin

from database import dynamodb

import uuid
from datetime import datetime, timezone


router = APIRouter(
    prefix="/api/goshala",
    tags=["Goshala"]
)


# ==================================================
# DynamoDB Table
# ==================================================

TABLE_NAME = "Goshala_Table"

table = dynamodb.Table(TABLE_NAME)


# ==================================================
# GET - Get Goshala information
# PUBLIC: No login required
# ==================================================

@router.get("")
def get_goshala():

    try:
        response = table.scan()
        items = response.get("Items", [])

        # Handle DynamoDB pagination
        while "LastEvaluatedKey" in response:
            response = table.scan(
                ExclusiveStartKey=response["LastEvaluatedKey"]
            )
            items.extend(response.get("Items", []))

        return {
            "message": "Goshala retrieved successfully",
            "goshala": items
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
# POST - Create Goshala information
# ADMIN ONLY
# ==================================================

@router.post("")
def create_goshala(
    goshala: GoshalaCreate,
    current_user: dict = Depends(require_admin)
):

    try:
        goshala_id = str(uuid.uuid4())

        current_time = datetime.now(
            timezone.utc
        ).isoformat()

        item = {
            "goshala_id": goshala_id,
            **goshala.model_dump(),
            "created_at": current_time,
            "updated_at": current_time
        }

        table.put_item(
            Item=item
        )

        return {
            "message": "Goshala created successfully",
            "goshala": item
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
# PUT - Update Goshala information
# ADMIN ONLY
# ==================================================

@router.put("/{goshala_id}")
def update_goshala(
    goshala_id: str,
    goshala: GoshalaUpdate,
    current_user: dict = Depends(require_admin)
):

    goshala_id = goshala_id.strip()

    try:
        response = table.get_item(
            Key={
                "goshala_id": goshala_id
            }
        )

        if "Item" not in response:
            raise HTTPException(
                status_code=404,
                detail=(
                    "Goshala not found for "
                    f"goshala_id: {goshala_id}"
                )
            )

        update_data = goshala.model_dump(
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
                "goshala_id": goshala_id
            },
            UpdateExpression=(
                "SET " + ", ".join(expression_parts)
            ),
            ExpressionAttributeNames=expression_names,
            ExpressionAttributeValues=expression_values
        )

        updated_response = table.get_item(
            Key={
                "goshala_id": goshala_id
            }
        )

        return {
            "message": "Goshala updated successfully",
            "goshala": updated_response.get("Item")
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
# DELETE - Delete Goshala information
# ADMIN ONLY
# ==================================================

@router.delete("/{goshala_id}")
def delete_goshala(
    goshala_id: str,
    current_user: dict = Depends(require_admin)
):

    goshala_id = goshala_id.strip()

    try:
        response = table.get_item(
            Key={
                "goshala_id": goshala_id
            }
        )

        if "Item" not in response:
            raise HTTPException(
                status_code=404,
                detail=(
                    "Goshala not found for "
                    f"goshala_id: {goshala_id}"
                )
            )

        table.delete_item(
            Key={
                "goshala_id": goshala_id
            }
        )

        return {
            "message": "Goshala deleted successfully",
            "goshala_id": goshala_id
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
