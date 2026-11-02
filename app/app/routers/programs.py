
from fastapi import APIRouter, HTTPException, Depends
from botocore.exceptions import ClientError

from app.models.program import ProgramCreate, ProgramUpdate
from app.auth.dependencies import require_admin
from database import dynamodb

import os
import uuid

from datetime import datetime, timezone


# ==================================================
# Router
# ==================================================

router = APIRouter(
    prefix="/api/programs",
    tags=["Programs"]
)


# ==================================================
# DynamoDB Table
# ==================================================

TABLE_NAME = os.getenv(
    "PROGRAMS_TABLE_NAME",
    "Programs_table"
)

table = dynamodb.Table(TABLE_NAME)


# ==================================================
# GET - Get all programs
# PUBLIC: Login is not required
# ==================================================

@router.get("")
def get_programs():

    try:
        response = table.scan()

        # Retrieve all programs, including records beyond
        # DynamoDB's first scan page.
        programs = response.get("Items", [])

        while "LastEvaluatedKey" in response:
            response = table.scan(
                ExclusiveStartKey=response["LastEvaluatedKey"]
            )
            programs.extend(response.get("Items", []))

        return {
            "message": "Programs retrieved successfully",
            "programs": programs
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
# POST - Create a new program
# ADMIN ONLY
# ==================================================

@router.post("")
def create_program(
    program: ProgramCreate,
    current_user: dict = Depends(require_admin)
):

    try:
        program_id = str(uuid.uuid4())

        current_time = datetime.now(
            timezone.utc
        ).isoformat()

        item = {
            "program_id": program_id,
            **program.model_dump(),
            "created_at": current_time,
            "updated_at": current_time
        }

        table.put_item(
            Item=item
        )

        return {
            "message": "Program created successfully",
            "program": item
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
# PUT - Update a program
# ADMIN ONLY
# ==================================================

@router.put("/{program_id}")
def update_program(
    program_id: str,
    program: ProgramUpdate,
    current_user: dict = Depends(require_admin)
):

    program_id = program_id.strip()

    try:
        response = table.get_item(
            Key={
                "program_id": program_id
            }
        )

        if "Item" not in response:
            raise HTTPException(
                status_code=404,
                detail=(
                    "Program not found for "
                    f"program_id: {program_id}"
                )
            )

        update_data = program.model_dump(
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
                "program_id": program_id
            },
            UpdateExpression=(
                "SET " + ", ".join(expression_parts)
            ),
            ExpressionAttributeNames=expression_names,
            ExpressionAttributeValues=expression_values
        )

        updated_response = table.get_item(
            Key={
                "program_id": program_id
            }
        )

        return {
            "message": "Program updated successfully",
            "program": updated_response.get("Item")
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
# DELETE - Delete a program
# ADMIN ONLY
# ==================================================

@router.delete("/{program_id}")
def delete_program(
    program_id: str,
    current_user: dict = Depends(require_admin)
):

    program_id = program_id.strip()

    try:
        response = table.get_item(
            Key={
                "program_id": program_id
            }
        )

        if "Item" not in response:
            raise HTTPException(
                status_code=404,
                detail=(
                    "Program not found for "
                    f"program_id: {program_id}"
                )
            )

        table.delete_item(
            Key={
                "program_id": program_id
            }
        )

        return {
            "message": "Program deleted successfully",
            "program_id": program_id
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
