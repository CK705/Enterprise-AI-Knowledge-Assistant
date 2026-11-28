"""Internal ProjectFlow knowledge service. Run uvicorn phase3_service:app."""

import hashlib
import hmac
import logging
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from phase3_engine import Answer, AnswerRequest, EmbedRequest, answer_question, embed_texts

load_dotenv(Path(__file__).resolve().with_name(".env"))
logger = logging.getLogger(__name__)
app = FastAPI(title="ProjectFlow internal knowledge service", docs_url=None, redoc_url=None,
              openapi_url=None)
MAX_BODY_BYTES = 1024 * 1024
SIGNATURE_WINDOW_SECONDS = 120


@app.get("/health")
def health():
    return {"status": "ok"}


async def signed_body(request: Request) -> bytes:
    secret = os.getenv("PHASE3_SERVICE_SECRET")
    if not secret or not secret.strip():
        raise HTTPException(status_code=503, detail="Knowledge service authentication is unconfigured")
    timestamp = request.headers.get("X-Knowledge-Timestamp", "")
    signature = request.headers.get("X-Knowledge-Signature", "")
    if (len(timestamp) != 10 or not timestamp.isascii() or not timestamp.isdecimal()
            or abs(time.time() - int(timestamp)) > SIGNATURE_WINDOW_SECONDS):
        raise HTTPException(status_code=401, detail="Invalid service signature")
    if len(signature) != 64 or not signature.isascii():
        raise HTTPException(status_code=401, detail="Invalid service signature")
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_BODY_BYTES:
            raise HTTPException(status_code=413, detail="Request is too large")
        body.extend(chunk)
    expected = hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=401, detail="Invalid service signature")
    return bytes(body)


def parse_signed_request(schema, body: bytes):
    # The legacy timestamp + body signature authenticates an envelope independently
    # of its URL. Make the two operations' required fields mutually exclusive.
    import json

    try:
        payload = json.loads(body)
        if not isinstance(payload, dict) or ("operation" in payload) == ("purpose" in payload):
            raise ValueError("Ambiguous operation")
        return schema.model_validate(payload)
    except (ValidationError, ValueError, RecursionError):
        # Validation details may contain private question text or passages.
        raise HTTPException(status_code=422, detail="Invalid knowledge service request") from None


async def call_provider(operation, payload):
    try:
        return await run_in_threadpool(operation, payload)
    except Exception as exc:
        # Provider error bodies can echo input. Emit only the category and request operation.
        logger.error("Knowledge service %s failed (%s)", operation.__name__, type(exc).__name__)
        raise HTTPException(status_code=503, detail="Knowledge service provider unavailable") from None


@app.post("/internal/knowledge/answer", response_model=Answer)
async def answer(body: bytes = Depends(signed_body)):
    return await call_provider(answer_question, parse_signed_request(AnswerRequest, body))


@app.post("/internal/knowledge/embed")
async def embed(body: bytes = Depends(signed_body)):
    return await call_provider(embed_texts, parse_signed_request(EmbedRequest, body))


@app.post("/internal/knowledge/verify")
async def verify(body: bytes = Depends(signed_body)):
    from phase3_engine import VerifyRequest, verify_faq
    return await call_provider(verify_faq, parse_signed_request(VerifyRequest, body))
