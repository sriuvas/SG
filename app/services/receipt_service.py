from datetime import datetime, timezone
from io import BytesIO
import os
from xml.sax.saxutils import escape

import boto3

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


# ============================================================
# AWS S3 CONFIGURATION
# ============================================================

S3_BUCKET_NAME = os.getenv("AWS_STORAGE_BUCKET_NAME")
S3_REGION_NAME = os.getenv("AWS_S3_REGION_NAME", "eu-north-1")

s3_client = boto3.client("s3", region_name=S3_REGION_NAME)


# ============================================================
# FONT REGISTRATION (Supporting ₹ Indian Rupee Symbol)
# ============================================================

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS_DIR = os.path.join(BASE_DIR, "fonts")

FONT_NAME = "Helvetica"
FONT_NAME_BOLD = "Helvetica-Bold"

def _init_receipt_fonts():
    global FONT_NAME, FONT_NAME_BOLD

    font_candidates = [
        (
            os.path.join(FONTS_DIR, "arial.ttf"),
            os.path.join(FONTS_DIR, "arialbd.ttf"),
        ),
        (
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
        ),
        (
            "C:/Windows/Fonts/segoeui.ttf",
            "C:/Windows/Fonts/segoeuib.ttf",
        ),
        (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ),
        (
            "/usr/share/fonts/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
        ),
    ]

    for reg_path, bold_path in font_candidates:
        if os.path.exists(reg_path):
            try:
                pdfmetrics.registerFont(TTFont("ReceiptFont", reg_path))
                if os.path.exists(bold_path):
                    pdfmetrics.registerFont(TTFont("ReceiptFont-Bold", bold_path))
                else:
                    pdfmetrics.registerFont(TTFont("ReceiptFont-Bold", reg_path))
                FONT_NAME = "ReceiptFont"
                FONT_NAME_BOLD = "ReceiptFont-Bold"
                return
            except Exception:
                continue

_init_receipt_fonts()


# ============================================================
# COMMON PDF STYLES & COLOR THEME
# ============================================================

TEMPLE_MAROON = colors.HexColor("#781D0F")
TEMPLE_GOLD = colors.HexColor("#D97706")
CREAM_BG = colors.HexColor("#FFF8EB")
GOLD_BORDER = colors.HexColor("#E5C378")
TEXT_DARK = colors.HexColor("#1C1917")
TEXT_MUTED = colors.HexColor("#57534E")
AMOUNT_BG = colors.HexColor("#FEF3C7")

styles = getSampleStyleSheet()

title_style = ParagraphStyle(
    "ReceiptTitle",
    parent=styles["Title"],
    fontName=FONT_NAME_BOLD,
    alignment=TA_CENTER,
    fontSize=18,
    leading=22,
    textColor=TEMPLE_MAROON,
    spaceAfter=6,
)

subtitle_style = ParagraphStyle(
    "ReceiptSubtitle",
    parent=styles["Normal"],
    fontName=FONT_NAME_BOLD,
    alignment=TA_CENTER,
    fontSize=11,
    leading=15,
    textColor=TEMPLE_GOLD,
    spaceAfter=18,
)

body_style = ParagraphStyle(
    "ReceiptBody",
    parent=styles["Normal"],
    fontName=FONT_NAME,
    fontSize=10,
    leading=14,
    textColor=TEXT_DARK,
)


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def _safe_value(value, default=""):
    """Convert values to safe strings for PDF display."""
    if value is None or str(value).strip() == "":
        value = default

    return escape(str(value))


def _format_date(date_val):
    """Format dates cleanly (e.g. 14 Oct 2026, 04:00 PM)."""
    if not date_val:
        return "Not specified"

    if isinstance(date_val, (int, float)):
        try:
            dt = datetime.fromtimestamp(date_val, tz=timezone.utc)
            return dt.strftime("%d %b %Y, %I:%M %p")
        except Exception:
            return str(date_val)

    if isinstance(date_val, str):
        date_str = date_val.strip()
        try:
            clean = date_str.replace("Z", "+00:00")
            dt = datetime.fromisoformat(clean)
            return dt.strftime("%d %b %Y, %I:%M %p")
        except Exception:
            return date_str

    return str(date_val)


def _format_amount(amount, is_free=False):
    """Format currency values cleanly with ₹ symbol."""
    if is_free:
        return "Free Seva"

    try:
        val = float(amount)
        if val == 0:
            return "Free Seva"
        return f"₹ {val:,.2f}"
    except Exception:
        return f"₹ {amount}"


def _build_receipt_table(details, col_widths):
    """Build a consistently styled receipt details table."""
    table = Table(details, colWidths=col_widths)

    table_style_list = [
        # Left Label Column - Warm Cream Background
        ("BACKGROUND", (0, 0), (0, -1), CREAM_BG),
        ("TEXTCOLOR", (0, 0), (0, -1), TEXT_MUTED),
        ("FONTNAME", (0, 0), (0, -1), FONT_NAME_BOLD),
        ("FONTSIZE", (0, 0), (0, -1), 9.5),

        # Right Value Column - Clean White Background
        ("BACKGROUND", (1, 0), (1, -1), colors.white),
        ("TEXTCOLOR", (1, 0), (1, -1), TEXT_DARK),
        ("FONTNAME", (1, 0), (1, -1), FONT_NAME),
        ("FONTSIZE", (1, 0), (1, -1), 9.5),

        # Grid lines and Outer Box Borders
        ("GRID", (0, 0), (-1, -1), 0.5, GOLD_BORDER),
        ("BOX", (0, 0), (-1, -1), 1.25, TEMPLE_GOLD),

        # Alignment and Padding
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]

    # Special highlighting for Total Amount / Donation Amount rows
    for i, row in enumerate(details):
        if row and any(
            keyword in str(row[0]).lower()
            for keyword in ["amount", "total amount", "donation amount"]
        ):
            table_style_list.extend(
                [
                    ("BACKGROUND", (0, i), (0, i), AMOUNT_BG),
                    ("BACKGROUND", (1, i), (1, i), colors.HexColor("#FFFBEB")),
                    ("TEXTCOLOR", (0, i), (0, i), TEMPLE_MAROON),
                    ("TEXTCOLOR", (1, i), (1, i), TEMPLE_MAROON),
                    ("FONTNAME", (0, i), (-1, i), FONT_NAME_BOLD),
                    ("FONTSIZE", (0, i), (-1, i), 10.5),
                ]
            )

    table.setStyle(TableStyle(table_style_list))
    return table


def _generate_standard_receipt(
    title,
    subtitle,
    details,
    col_widths,
    thank_you_message,
    closing_message=None,
):
    """Generate a PDF receipt using the common layout."""
    buffer = BytesIO()

    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=40,
        leftMargin=40,
        topMargin=36,
        bottomMargin=36,
    )

    elements = [
        Paragraph(escape(title), title_style),
        Paragraph(escape(subtitle), subtitle_style),
        _build_receipt_table(details, col_widths),
        Spacer(1, 16),
        Paragraph(escape(thank_you_message), body_style),
    ]

    if closing_message:
        elements.extend(
            [
                Spacer(1, 8),
                Paragraph(escape(closing_message), body_style),
            ]
        )

    elements.extend(
        [
            Spacer(1, 14),
            Paragraph(
                escape("May the Divine Blessings of Sri Subramanya Swamy be with you and your family."),
                ParagraphStyle(
                    "BlessingStyle",
                    parent=styles["Normal"],
                    fontName=FONT_NAME_BOLD,
                    alignment=TA_CENTER,
                    fontSize=9.5,
                    leading=14,
                    textColor=TEMPLE_MAROON,
                ),
            ),
            Spacer(1, 5),
            Paragraph(
                escape("* This is an authentic computer-generated official receipt. No physical signature is required."),
                ParagraphStyle(
                    "ComputerGenerated",
                    parent=styles["Normal"],
                    fontName=FONT_NAME,
                    alignment=TA_CENTER,
                    fontSize=8,
                    leading=11,
                    textColor=colors.HexColor("#78716C"),
                ),
            ),
        ]
    )

    document.build(elements)

    return buffer.getvalue()


# ============================================================
# PROGRAM REGISTRATION RECEIPT
# ============================================================

def generate_program_receipt_pdf(registration: dict) -> bytes:
    amount = registration.get("total_amount", registration.get("amount", 0))
    is_free = (
        registration.get("payment_required") is False
        or (isinstance(amount, (int, float)) and amount == 0)
        or str(amount).strip() in {"0", "0.0", "0.00"}
    )

    details = [
        ["Receipt Number", _safe_value(registration.get("receipt_number"))],
        [
            "Transaction ID",
            _safe_value(
                registration.get("transaction_id")
                or registration.get("razorpay_payment_id")
            ),
        ],
        ["Registration ID", _safe_value(registration.get("registration_id"))],
        [
            "Program ID",
            _safe_value(
                registration.get("program_id")
                or registration.get("program_title")
                or registration.get("program_name")
            ),
        ],
        [
            "Devotee Name",
            _safe_value(
                registration.get("devotee_name")
                or registration.get("name")
            ),
        ],
        ["Email", _safe_value(registration.get("email"))],
        ["Phone", _safe_value(registration.get("phone"))],
    ]

    if registration.get("gothram"):
        details.append(["Gothram", _safe_value(registration.get("gothram"))])

    if registration.get("nakshatram"):
        details.append(["Nakshatram", _safe_value(registration.get("nakshatram"))])

    attendees = (
        registration.get("attendees_count")
        or registration.get("attendees")
        or 1
    )
    details.append(["Attendees", _safe_value(attendees)])

    unit_price = registration.get("unit_price")
    if unit_price is not None:
        try:
            if float(unit_price) > 0:
                details.append(["Unit Price", _format_amount(unit_price)])
        except (ValueError, TypeError):
            pass

    details.extend(
        [
            ["Total Amount", _format_amount(amount, is_free=is_free)],
            [
                "Payment Status",
                _safe_value(
                    registration.get("status")
                    or registration.get("payment_status")
                    or "SUCCESS"
                ),
            ],
            [
                "Registration Date",
                _format_date(
                    registration.get("created_at")
                    or registration.get("registration_date")
                    or registration.get("date")
                ),
            ],
        ]
    )

    return _generate_standard_receipt(
        title="Temple Program Registration Receipt",
        subtitle="Official Payment Receipt",
        details=details,
        col_widths=[150, 340],
        thank_you_message="Thank you for participating in the temple program.",
    )


# ============================================================
# EVENT RECEIPT
# ============================================================

def generate_event_receipt_pdf(registration: dict) -> bytes:
    amount = registration.get("total_amount", registration.get("amount", 0))
    is_free = (
        registration.get("payment_required") is False
        or (isinstance(amount, (int, float)) and amount == 0)
        or str(amount).strip() in {"0", "0.0", "0.00"}
    )

    details = [
        ["Receipt Number", _safe_value(registration.get("receipt_number"))],
        [
            "Transaction ID",
            _safe_value(
                registration.get("transaction_id")
                or registration.get("razorpay_payment_id")
            ),
        ],
        ["Registration ID", _safe_value(registration.get("registration_id"))],
        [
            "Event ID",
            _safe_value(
                registration.get("event_id")
                or registration.get("event_title")
                or registration.get("event_name")
            ),
        ],
        [
            "Devotee Name",
            _safe_value(
                registration.get("devotee_name")
                or registration.get("name")
            ),
        ],
        ["Email", _safe_value(registration.get("email"))],
        ["Phone", _safe_value(registration.get("phone"))],
    ]

    if registration.get("gothram"):
        details.append(["Gothram", _safe_value(registration.get("gothram"))])

    if registration.get("nakshatram"):
        details.append(["Nakshatram", _safe_value(registration.get("nakshatram"))])

    attendees = (
        registration.get("attendees_count")
        or registration.get("attendees")
        or 1
    )
    details.append(["Attendees", _safe_value(attendees)])

    unit_price = registration.get("unit_price")
    if unit_price is not None:
        try:
            if float(unit_price) > 0:
                details.append(["Unit Price", _format_amount(unit_price)])
        except (ValueError, TypeError):
            pass

    details.extend(
        [
            ["Total Amount", _format_amount(amount, is_free=is_free)],
            [
                "Payment Status",
                _safe_value(
                    registration.get("status")
                    or registration.get("payment_status")
                    or "SUCCESS"
                ),
            ],
            [
                "Registration Date",
                _format_date(
                    registration.get("created_at")
                    or registration.get("registration_date")
                    or registration.get("date")
                ),
            ],
        ]
    )

    return _generate_standard_receipt(
        title="Temple Event Registration Receipt",
        subtitle="Official Payment Receipt",
        details=details,
        col_widths=[150, 340],
        thank_you_message="Thank you for participating in the temple event.",
    )


# ============================================================
# DONATION RECEIPT
# ============================================================

def generate_donation_receipt_pdf(donation: dict) -> bytes:
    """Generate a donation receipt including the donor's place or city."""
    amount = donation.get("amount", donation.get("donation_amount", 0))

    place = donation.get("place")
    if place is None or str(place).strip() == "":
        place = donation.get("city")
    if place is None or str(place).strip() == "":
        place = "Not provided"

    details = [
        ["Receipt Number", _safe_value(donation.get("receipt_number"))],
        [
            "Transaction ID",
            _safe_value(
                donation.get("transaction_id")
                or donation.get("razorpay_payment_id")
            ),
        ],
        [
            "Donation ID",
            _safe_value(
                donation.get("donation_id")
                or donation.get("id")
            ),
        ],
        [
            "Donor Name",
            _safe_value(
                donation.get("donor_name")
                or donation.get("name")
            ),
        ],
        ["Email", _safe_value(donation.get("email"))],
        ["Phone", _safe_value(donation.get("phone"))],
        ["Place / City", _safe_value(place)],
        ["Donation Amount", _format_amount(amount)],
        [
            "Payment Status",
            _safe_value(
                donation.get("payment_status")
                or donation.get("status")
                or "SUCCESS"
            ),
        ],
        [
            "Donation Date",
            _format_date(
                donation.get("created_at")
                or donation.get("payment_date")
                or donation.get("date")
            ),
        ],
    ]

    return _generate_standard_receipt(
        title="Temple Donation Receipt",
        subtitle="Official Donation Payment Receipt",
        details=details,
        col_widths=[170, 320],
        thank_you_message="Thank you for your generous contribution to the temple.",
        closing_message=(
            "This receipt confirms that the donation payment was successfully processed."
        ),
    )


# ============================================================
# UPLOAD RECEIPT TO S3
# ============================================================

def upload_receipt_to_s3(pdf_bytes: bytes, receipt_number: str):
    if not S3_BUCKET_NAME:
        raise RuntimeError("AWS_STORAGE_BUCKET_NAME is not configured")

    clean_receipt_number = str(receipt_number).strip()
    if not clean_receipt_number:
        raise ValueError("Receipt number is required for S3 upload")

    receipt_s3_key = f"receipts/{clean_receipt_number}.pdf"

    s3_client.put_object(
        Bucket=S3_BUCKET_NAME,
        Key=receipt_s3_key,
        Body=pdf_bytes,
        ContentType="application/pdf",
    )

    receipt_s3_url = (
        f"https://{S3_BUCKET_NAME}.s3."
        f"{S3_REGION_NAME}.amazonaws.com/"
        f"{receipt_s3_key}"
    )

    return {
        "receipt_s3_key": receipt_s3_key,
        "receipt_s3_url": receipt_s3_url,
    }


# ============================================================
# GENERATE PRESIGNED URL
# ============================================================

def generate_receipt_presigned_url(
    receipt_s3_key: str,
    expiration: int = 3600,
):
    if not S3_BUCKET_NAME:
        raise RuntimeError("AWS_STORAGE_BUCKET_NAME is not configured")

    if not receipt_s3_key or not isinstance(receipt_s3_key, str):
        raise ValueError("Invalid receipt S3 key: key must be a non-empty string")

    clean_key = receipt_s3_key.strip()
    invalid_placeholders = {"receipt_s3_key", "receipt_s3_url", "none", "null", ""}
    if clean_key.lower() in invalid_placeholders or not clean_key.startswith("receipts/"):
        raise ValueError(f"Invalid receipt S3 key: '{receipt_s3_key}' is not a valid S3 location")

    return s3_client.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": S3_BUCKET_NAME,
            "Key": clean_key,
        },
        ExpiresIn=expiration,
    )