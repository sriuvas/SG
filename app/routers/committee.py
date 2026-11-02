
from fastapi import APIRouter, HTTPException, Depends
from botocore.exceptions import ClientError

from app.models.committee import CommitteeCreate, CommitteeUpdate
from app.auth.auth import require_admin
from database import dynamodb

import os
import uuid
from datetime import datetime, timezone


# ==================================================
# Router
# ==================================================

router = APIRouter(
    prefix="/api/committee",
    tags=["Committee"]
)


# ==================================================
# DynamoDB Table
# ==================================================

TABLE_NAME = os.getenv(
    "COMMITTEE_TABLE_NAME",
    "Committee_Table"
)

table = dynamodb.Table(TABLE_NAME)


# ==================================================
# GET - Get all committee members
# PUBLIC: Login is not required
# ==================================================

@router.get("")
def get_committee():

    try:
        response = table.scan()

        # Retrieve all committee members across scan pages.
        committee_members = response.get("Items", [])

        while "LastEvaluatedKey" in response:
            response = table.scan(
                ExclusiveStartKey=response["LastEvaluatedKey"]
            )
            committee_members.extend(
                response.get("Items", [])
            )

        return {
            "message": "Committee members retrieved successfully",
            "committee": committee_members
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
# POST - Create committee member
# ADMIN ONLY
# ==================================================

@router.post("")
def create_committee(
    member: CommitteeCreate,
    current_user: dict = Depends(require_admin)
):

    try:
        member_id = str(uuid.uuid4())

        current_time = datetime.now(
            timezone.utc
        ).isoformat()

        item = {
            "member_id": member_id,
            **member.model_dump(),
            "created_at": current_time,
            "updated_at": current_time
        }

        table.put_item(
            Item=item
        )

        return {
            "message": "Committee member created successfully",
            "committee_member": item
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
# PUT - Update committee member
# ADMIN ONLY
# ==================================================

@router.put("/{member_id}")
def update_committee(
    member_id: str,
    member: CommitteeUpdate,
    current_user: dict = Depends(require_admin)
):

    member_id = member_id.strip()

    try:
        response = table.get_item(
            Key={
                "member_id": member_id
            }
        )

        if "Item" not in response:
            raise HTTPException(
                status_code=404,
                detail="Committee member not found"
            )

        update_data = member.model_dump(
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
            name = f"#field{index}"
            value_name = f":value{index}"

            expression_parts.append(
                f"{name} = {value_name}"
            )

            expression_names[name] = key
            expression_values[value_name] = value

        table.update_item(
            Key={
                "member_id": member_id
            },
            UpdateExpression=(
                "SET " + ", ".join(expression_parts)
            ),
            ExpressionAttributeNames=expression_names,
            ExpressionAttributeValues=expression_values
        )

        updated_response = table.get_item(
            Key={
                "member_id": member_id
            }
        )

        return {
            "message": "Committee member updated successfully",
            "committee_member": updated_response.get("Item")
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
# DELETE - Delete committee member
# ADMIN ONLY
# ==================================================

@router.delete("/{member_id}")
def delete_committee(
    member_id: str,
    current_user: dict = Depends(require_admin)
):

    member_id = member_id.strip()

    try:
        response = table.get_item(
            Key={
                "member_id": member_id
            }
        )

        if "Item" not in response:
            raise HTTPException(
                status_code=404,
                detail="Committee member not found"
            )

        table.delete_item(
            Key={
                "member_id": member_id
            }
        )

        return {
            "message": "Committee member deleted successfully",
            "member_id": member_id
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
