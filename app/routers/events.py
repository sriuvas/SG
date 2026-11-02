from fastapi import APIRouter, HTTPException, Depends
from botocore.exceptions import ClientError

from app.models.event import EventCreate, EventUpdate
from app.auth.dependencies import require_admin
from database import dynamodb

import os
import uuid

from datetime import datetime, timezone


# ==================================================
# Router
# ==================================================

router = APIRouter(
    prefix="/api/events",
    tags=["Events"]
)


# ==================================================
# DynamoDB Table
# ==================================================

TABLE_NAME = os.getenv(
    "EVENTS_TABLE_NAME",
    "Events_table"
)

table = dynamodb.Table(TABLE_NAME)


# ==================================================
# GET - Get all events
# PUBLIC: Login is not required
# ==================================================

@router.get("")
def get_events():

    try:
        response = table.scan()
        events = response.get("Items", [])

        # Retrieve all records across DynamoDB scan pages.
        while response.get("LastEvaluatedKey"):
            response = table.scan(
                ExclusiveStartKey=response["LastEvaluatedKey"]
            )
            events.extend(response.get("Items", []))

        return {
            "message": "Events retrieved successfully",
            "events": events
        }

    except ClientError as error:
        raise HTTPException(
            status_code=500,
            detail=f"DynamoDB error: {error.response['Error']['Message']}"
        )


# ==================================================
# POST - Create a new event
# ADMIN ONLY
# ==================================================

@router.post("")
def create_event(
    event: EventCreate,
    current_user: dict = Depends(require_admin)
):

    try:
        event_id = str(uuid.uuid4())

        current_time = datetime.now(
            timezone.utc
        ).isoformat()

        item = {
            "event_id": event_id,
            **event.model_dump(),
            "created_at": current_time,
            "updated_at": current_time
        }

        table.put_item(
            Item=item
        )

        return {
            "message": "Event created successfully",
            "event": item
        }

    except ClientError as error:
        raise HTTPException(
            status_code=500,
            detail=f"DynamoDB error: {error.response['Error']['Message']}"
        )


# ==================================================
# PUT - Update an existing event
# ADMIN ONLY
# ==================================================

@router.put("/{event_id}")
def update_event(
    event_id: str,
    event: EventUpdate,
    current_user: dict = Depends(require_admin)
):

    event_id = event_id.strip()

    try:
        response = table.get_item(
            Key={
                "event_id": event_id
            }
        )

        if "Item" not in response:
            raise HTTPException(
                status_code=404,
                detail=f"Event not found for event_id: {event_id}"
            )

        update_data = event.model_dump(
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
                "event_id": event_id
            },
            UpdateExpression="SET " + ", ".join(
                expression_parts
            ),
            ExpressionAttributeNames=expression_names,
            ExpressionAttributeValues=expression_values
        )

        updated_response = table.get_item(
            Key={
                "event_id": event_id
            }
        )

        return {
            "message": "Event updated successfully",
            "event": updated_response.get("Item")
        }

    except HTTPException:
        raise

    except ClientError as error:
        raise HTTPException(
            status_code=500,
            detail=f"DynamoDB error: {error.response['Error']['Message']}"
        )


# ==================================================
# DELETE - Delete an event
# ADMIN ONLY
# ==================================================

@router.delete("/{event_id}")
def delete_event(
    event_id: str,
    current_user: dict = Depends(require_admin)
):

    event_id = event_id.strip()

    try:
        response = table.delete_item(
            Key={
                "event_id": event_id
            },
            ReturnValues="ALL_OLD"
        )

        deleted_item = response.get("Attributes")

        if not deleted_item:
            raise HTTPException(
                status_code=404,
                detail=f"Event not found for event_id: {event_id}"
            )

        return {
            "message": "Event deleted successfully",
            "event_id": event_id,
            "event": deleted_item
        }

    except HTTPException:
        raise

    except ClientError as error:
        raise HTTPException(
            status_code=500,
            detail=f"DynamoDB error: {error.response['Error']['Message']}"
        )