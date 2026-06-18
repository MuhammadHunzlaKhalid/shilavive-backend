from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
import razorpay
import hmac
import hashlib
import json
import os
from datetime import datetime

# ── Config ────────────────────────────────────────────────
RAZORPAY_KEY_ID     = os.getenv("RAZORPAY_KEY_ID",     "rzp_test_T2kRiGx2IBDi0x")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET",  "seKtE77oHWStBrXKsuYyYWDx")
FRONTEND_URL        = os.getenv("FRONTEND_URL",         "https://shila-vive.com")

client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

app = FastAPI(title="Shila Vive Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten to FRONTEND_URL after testing
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── In-memory order store (replace with DB later) ─────────
orders = {}

# ── Schemas ───────────────────────────────────────────────
class CreateOrderRequest(BaseModel):
    amount: int          # INR, e.g. 999
    quantity: int
    name: str
    email: str
    phone: str

class VerifyPaymentRequest(BaseModel):
    razorpay_order_id:   str
    razorpay_payment_id: str
    razorpay_signature:  str
    name:     str
    email:    str
    phone:    str
    quantity: int

# ── Routes ────────────────────────────────────────────────
@app.get("/")
def root():
    return {"status": "Shila Vive backend running ✅"}


@app.post("/create-order")
def create_order(req: CreateOrderRequest):
    try:
        amount_paise = req.amount * 100   # Razorpay needs paise
        rzp_order = client.order.create({
            "amount":   amount_paise,
            "currency": "INR",
            "receipt":  f"rcpt_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "notes": {
                "customer_name":  req.name,
                "customer_email": req.email,
                "customer_phone": req.phone,
                "quantity":       str(req.quantity),
                "product":        "Pure Himalayan Shilajit 100g Natural Resin"
            }
        })
        # store locally
        orders[rzp_order["id"]] = {
            "order_id":    rzp_order["id"],
            "amount_inr":  req.amount,
            "quantity":    req.quantity,
            "name":        req.name,
            "email":       req.email,
            "phone":       req.phone,
            "status":      "created",
            "created_at":  datetime.now().isoformat()
        }
        return {
            "order_id":    rzp_order["id"],
            "amount_paise": amount_paise,
            "currency":    "INR"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/verify-payment")
def verify_payment(req: VerifyPaymentRequest):
    # Razorpay signature verification
    body        = f"{req.razorpay_order_id}|{req.razorpay_payment_id}"
    expected    = hmac.new(
        RAZORPAY_KEY_SECRET.encode(),
        body.encode(),
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected, req.razorpay_signature):
        raise HTTPException(status_code=400, detail="Invalid payment signature")

    # Update order record
    if req.razorpay_order_id in orders:
        orders[req.razorpay_order_id].update({
            "payment_id": req.razorpay_payment_id,
            "status":     "paid",
            "paid_at":    datetime.now().isoformat()
        })

    return {
        "status":     "success",
        "order_id":   req.razorpay_order_id,
        "payment_id": req.razorpay_payment_id,
        "message":    "Payment verified successfully"
    }


@app.get("/orders")
def list_orders(secret: str = ""):
    # simple admin protection — set ADMIN_SECRET env var on Railway
    admin_secret = os.getenv("ADMIN_SECRET", "shilavive123")
    if secret != admin_secret:
        raise HTTPException(status_code=403, detail="Forbidden")
    return {"total": len(orders), "orders": list(orders.values())}
