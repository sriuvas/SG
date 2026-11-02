import os
import time
import uuid
import boto3
from botocore.exceptions import ClientError
from fastapi import (
    APIRouter,
    HTTPException,
    UploadFile,
    File,
    Depends,
    Form,
)
from pydantic import BaseModel
from app.auth.dependencies import require_admin

router = APIRouter(
    prefix="/api/pages",
    tags=["Page Media"]
)

S3_BUCKET_NAME = os.getenv(
    "MEDIA_S3_BUCKET_NAME",
    "images1245"
)

S3_REGION_NAME = os.getenv(
    "AWS_S3_REGION_NAME",
    "eu-north-1"
)

s3_client = boto3.client(
    "s3",
    region_name=S3_REGION_NAME
)

MEDIA_URL_EXPIRATION = int(
    os.getenv(
        "MEDIA_URL_EXPIRATION",
        "3600"
    )
)

IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp"
}

VIDEO_EXTENSIONS = {
    ".mp4",
    ".webm",
    ".mov",
    ".m4v",
    ".avi",
    ".mkv",
    ".3gp"
}

PDF_EXTENSIONS = {
    ".pdf"
}

ALLOWED_PAGE_NAMES = {
    "home",
    "nakshatra",
    "gallery",
    "events",
    "programs",
    "committee",
    "goshala"
}

HOME_SLOTS = {
    "hero": {
        "section": "hero",
        "prefix": "home/hero/"
    },
    "photo1": {
        "section": "experience",
        "prefix": "home/"
    },
    "photo2": {
        "section": "discover",
        "prefix": "home/"
    },
    "photo3": {
        "section": "events",
        "prefix": "home/"
    },
    "photo4": {
        "section": "programs",
        "prefix": "home/"
    },
    "photo5": {
        "section": "gallery",
        "prefix": "home/"
    },
    "photo6": {
        "section": "donation",
        "prefix": "home/"
    }
}


def build_permanent_s3_url(
    object_key: str
) -> str:
    return (
        f"https://{S3_BUCKET_NAME}.s3.{S3_REGION_NAME}.amazonaws.com/"
        f"{object_key}"
    )


def get_media_type(
    file_name: str
) -> str | None:

    extension = os.path.splitext(
        file_name
    )[1].lower()

    if extension in IMAGE_EXTENSIONS:
        return "image"

    if extension in VIDEO_EXTENSIONS:
        return "video"

    if extension in PDF_EXTENSIONS:
        return "pdf"

    return None


def get_home_slot_from_key(
    object_key: str
) -> str | None:

    if object_key.startswith(
        "home/hero/"
    ):
        return "hero"

    file_name = os.path.basename(
        object_key
    )

    for slot in (
        "photo1",
        "photo2",
        "photo3",
        "photo4",
        "photo5",
        "photo6"
    ):
        if file_name.lower().startswith(
            f"{slot}."
        ):
            return slot

    return None


def build_home_object_key(
    slot: str,
    extension: str
) -> str:

    slot = slot.strip().lower()
    extension = extension.lower()

    if slot == "hero":
        return (
            "home/hero/"
            f"hero{extension}"
        )

    if slot in {
        "photo1",
        "photo2",
        "photo3",
        "photo4",
        "photo5",
        "photo6"
    }:
        return (
            "home/"
            f"{slot}{extension}"
        )

    raise HTTPException(
        status_code=400,
        detail=(
            "Invalid Home slot. "
            "Allowed slots are: "
            "hero, photo1, photo2, "
            "photo3, photo4, photo5, photo6"
        )
    )


def get_page_media(
    page_name: str
):
    prefix = f"{page_name}/"
    media = []

    try:
        paginator = s3_client.get_paginator(
            "list_objects_v2"
        )

        pages = paginator.paginate(
            Bucket=S3_BUCKET_NAME,
            Prefix=prefix
        )

        for page in pages:

            objects = page.get(
                "Contents",
                []
            )

            for obj in objects:

                object_key = obj.get(
                    "Key"
                )

                if not object_key:
                    continue

                if object_key.endswith("/"):
                    continue

                file_name = os.path.basename(
                    object_key
                )

                media_type = get_media_type(
                    file_name
                )

                if not media_type:
                    continue

                # Read title from S3 metadata.
                # Existing files without metadata use
                # their filename as the fallback title.
                object_title = file_name

                head_meta = {}
                try:
                    head_response = s3_client.head_object(
                        Bucket=S3_BUCKET_NAME,
                        Key=object_key
                    )
                    head_meta = head_response.get("Metadata", {})
                    object_title = (
                        head_meta.get("title")
                        or file_name
                    )

                except ClientError as error:

                    print(
                        "Unable to read media metadata:",
                        error
                    )

                last_modified = obj.get("LastModified")
                last_modified_ts = int(last_modified.timestamp()) if last_modified else None

                created_at_ts = None
                if head_meta.get("created_at"):
                    try:
                        created_at_ts = int(head_meta.get("created_at"))
                    except Exception:
                        pass
                if not created_at_ts and last_modified_ts:
                    created_at_ts = last_modified_ts

                permanent_url = build_permanent_s3_url(
                    object_key
                )
                url_with_version = (
                    f"{permanent_url}?v={last_modified_ts}"
                    if last_modified_ts
                    else permanent_url
                )

                item = {
                    "title":
                        object_title,

                    "file_name":
                        file_name,

                    "type":
                        media_type,

                    "s3_object_key":
                        object_key,

                    "url":
                        url_with_version,

                    "version":
                        last_modified_ts,

                    "created_at_ts":
                        created_at_ts,

                    "last_modified":
                        last_modified.isoformat() if last_modified else None
                }

                if page_name == "home":

                    slot = (
                        get_home_slot_from_key(
                            object_key
                        )
                    )

                    if slot:

                        item["slot"] = slot

                        item["section"] = (
                            HOME_SLOTS[
                                slot
                            ]["section"]
                        )

                media.append(
                    item
                )

        if page_name == "home":

            slot_order = {
                "hero": 0,
                "photo1": 1,
                "photo2": 2,
                "photo3": 3,
                "photo4": 4,
                "photo5": 5,
                "photo6": 6
            }

            media.sort(
                key=lambda item:
                    slot_order.get(
                        item.get("slot"),
                        99
                    )
            )
        else:
            # First-In, First-Out (FIFO) sorting:
            # Sort by created_at_ts ascending so newly added media always comes LAST,
            # while in-place edits preserve their existing position.
            import re

            def natural_tokens(s):
                norm = re.sub(r'[\s_\-]+', ' ', s.lower()).strip()
                tokens = re.split(r'(\d+)', norm)
                return [(0, int(t)) if t.isdigit() else (1, t) for t in tokens if t]

            def fifo_sort_key(item):
                c_ts = item.get("created_at_ts") or item.get("version") or 0
                key = item.get("file_name") or item.get("s3_object_key") or ""
                return (c_ts, natural_tokens(key))

            media.sort(key=fifo_sort_key)

        return media

    except ClientError as error:

        print(
            "S3 media access error:",
            error
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "Unable to access media "
                "storage"
            )
        )

    except Exception as error:

        print(
            "Unexpected media access error:",
            error
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "Unable to retrieve page "
                "media"
            )
        )


def delete_existing_home_slot(
    slot: str
):

    possible_extensions = [
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".mp4",
        ".webm",
        ".mov",
        ".m4v",
        ".avi",
        ".mkv",
        ".3gp",
        ".pdf"
    ]

    for extension in possible_extensions:

        key = build_home_object_key(
            slot,
            extension
        )

        try:

            s3_client.head_object(
                Bucket=S3_BUCKET_NAME,
                Key=key
            )

            s3_client.delete_object(
                Bucket=S3_BUCKET_NAME,
                Key=key
            )

        except ClientError as error:

            error_code = (
                error.response
                .get(
                    "Error",
                    {}
                )
                .get(
                    "Code"
                )
            )

            if error_code in {
                "404",
                "NoSuchKey",
                "NotFound"
            }:
                continue

            raise


def build_safe_page_media_key(
    page_name: str,
    media_title: str | None,
    original_file_name: str | None,
    extension: str
) -> tuple[str, str]:
    import re
    base_candidate = ""
    if media_title and media_title.strip():
        base_candidate = media_title.strip()
    elif original_file_name and original_file_name.strip():
        base_candidate = os.path.splitext(original_file_name.strip())[0]

    # Replace forbidden filename and URL characters with underscores
    safe_name = re.sub(r'[/\\?#&%"\'*:<>.|~`!@$^+=()[\]{}]+', '_', base_candidate).strip()
    # Collapse multiple spaces, hyphens, and underscores
    safe_name = re.sub(r'[\s_-]+', '_', safe_name).strip('_')

    generic_names = {"blob", "upload", "image", "media", "file", f"{page_name}_media", f"{page_name}_item"}
    if not safe_name or safe_name.lower() in generic_names:
        if original_file_name:
            orig_base = os.path.splitext(original_file_name.strip())[0]
            clean_orig = re.sub(r'[/\\?#&%"\'*:<>.|~`!@$^+=()[\]{}]+', '_', orig_base).strip()
            clean_orig = re.sub(r'[\s_-]+', '_', clean_orig).strip('_')
            if clean_orig and clean_orig.lower() not in generic_names:
                safe_name = clean_orig

    if not safe_name or safe_name.lower() in generic_names:
        safe_name = f"{page_name}_item"

    safe_name = safe_name[:80].strip('_')

    candidate_file_name = f"{safe_name}{extension}"
    candidate_key = f"{page_name}/{candidate_file_name}"

    try:
        s3_client.head_object(Bucket=S3_BUCKET_NAME, Key=candidate_key)
        # Collision detected: append counter suffix _2, _3, ...
        counter = 2
        while counter < 1000:
            candidate_file_name = f"{safe_name}_{counter}{extension}"
            candidate_key = f"{page_name}/{candidate_file_name}"
            try:
                s3_client.head_object(Bucket=S3_BUCKET_NAME, Key=candidate_key)
                counter += 1
            except ClientError:
                break
    except ClientError:
        pass

    return candidate_key, candidate_file_name


class UploadUrlRequest(BaseModel):
    file_name: str
    content_type: str | None = None
    slot: str | None = None
    title: str | None = None
    overwrite: bool | None = False
    replace_file_name: str | None = None


@router.post(
    "/{page_name}/upload-url"
)
def get_upload_url(
    page_name: str,
    payload: UploadUrlRequest,
    current_user: dict = Depends(
        require_admin
    )
):
    try:
        page_name = (
            page_name
            .strip()
            .lower()
        )

        if page_name not in ALLOWED_PAGE_NAMES:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Invalid page name. Allowed pages are: "
                    "home, nakshatra, gallery, "
                    "events, programs, committee, "
                    "goshala"
                )
            )

        if not payload.file_name:
            raise HTTPException(
                status_code=400,
                detail="file_name is required"
            )

        media_type = get_media_type(
            payload.file_name
        )

        if not media_type:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Unsupported file type. "
                    "Allowed images: JPG, JPEG, "
                    "PNG, WEBP. "
                    "Allowed videos: MP4, WEBM, "
                    "MOV, M4V, AVI, MKV, 3GP. "
                    "Allowed documents: PDF."
                )
            )

        extension = os.path.splitext(
            payload.file_name
        )[1].lower()

        media_title = (
            payload.title.strip()
            if payload.title and payload.title.strip()
            else None
        )

        if page_name == "home":
            if not payload.slot:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Home slot is required. "
                        "Allowed slots are: "
                        "hero, photo1, photo2, "
                        "photo3, photo4, photo5, "
                        "photo6"
                    )
                )

            slot = (
                payload.slot
                .strip()
                .lower()
            )

            if slot not in HOME_SLOTS:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Invalid Home slot. "
                        "Allowed slots are: "
                        "hero, photo1, photo2, "
                        "photo3, photo4, photo5, "
                        "photo6"
                    )
                )

            delete_existing_home_slot(
                slot
            )

            s3_object_key = (
                build_home_object_key(
                    slot,
                    extension
                )
            )

            stored_file_name = (
                os.path.basename(
                    s3_object_key
                )
            )
        else:
            if payload.overwrite or payload.replace_file_name:
                raw_target = (payload.file_name or payload.replace_file_name).strip()
                stored_file_name = os.path.basename(raw_target)
                s3_object_key = f"{page_name}/{stored_file_name}"

                # Check existing created_at before deleting old file
                existing_created_at = None
                check_keys = [s3_object_key]
                if payload.replace_file_name:
                    check_keys.append(f"{page_name}/{os.path.basename(payload.replace_file_name.strip())}")
                for ck in check_keys:
                    try:
                        head = s3_client.head_object(Bucket=S3_BUCKET_NAME, Key=ck)
                        meta = head.get("Metadata", {})
                        if meta.get("created_at"):
                            existing_created_at = meta.get("created_at")
                            break
                        elif head.get("LastModified"):
                            existing_created_at = str(int(head["LastModified"].timestamp()))
                            break
                    except Exception:
                        pass

                # If replace_file_name was passed and differs from target, delete old file so it doesn't linger
                if payload.replace_file_name:
                    clean_old = os.path.basename(payload.replace_file_name.strip())
                    if clean_old != stored_file_name:
                        try:
                            s3_client.delete_object(Bucket=S3_BUCKET_NAME, Key=f"{page_name}/{clean_old}")
                        except Exception as del_err:
                            print("Old file deletion failed:", del_err)
            else:
                s3_object_key, stored_file_name = build_safe_page_media_key(
                    page_name,
                    media_title,
                    payload.file_name,
                    extension
                )

        content_type = payload.content_type
        if not content_type or content_type == "application/octet-stream":
            if extension == ".pdf":
                content_type = "application/pdf"
            elif extension in {".mp4", ".m4v"}:
                content_type = "video/mp4"
            elif extension == ".mov":
                content_type = "video/quicktime"
            elif extension == ".webm":
                content_type = "video/webm"
            elif extension in VIDEO_EXTENSIONS:
                content_type = "video/mp4"
            elif extension in {".jpg", ".jpeg"}:
                content_type = "image/jpeg"
            elif extension in IMAGE_EXTENSIONS:
                content_type = f"image/{extension.lstrip('.')}"
            else:
                content_type = "application/octet-stream"

        upload_params = {
            "Bucket": S3_BUCKET_NAME,
            "Key": s3_object_key,
        }

        presigned_upload_url = s3_client.generate_presigned_url(
            "put_object",
            Params=upload_params,
            ExpiresIn=3600
        )

        current_ts = int(time.time())
        permanent_url = build_permanent_s3_url(
            s3_object_key
        )
        url_with_version = f"{permanent_url}?v={current_ts}"

        response = {
            "message": "Upload URL generated successfully",
            "upload_url": presigned_upload_url,
            "url": url_with_version,
            "version": current_ts,
            "page": page_name,
            "title": media_title or payload.file_name,
            "file_name": payload.file_name,
            "stored_file_name": stored_file_name,
            "type": media_type,
            "content_type": content_type,
            "s3_bucket": S3_BUCKET_NAME,
            "s3_object_key": s3_object_key,
        }

        if page_name == "home" and payload.slot:
            slot = payload.slot.strip().lower()
            response["slot"] = slot
            response["section"] = HOME_SLOTS[slot]["section"]

        return response

    except HTTPException:
        raise
    except Exception as error:
        print("Upload URL error:", error)
        raise HTTPException(
            status_code=500,
            detail="Unable to generate upload URL"
        )


@router.post(
    "/{page_name}/media"
)
async def upload_page_media(

    page_name: str,

    file: UploadFile = File(...),

    slot: str | None = Form(
        default=None
    ),

    title: str | None = Form(
        default=None
    ),

    overwrite: bool | None = Form(
        default=False
    ),

    replace_file_name: str | None = Form(
        default=None
    ),

    current_user: dict = Depends(
        require_admin
    )

):

    try:

        page_name = (
            page_name
            .strip()
            .lower()
        )

        if page_name not in ALLOWED_PAGE_NAMES:

            raise HTTPException(
                status_code=400,
                detail=(
                    "Invalid page name. "
                    "Allowed pages are: "
                    "home, nakshatra, gallery, "
                    "events, programs, committee, "
                    "goshala"
                )
            )

        if not file.filename:

            raise HTTPException(
                status_code=400,
                detail="No file selected"
            )

        media_type = get_media_type(
            file.filename
        )

        if not media_type:

            raise HTTPException(
                status_code=400,
                detail=(
                    "Unsupported file type. "
                    "Allowed images: JPG, JPEG, "
                    "PNG, WEBP. "
                    "Allowed videos: MP4, WEBM. "
                    "Allowed documents: PDF."
                )
            )

        extension = os.path.splitext(
            file.filename
        )[1].lower()

        media_title = (
            title.strip()
            if title and title.strip()
            else None
        )

        if page_name == "home":

            if not slot:

                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Home slot is required. "
                        "Allowed slots are: "
                        "hero, photo1, photo2, "
                        "photo3, photo4, photo5, "
                        "photo6"
                    )
                )

            slot = (
                slot
                .strip()
                .lower()
            )

            if slot not in HOME_SLOTS:

                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Invalid Home slot. "
                        "Allowed slots are: "
                        "hero, photo1, photo2, "
                        "photo3, photo4, photo5, "
                        "photo6"
                    )
                )

            delete_existing_home_slot(
                slot
            )

            s3_object_key = (
                build_home_object_key(
                    slot,
                    extension
                )
            )

            stored_file_name = (
                os.path.basename(
                    s3_object_key
                )
            )
        else:
            if overwrite or replace_file_name:
                raw_target = os.path.basename((file.filename or replace_file_name).strip())
                s3_object_key = f"{page_name}/{raw_target}"
                stored_file_name = raw_target
            else:
                s3_object_key, stored_file_name = build_safe_page_media_key(
                    page_name,
                    media_title,
                    file.filename,
                    extension
                )

        content_type = (
            file.content_type
            or "application/octet-stream"
        )
        if not content_type or content_type == "application/octet-stream":
            if extension == ".pdf":
                content_type = "application/pdf"
            elif extension in {".mp4", ".m4v"}:
                content_type = "video/mp4"
            elif extension == ".mov":
                content_type = "video/quicktime"
            elif extension == ".webm":
                content_type = "video/webm"
            elif extension in VIDEO_EXTENSIONS:
                content_type = "video/mp4"
            elif extension in {".jpg", ".jpeg"}:
                content_type = "image/jpeg"
            elif extension in IMAGE_EXTENSIONS:
                content_type = f"image/{extension.lstrip('.')}"

        upload_extra_args = {
            "ContentType":
                content_type
        }

        # Check existing created_at or preserve it
        existing_created_at = None
        check_keys = [s3_object_key]
        if replace_file_name:
            check_keys.append(f"{page_name}/{os.path.basename(replace_file_name.strip())}")
        for ck in check_keys:
            try:
                head = s3_client.head_object(Bucket=S3_BUCKET_NAME, Key=ck)
                meta = head.get("Metadata", {})
                if meta.get("created_at"):
                    existing_created_at = meta.get("created_at")
                    break
                elif head.get("LastModified"):
                    existing_created_at = str(int(head["LastModified"].timestamp()))
                    break
            except Exception:
                pass

        # If replace_file_name was passed and differs from target, delete old file so it doesn't linger
        if replace_file_name:
            clean_old = os.path.basename(replace_file_name.strip())
            if clean_old != stored_file_name:
                try:
                    s3_client.delete_object(Bucket=S3_BUCKET_NAME, Key=f"{page_name}/{clean_old}")
                except Exception as e:
                    print("Old file deletion failed:", e)

        created_ts = existing_created_at or str(int(time.time()))
        upload_metadata = {
            "created_at": created_ts
        }
        if media_title:
            upload_metadata["title"] = media_title

        upload_extra_args["Metadata"] = upload_metadata

        s3_client.upload_fileobj(

            file.file,

            S3_BUCKET_NAME,

            s3_object_key,

            ExtraArgs=
                upload_extra_args

        )

        current_ts = int(time.time())
        permanent_url = build_permanent_s3_url(
            s3_object_key
        )
        url_with_version = f"{permanent_url}?v={current_ts}"

        response = {

            "message":
                "Media uploaded successfully",

            "page":
                page_name,

            "title":
                media_title or file.filename,

            "file_name":
                file.filename,

            "stored_file_name":
                stored_file_name,

            "type":
                media_type,

            "s3_bucket":
                S3_BUCKET_NAME,

            "s3_object_key":
                s3_object_key,

            "url":
                url_with_version,

            "version":
                current_ts,

        }

        if page_name == "home":

            response["slot"] = slot

            response["section"] = (
                HOME_SLOTS[
                    slot
                ]["section"]
            )

        return response

    except HTTPException:

        raise

    except ClientError as error:

        print(
            "S3 media upload error:",
            error
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "Unable to upload media "
                "to S3"
            )
        )

    except Exception as error:

        print(
            "Unexpected media upload error:",
            error
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "Unable to upload media"
            )
        )


@router.delete(
    "/{page_name}/media"
)
def delete_page_media(

    page_name: str,

    slot: str | None = Form(
        default=None
    ),

    file_name: str | None = Form(
        default=None
    ),

    current_user: dict = Depends(
        require_admin
    )

):

    try:

        page_name = (
            page_name
            .strip()
            .lower()
        )

        if page_name not in ALLOWED_PAGE_NAMES:

            raise HTTPException(
                status_code=400,
                detail=(
                    "Invalid page name. "
                    "Allowed pages are: "
                    "home, nakshatra, gallery, "
                    "events, programs, committee, "
                    "goshala"
                )
            )

        if page_name == "home":

            if not slot:

                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Home slot is required. "
                        "Allowed slots are: "
                        "hero, photo1, photo2, "
                        "photo3, photo4, photo5, "
                        "photo6"
                    )
                )

            slot = (
                slot
                .strip()
                .lower()
            )

            if slot not in HOME_SLOTS:

                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Invalid Home slot. "
                        "Allowed slots are: "
                        "hero, photo1, photo2, "
                        "photo3, photo4, photo5, "
                        "photo6"
                    )
                )

            possible_extensions = [
                ".jpg",
                ".jpeg",
                ".png",
                ".webp",
                ".mp4",
                ".webm",
                ".mov",
                ".m4v",
                ".avi",
                ".mkv",
                ".3gp",
                ".pdf"
            ]

            s3_object_key = None

            for extension in possible_extensions:

                possible_key = (
                    build_home_object_key(
                        slot,
                        extension
                    )
                )

                try:

                    s3_client.head_object(
                        Bucket=S3_BUCKET_NAME,
                        Key=possible_key
                    )

                    s3_object_key = (
                        possible_key
                    )

                    break

                except ClientError as error:

                    error_code = (
                        error.response
                        .get(
                            "Error",
                            {}
                        )
                        .get(
                            "Code"
                        )
                    )

                    if error_code in {
                        "404",
                        "NoSuchKey",
                        "NotFound"
                    }:
                        continue

                    raise

            if not s3_object_key:

                raise HTTPException(
                    status_code=404,
                    detail=(
                        "No media found in "
                        f"Home slot '{slot}'"
                    )
                )

            s3_client.delete_object(
                Bucket=S3_BUCKET_NAME,
                Key=s3_object_key
            )

            return {

                "message":
                    "Media deleted successfully",

                "page":
                    "home",

                "slot":
                    slot,

                "section":
                    HOME_SLOTS[
                        slot
                    ]["section"],

                "s3_bucket":
                    S3_BUCKET_NAME,

                "s3_object_key":
                    s3_object_key
            }

        else:

            if not file_name:

                raise HTTPException(
                    status_code=400,
                    detail=(
                        "file_name is required "
                        "for this page"
                    )
                )

            file_name = (
                file_name
                .strip()
            )

            if (
                os.path.basename(
                    file_name
                )
                != file_name
            ):

                raise HTTPException(
                    status_code=400,
                    detail="Invalid file name"
                )

            media_type = get_media_type(
                file_name
            )

            if not media_type:

                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Unsupported file type. "
                        "Allowed images: JPG, "
                        "JPEG, PNG, WEBP. "
                        "Allowed videos: MP4, WEBM. "
                        "Allowed documents: PDF."
                    )
                )

            s3_object_key = (
                f"{page_name}/"
                f"{file_name}"
            )

            try:

                s3_client.head_object(
                    Bucket=S3_BUCKET_NAME,
                    Key=s3_object_key
                )

            except ClientError as error:

                error_code = (
                    error.response
                    .get(
                        "Error",
                        {}
                    )
                    .get(
                        "Code"
                    )
                )

                if error_code in {
                    "404",
                    "NoSuchKey",
                    "NotFound"
                }:

                    raise HTTPException(
                        status_code=404,
                        detail=(
                            "Media file not found"
                        )
                    )

                raise

            s3_client.delete_object(
                Bucket=S3_BUCKET_NAME,
                Key=s3_object_key
            )

            return {

                "message":
                    "Media deleted successfully",

                "page":
                    page_name,

                "file_name":
                    file_name,

                "s3_bucket":
                    S3_BUCKET_NAME,

                "s3_object_key":
                    s3_object_key
            }

    except HTTPException:

        raise

    except ClientError as error:

        print(
            "S3 media delete error:",
            error
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "Unable to delete media "
                "from S3"
            )
        )

    except Exception as error:

        print(
            "Unexpected media delete error:",
            error
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "Unable to delete media"
            )
        )


class UpdateMediaTitleRequest(BaseModel):
    file_name: str
    title: str
    slot: str | None = None


@router.put(
    "/{page_name}/media/title"
)
def update_page_media_title(
    page_name: str,
    payload: UpdateMediaTitleRequest,
    current_user: dict = Depends(
        require_admin
    )
):
    try:
        page_name = page_name.strip().lower()
        if page_name not in ALLOWED_PAGE_NAMES:
            raise HTTPException(
                status_code=400,
                detail="Invalid page name"
            )

        if not payload.file_name or not payload.title:
            raise HTTPException(
                status_code=400,
                detail="file_name and title are required"
            )

        target_file = os.path.basename(payload.file_name.strip())
        s3_object_key = f"{page_name}/{target_file}"

        head = s3_client.head_object(
            Bucket=S3_BUCKET_NAME,
            Key=s3_object_key
        )
        content_type = head.get("ContentType", "image/jpeg")

        s3_client.copy_object(
            Bucket=S3_BUCKET_NAME,
            Key=s3_object_key,
            CopySource={"Bucket": S3_BUCKET_NAME, "Key": s3_object_key},
            ContentType=content_type,
            Metadata={"title": payload.title.strip()},
            MetadataDirective="REPLACE"
        )

        current_ts = int(time.time())
        permanent_url = build_permanent_s3_url(s3_object_key)

        return {
            "message": "Title updated successfully",
            "title": payload.title.strip(),
            "url": f"{permanent_url}?v={current_ts}",
            "version": current_ts
        }
    except HTTPException:
        raise
    except ClientError as e:
        print("Update title client error:", e)
        raise HTTPException(
            status_code=500,
            detail=f"Unable to update media title: {str(e)}"
        )
    except Exception as e:
        print("Update title error:", e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update title: {str(e)}"
        )


@router.get(
    "/home"
)
def get_home_page_media():

    media = get_page_media(
        "home"
    )

    return {

        "page":
            "home",

        "media":
            media
    }


@router.get(
    "/nakshatra"
)
def get_nakshatra_page_media():

    media = get_page_media(
        "nakshatra"
    )

    return {

        "page":
            "nakshatra",

        "media":
            media
    }


@router.get(
    "/gallery"
)
def get_gallery_page_media():

    media = get_page_media(
        "gallery"
    )

    return {

        "page":
            "gallery",

        "media":
            media
    }


@router.get(
    "/events"
)
def get_events_page_media():

    media = get_page_media(
        "events"
    )

    return {

        "page":
            "events",

        "media":
            media
    }


@router.get(
    "/programs"
)
def get_programs_page_media():

    media = get_page_media(
        "programs"
    )

    return {

        "page":
            "programs",

        "media":
            media
    }


@router.get(
    "/committee"
)
def get_committee_page_media():

    media = get_page_media(
        "committee"
    )

    return {

        "page":
            "committee",

        "media":
            media
    }


@router.get(
    "/goshala"
)
def get_goshala_page_media():

    media = get_page_media(
        "goshala"
    )

    return {

        "page":
            "goshala",

        "media":
            media
    }