import os

from dotenv import load_dotenv

from fastapi import (
    Depends,
    HTTPException
)

from fastapi.security import (
    HTTPBearer,
    HTTPAuthorizationCredentials
)

from jose import (
    jwt,
    JWTError
)


# ==================================================
# LOAD ENVIRONMENT VARIABLES
# ==================================================

load_dotenv()


# ==================================================
# JWT CONFIGURATION
# ==================================================

SECRET_KEY = os.getenv(
    "JWT_SECRET_KEY"
)

ALGORITHM = "HS256"


if not SECRET_KEY:
    raise RuntimeError(
        "JWT_SECRET_KEY is not configured"
    )


# ==================================================
# HTTP BEARER AUTHENTICATION
# ==================================================

security = HTTPBearer()


# ==================================================
# GET CURRENT USER
# ==================================================

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(
        security
    )
):

    # ----------------------------------------------
    # Get JWT token
    # ----------------------------------------------

    token = credentials.credentials


    try:

        # ------------------------------------------
        # Decode JWT
        # ------------------------------------------

        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )


        # ------------------------------------------
        # Get user_id from JWT
        # ------------------------------------------

        user_id = payload.get(
            "user_id"
        )


        # ------------------------------------------
        # Get role from JWT
        # ------------------------------------------

        role = payload.get(
            "role"
        )


        # ------------------------------------------
        # Validate user_id
        # ------------------------------------------

        if user_id is None:

            raise HTTPException(
                status_code=401,
                detail="Invalid token: user_id missing"
            )


        # ------------------------------------------
        # Validate role
        # ------------------------------------------

        if role is None:

            raise HTTPException(
                status_code=401,
                detail="Invalid token: role missing"
            )


        # ------------------------------------------
        # Convert values to clean strings
        # ------------------------------------------

        user_id = str(
            user_id
        ).strip()

        role = str(
            role
        ).strip().lower()


        # ------------------------------------------
        # Final validation
        # ------------------------------------------

        if not user_id:

            raise HTTPException(
                status_code=401,
                detail="Invalid token: user_id is empty"
            )


        if not role:

            raise HTTPException(
                status_code=401,
                detail="Invalid token: role is empty"
            )


        # ------------------------------------------
        # DEBUG INFORMATION
        #
        # This prints ONLY user_id and role.
        # It does NOT print the JWT token.
        # ------------------------------------------

        print(
            "=========================================="
        )

        print(
            "AUTHENTICATED USER"
        )

        print(
            f"user_id: {user_id}"
        )

        print(
            f"role: {role}"
        )

        print(
            "=========================================="
        )


        # ------------------------------------------
        # Return authenticated user
        # ------------------------------------------

        return {
            "user_id": user_id,
            "role": role
        }


    # ----------------------------------------------
    # JWT Error
    # ----------------------------------------------

    except JWTError:

        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token"
        )


# ==================================================
# REQUIRE ADMIN
# ==================================================

def require_admin(
    current_user: dict = Depends(
        get_current_user
    )
):

    # ----------------------------------------------
    # Check admin role
    # ----------------------------------------------

    if current_user["role"] != "admin":
        try:
            import boto3
            dynamodb = boto3.resource("dynamodb", region_name=os.getenv("AWS_S3_REGION_NAME", "eu-north-1"))
            user_table = dynamodb.Table("Users_Table")
            resp = user_table.get_item(Key={"user_id": current_user["user_id"]})
            item = resp.get("Item")
            if item and str(item.get("role", "")).strip().lower() == "admin":
                current_user["role"] = "admin"
                return current_user
        except Exception as e:
            print("Fallback admin check error:", e)

        raise HTTPException(
            status_code=403,
            detail="Admin access required"
        )


    # ----------------------------------------------
    # Return authenticated admin
    # ----------------------------------------------

    return current_user