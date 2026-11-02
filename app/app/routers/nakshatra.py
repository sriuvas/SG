from fastapi import APIRouter, HTTPException, Depends
from boto3.dynamodb.conditions import Attr

from app.models.nakshatra import (
    NakshatraCreate,
    NakshatraUpdate,
    NakshatraCalculate
)

from app.auth.dependencies import (
    get_current_user,
    require_admin
)

from app.services.nakshatra_service import (
    calculate_nakshatra
)

from database import dynamodb

import uuid
from datetime import datetime, timezone


router = APIRouter(
    prefix="/api/nakshatra",
    tags=["Nakshatra"]
)


# ==================================================
# DynamoDB Table
# ==================================================

TABLE_NAME = "Nakshatra_Table"

table = dynamodb.Table(TABLE_NAME)


# ==================================================
# GET - Get all Nakshatra information
# User + Admin can access
# ==================================================

@router.get("")
def get_nakshatra(
    current_user: dict = Depends(get_current_user)
):

    response = table.scan()
    items = response.get("Items", [])
    # First-In, First-Out (FIFO) sorting: newly added nakshatras always appear last
    items.sort(key=lambda x: x.get("created_at") or "")

    return {
        "message": "Nakshatra retrieved successfully",
        "nakshatra": items
    }


# ==================================================
# POST - Calculate User Nakshatra
# User + Admin can access
#
# User provides:
#   - Name
#   - Date of Birth
#   - Birth Time
#
# Returns:
#   - Calculated Nakshatra
#   - Nakshatra number
#   - Moon longitude
#   - Stored Nakshatra details
# ==================================================

@router.post("/calculate")
def calculate_user_nakshatra(
    data: NakshatraCalculate,
    current_user: dict = Depends(get_current_user)
):

    # ------------------------------------------------
    # Validate name
    # ------------------------------------------------

    if not data.name.strip():

        raise HTTPException(
            status_code=400,
            detail="Name is required"
        )

    # ------------------------------------------------
    # Calculate Nakshatra
    # ------------------------------------------------

    try:

        result = calculate_nakshatra(
            data.date_of_birth,
            data.birth_time
        )

    except ValueError as e:

        raise HTTPException(
            status_code=400,
            detail=str(e)
        )

    except Exception as e:

        print(
            f"Nakshatra calculation error: {str(e)}"
        )

        raise HTTPException(
            status_code=500,
            detail="Unable to calculate Nakshatra"
        )

    # ------------------------------------------------
    # Find Nakshatra details in DynamoDB
    # ------------------------------------------------

    try:

        response = table.scan(
            FilterExpression=Attr(
                "nakshatra_name"
            ).eq(result["nakshatra"])
        )

        items = response.get(
            "Items",
            []
        )

    except Exception as e:

        print(
            f"DynamoDB Nakshatra lookup error: {str(e)}"
        )

        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve Nakshatra details"
        )

    # ------------------------------------------------
    # Get matching Nakshatra details
    # ------------------------------------------------

    nakshatra_details = (
        items[0]
        if items
        else None
    )

    # ------------------------------------------------
    # Return result
    # ------------------------------------------------

    return {

        "message":
            "Nakshatra calculated successfully",

        "name":
            data.name.strip(),

        "date_of_birth":
            data.date_of_birth,

        "birth_time":
            data.birth_time,

        "nakshatra":
            result["nakshatra"],

        "nakshatra_number":
            result["nakshatra_number"],

        "sidereal_moon_longitude":
            result["sidereal_moon_longitude"],

        "nakshatra_position_degrees":
            result["nakshatra_position_degrees"],

        "details":
            nakshatra_details
    }


# ==================================================
# POST - Create Nakshatra information
# Admin Only
# ==================================================

@router.post("")
def create_nakshatra(
    nakshatra: NakshatraCreate,
    current_user: dict = Depends(require_admin)
):

    nakshatra_id = str(
        uuid.uuid4()
    )

    current_time = datetime.now(
        timezone.utc
    ).isoformat()

    item = {

        "nakshatra_id":
            nakshatra_id,

        **nakshatra.model_dump(),

        "created_at":
            current_time,

        "updated_at":
            current_time
    }

    table.put_item(
        Item=item
    )

    return {

        "message":
            "Nakshatra created successfully",

        "nakshatra":
            item
    }


# ==================================================
# PUT - Update Nakshatra information
# Admin Only
# ==================================================

@router.put("/{nakshatra_id}")
def update_nakshatra(
    nakshatra_id: str,
    nakshatra: NakshatraUpdate,
    current_user: dict = Depends(require_admin)
):

    nakshatra_id = nakshatra_id.strip()

    response = table.get_item(
        Key={
            "nakshatra_id":
                nakshatra_id
        }
    )

    if "Item" not in response:

        raise HTTPException(
            status_code=404,
            detail=(
                "Nakshatra not found for "
                f"nakshatra_id: {nakshatra_id}"
            )
        )

    update_data = nakshatra.model_dump(
        exclude_unset=True
    )

    if not update_data:

        raise HTTPException(
            status_code=400,
            detail="No fields provided for update"
        )

    update_data["updated_at"] = (
        datetime.now(
            timezone.utc
        ).isoformat()
    )

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
            "nakshatra_id":
                nakshatra_id
        },

        UpdateExpression=(
            "SET "
            + ", ".join(
                expression_parts
            )
        ),

        ExpressionAttributeNames=
            expression_names,

        ExpressionAttributeValues=
            expression_values
    )

    updated_response = table.get_item(
        Key={
            "nakshatra_id":
                nakshatra_id
        }
    )

    return {

        "message":
            "Nakshatra updated successfully",

        "nakshatra":
            updated_response.get("Item")
    }


# ==================================================
# DELETE - Delete Nakshatra information
# Admin Only
# ==================================================

@router.delete("/{nakshatra_id}")
def delete_nakshatra(
    nakshatra_id: str,
    current_user: dict = Depends(require_admin)
):

    nakshatra_id = nakshatra_id.strip()

    response = table.delete_item(

        Key={
            "nakshatra_id":
                nakshatra_id
        },

        ReturnValues="ALL_OLD"
    )

    if "Attributes" not in response:

        raise HTTPException(
            status_code=404,
            detail=(
                "Nakshatra not found for "
                f"nakshatra_id: {nakshatra_id}"
            )
        )

    return {

        "message":
            "Nakshatra deleted successfully",

        "nakshatra_id":
            nakshatra_id
    }