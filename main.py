from fastapi import FastAPI, Header, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import uuid
import time
import base64

app = FastAPI()

# Allow browser requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

TOTAL_ORDERS = 49
RATE_LIMIT = 20
WINDOW = 10  # seconds

# -----------------------------
# In-memory storage
# -----------------------------

orders_created = {}
idempotency_store = {}

rate_limits = {}


# -----------------------------
# Request model
# -----------------------------

class Order(BaseModel):
    item: str
    quantity: int


# -----------------------------
# POST /orders
# -----------------------------

@app.post("/orders", status_code=201)
def create_order(
    order: Order,
    idempotency_key: str = Header(..., alias="Idempotency-Key")
):

    # Already created?
    if idempotency_key in idempotency_store:
        return idempotency_store[idempotency_key]

    order_id = str(uuid.uuid4())

    result = {
        "id": order_id,
        "item": order.item,
        "quantity": order.quantity
    }

    idempotency_store[idempotency_key] = result
    orders_created[order_id] = result

    return result


# -----------------------------
# GET /orders
# -----------------------------

@app.get("/orders")
def list_orders(limit: int = 10, cursor: Optional[str] = None):

    start = 1

    if cursor:
        start = int(base64.b64decode(cursor).decode())

    end = min(start + limit - 1, TOTAL_ORDERS)

    items = []

    for i in range(start, end + 1):
        items.append({
            "id": i,
            "name": f"Order {i}"
        })

    next_cursor = None

    if end < TOTAL_ORDERS:
        next_cursor = base64.b64encode(str(end + 1).encode()).decode()

    return {
        "items": items,
        "next_cursor": next_cursor
    }


# -----------------------------
# Rate Limiter
# -----------------------------

@app.middleware("http")
async def rate_limit(request, call_next):

    client = request.headers.get("X-Client-Id")

    if client:

        now = time.time()

        history = rate_limits.get(client, [])

        history = [t for t in history if now - t < WINDOW]

        if len(history) >= RATE_LIMIT:
            retry = int(WINDOW - (now - history[0]))
            if retry < 1:
                retry = 1

            return Response(
                status_code=429,
                headers={
                    "Retry-After": str(retry)
                }
            )

        history.append(now)

        rate_limits[client] = history

    response = await call_next(request)

    return response