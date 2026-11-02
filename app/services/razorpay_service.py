import os
import razorpay
from dotenv import load_dotenv

load_dotenv()

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")

if not RAZORPAY_KEY_ID:
    raise RuntimeError("RAZORPAY_KEY_ID is not configured")

if not RAZORPAY_KEY_SECRET:
    raise RuntimeError("RAZORPAY_KEY_SECRET is not configured")

razorpay_client = razorpay.Client(
    auth=(
        RAZORPAY_KEY_ID,
        RAZORPAY_KEY_SECRET
    )
)


def create_razorpay_order(
    amount_paise: int,
    receipt: str
):
    order_data = {
        "amount": amount_paise,
        "currency": "INR",
        "receipt": receipt
    }

    return razorpay_client.order.create(
        data=order_data
    )


def verify_razorpay_payment(
    razorpay_order_id: str,
    razorpay_payment_id: str,
    razorpay_signature: str
):
    payment_data = {
        "razorpay_order_id": razorpay_order_id,
        "razorpay_payment_id": razorpay_payment_id,
        "razorpay_signature": razorpay_signature
    }

    return razorpay_client.utility.verify_payment_signature(
        payment_data
    )