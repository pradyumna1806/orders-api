from fastapi import FastAPI, Header, Request, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import uuid
import time
import base64

app = FastAPI()

# -----------------------------
# CORS
# -----------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

TOTAL_ORDERS = 49
RATE_LIMIT = 20
WINDOW = 10  # seconds

# -----------------------------
# In-memory storage
# -----------------------------
idempotency_store = {}
rate_limits = {}

# -----------------------------
# Rate Limiter Middleware
# -----------------------------
@app.middleware("http")
async def rate_limit(request: Request, call_next):

    client = request.headers.get("X-Client-Id")

    if client:
        now = time.time()

        history = rate_limits.get(client, [])

        # Keep only requests within last WINDOW seconds
        history = [t for t in history if now - t < WINDOW]

        if len(history) >= RATE_LIMIT:
            retry_after = max(1, int(WINDOW - (now - history[0])))

            return Response(
                content="Rate limit exceeded",
                status_code=429,
                headers={
                    "Retry-After": str(retry_after)
                },
            )

        history.append(now)
        rate_limits[client] = history

    response = await call_next(request)
    return response


# -----------------------------
# POST /orders
# -----------------------------
@app.post("/orders", status_code=201)
async def create_order(
    request: Request,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Missing Idempotency-Key")

    # Same key -> same response
    if idempotency_key in idempotency_store:
        return idempotency_store[idempotency_key]

    # Accept any valid JSON body
    try:
        body = await request.json()
        if not isinstance(body, dict):
            body = {}
    except Exception:
        body = {}

    result = {
        "id": str(uuid.uuid4()),
        **body,
    }

    idempotency_store[idempotency_key] = result

    return result


# -----------------------------
# GET /orders
# -----------------------------
@app.get("/orders")
def list_orders(limit: int = 10, cursor: Optional[str] = None):

    if limit < 1:
        limit = 1

    start = 1

    if cursor:
        try:
            start = int(base64.b64decode(cursor.encode()).decode())
        except Exception:
            start = 1

    if start > TOTAL_ORDERS:
        return {
            "items": [],
            "next_cursor": None
        }

    end = min(start + limit - 1, TOTAL_ORDERS)

    items = []

    for i in range(start, end + 1):
        items.append({
            "id": i
        })

    next_cursor = None

    if end < TOTAL_ORDERS:
        next_cursor = base64.b64encode(str(end + 1).encode()).decode()

    return {
        "items": items,
        "next_cursor": next_cursor
    }


# -----------------------------
# Root endpoint
# -----------------------------
@app.get("/")
def root():
    return {
        "message": "Orders API is running"
    }