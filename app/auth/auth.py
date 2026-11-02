import os

from dotenv import load_dotenv

from fastapi import (
    APIRouter,
    HTTPException,
    Depends
)

from fastapi.security import (
    HTTPBearer,
    HTTPAuthorizationCredentials
)

from pydantic import BaseModel

from database import dynamodb

from passlib.context import CryptContext

from jose import (
    jwt,
    JWTError
)

from datetime import (
    datetime,
    timedelta,
    timezone
)


# ==================================================
# Load Environment Variables
# ==================================================

load_dotenv()


# ==================================================
# Router
# ==================================================

router = APIRouter(
    prefix="/api/auth",
    tags=["Authentication"]
)


# ==================================================
# Password Hashing
# ==================================================

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
)


# ==================================================
# JWT Configuration
# ==================================================

SECRET_KEY = os.getenv(
    "JWT_SECRET_KEY"
)

ALGORITHM = "HS256"


# ==================================================
# ACCESS TOKEN
# ==================================================

# Access token is short-lived.
#
# Current project setting:
# 60 minutes
#
# The access token is used to access
# protected APIs.

ACCESS_TOKEN_EXPIRE_MINUTES = 60


# ==================================================
# REFRESH TOKEN
# ==================================================

# Refresh token is long-lived.
#
# Validity:
# 1 year = 365 days
#
# The refresh token is ONLY used to
# generate a new access token.

REFRESH_TOKEN_EXPIRE_DAYS = 365


# ==================================================
# Bearer Token Security
# ==================================================

security = HTTPBearer()


# ==================================================
# DynamoDB Table
# ==================================================

TABLE_NAME = "Users_Table"

table = dynamodb.Table(
    TABLE_NAME
)


# ==================================================
# Login Request Model
# ==================================================

class LoginRequest(BaseModel):

    email: str

    password: str


# ==================================================
# Refresh Token Request Model
# ==================================================

class RefreshTokenRequest(BaseModel):

    refresh_token: str


# ==================================================
# Verify Password
# ==================================================

def verify_password(
    plain_password: str,
    password_hash: str
) -> bool:

    return pwd_context.verify(
        plain_password,
        password_hash
    )


# ==================================================
# Create Access Token
# ==================================================

def create_access_token(
    user_id: str,
    role: str
) -> str:

    expire = datetime.now(
        timezone.utc
    ) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )

    payload = {

        "user_id": user_id,

        "role": role,

        "token_type": "access",

        "exp": expire
    }

    token = jwt.encode(
        payload,
        SECRET_KEY,
        algorithm=ALGORITHM
    )

    return token


# ==================================================
# Create Refresh Token
# ==================================================

def create_refresh_token(
    user_id: str,
    role: str
) -> str:

    expire = datetime.now(
        timezone.utc
    ) + timedelta(
        days=REFRESH_TOKEN_EXPIRE_DAYS
    )

    payload = {

        "user_id": user_id,

        "role": role,

        "token_type": "refresh",

        "exp": expire
    }

    token = jwt.encode(
        payload,
        SECRET_KEY,
        algorithm=ALGORITHM
    )

    return token


# ==================================================
# POST - Login
# ==================================================

@router.post("/login")
def login(
    credentials: LoginRequest
):

    # ==================================================
    # Find User By Email
    # ==================================================

    response = table.scan(

        FilterExpression="email = :email",

        ExpressionAttributeValues={

            ":email": credentials.email

        }
    )

    users = response.get(
        "Items",
        []
    )


    # ==================================================
    # Check Whether User Exists
    # ==================================================

    if not users:

        raise HTTPException(

            status_code=401,

            detail="Invalid email or password"
        )


    user = users[0]


    # ==================================================
    # Get Password Hash
    # ==================================================

    password_hash = user.get(
        "password_hash"
    )

    if not password_hash:

        raise HTTPException(

            status_code=401,

            detail="User password is not configured"
        )


    # ==================================================
    # Verify Password
    # ==================================================

    if not verify_password(

        credentials.password,

        password_hash

    ):

        raise HTTPException(

            status_code=401,

            detail="Invalid email or password"
        )


    # ==================================================
    # Get User Information
    # ==================================================

    user_id = user.get(
        "user_id"
    )

    role = user.get(
        "role",
        "User"
    )


    # ==================================================
    # Generate Access Token
    # ==================================================

    access_token = create_access_token(

        user_id=user_id,

        role=role

    )


    # ==================================================
    # Generate Refresh Token
    # ==================================================

    refresh_token = create_refresh_token(

        user_id=user_id,

        role=role

    )


    # ==================================================
    # Return Login Response
    # ==================================================

    return {

        "access_token":
            access_token,

        "refresh_token":
            refresh_token,

        "token_type":
            "bearer",

        "role":
            role,

        "user_id":
            user_id

    }


# ==================================================
# POST - Refresh Access Token
# ==================================================

@router.post("/refresh")
def refresh_access_token(
    request: RefreshTokenRequest
):

    refresh_token = (
        request.refresh_token.strip()
    )


    # ==================================================
    # Validate Refresh Token Input
    # ==================================================

    if not refresh_token:

        raise HTTPException(

            status_code=401,

            detail="Refresh token is required"
        )


    try:

        # ==================================================
        # Decode Refresh Token
        # ==================================================

        payload = jwt.decode(

            refresh_token,

            SECRET_KEY,

            algorithms=[ALGORITHM]

        )


        # ==================================================
        # Check Token Type
        # ==================================================

        token_type = payload.get(
            "token_type"
        )

        if token_type != "refresh":

            raise HTTPException(

                status_code=401,

                detail="Invalid refresh token"
            )


        # ==================================================
        # Get User Information
        # ==================================================

        user_id = payload.get(
            "user_id"
        )

        role = payload.get(
            "role"
        )


        # ==================================================
        # Validate User Information
        # ==================================================

        if not user_id or not role:

            raise HTTPException(

                status_code=401,

                detail="Invalid refresh token"
            )


        # ==================================================
        # Generate New Access Token
        # ==================================================

        new_access_token = create_access_token(

            user_id=user_id,

            role=role

        )


        # ==================================================
        # Return New Access Token
        # ==================================================

        return {

            "access_token":
                new_access_token,

            "token_type":
                "bearer",

            "user_id":
                user_id,

            "role":
                role

        }


    except JWTError:

        raise HTTPException(

            status_code=401,

            detail="Invalid or expired refresh token"
        )


# ==================================================
# Get Current User
# ==================================================

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(
        security
    )
):

    token = credentials.credentials

    try:

        # ==================================================
        # Decode JWT Token
        # ==================================================

        payload = jwt.decode(

            token,

            SECRET_KEY,

            algorithms=[ALGORITHM]

        )


        # ==================================================
        # Get User ID
        # ==================================================

        user_id = payload.get(
            "user_id"
        )


        # ==================================================
        # Get Role
        # ==================================================

        role = payload.get(
            "role"
        )


        # ==================================================
        # Get Token Type
        # ==================================================

        token_type = payload.get(
            "token_type"
        )


        # ==================================================
        # Validate Token
        # ==================================================

        if not user_id or not role:

            raise HTTPException(

                status_code=401,

                detail="Invalid token"
            )


        # ==================================================
        # Prevent Refresh Token From Being Used
        # Directly Against Protected APIs
        # ==================================================

        if token_type == "refresh":

            raise HTTPException(

                status_code=401,

                detail=(
                    "Refresh token cannot be used "
                    "as an access token"
                )
            )


        # ==================================================
        # Return Current User
        # ==================================================

        return {

            "user_id":
                user_id,

            "role":
                role

        }


    except JWTError:

        raise HTTPException(

            status_code=401,

            detail="Invalid or expired token"
        )


# ==================================================
# Admin Authorization
# ==================================================

def require_admin(
    current_user: dict = Depends(
        get_current_user
    )
):

    # ==================================================
    # Check Whether User Is Admin
    # ==================================================

    if current_user["role"].lower() != "admin":

        raise HTTPException(

            status_code=403,

            detail="Admin access required"
        )


    return current_user