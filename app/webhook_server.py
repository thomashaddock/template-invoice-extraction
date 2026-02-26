import json
import logging
import os
import threading
import time
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request, Response

logger = logging.getLogger(__name__)

WEBHOOK_BEARER_TOKEN = os.getenv("WEBHOOK_BEARER_TOKEN", "")

# File-based result store — works both in-process (local dev) and
# cross-process (Heroku where FastAPI and Streamlit are separate processes).
RESULTS_DIR = Path(os.environ.get("WEBHOOK_RESULTS_DIR", "/tmp/doc2data_webhooks"))
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

webhook_app = FastAPI(title="Doc2Data Webhook Receiver", docs_url=None, redoc_url=None)


@webhook_app.get("/health")
async def health():
    return {"status": "ok"}


@webhook_app.post("/webhook")
async def receive_webhook(request: Request):
    """
    Receives the crewWebhookUrl callback from CrewAI Enterprise.

    Payload format (per CrewAI docs):
    {
        "kickoff_id": "abcd-1234-...",
        "result": "string with final output",
        "result_json": { ... structured data ... },
        "token_usage": { ... },
        "meta": { ... }
    }
    """
    if WEBHOOK_BEARER_TOKEN:
        auth = request.headers.get("Authorization", "")
        if auth and auth != f"Bearer {WEBHOOK_BEARER_TOKEN}":
            logger.warning("Webhook auth failed — rejecting request")
            return Response(
                content=json.dumps({"error": "unauthorized"}),
                status_code=401,
                media_type="application/json",
            )

    body = await request.json()
    logger.info("Webhook received: keys=%s", list(body.keys()))

    kickoff_id = body.get("kickoff_id")
    if not kickoff_id:
        logger.warning("Webhook payload missing kickoff_id — ignoring")
        return {"status": "ignored", "reason": "no kickoff_id"}

    result_json = body.get("result_json") or {}
    result_raw = body.get("result", "")

    if not result_json and result_raw:
        try:
            result_json = json.loads(result_raw) if isinstance(result_raw, str) else result_raw
        except (json.JSONDecodeError, TypeError):
            result_json = {}

    parsed = {
        "extraction_status": result_json.get("extraction_status", "completed"),
        "invoice_data": result_json.get("invoice_data", {}),
        "db_record_id": result_json.get("db_record_id"),
        "error_message": result_json.get("error_message"),
    }

    _store_result(kickoff_id, parsed)
    logger.info("Webhook stored result for kickoff_id=%s", kickoff_id)

    return {"status": "received"}


# ── File-based result storage ───────────────────────────────


def _store_result(kickoff_id: str, result: dict):
    """Atomically write result to disk for cross-process access."""
    result["_ts"] = time.time()
    path = RESULTS_DIR / f"{kickoff_id}.json"
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(result))
    tmp_path.rename(path)


def wait_for_result(kickoff_id: str, timeout: int = 120) -> dict | None:
    """
    Poll the filesystem for a result file. Works whether the webhook
    handler runs in the same process (local dev) or a different one (Heroku).
    Checks 4x/sec — reading a tiny file from /tmp is essentially free.
    """
    path = RESULTS_DIR / f"{kickoff_id}.json"
    elapsed = 0.0
    while elapsed < timeout:
        if path.exists():
            try:
                result = json.loads(path.read_text())
                path.unlink(missing_ok=True)
                result.pop("_ts", None)
                return result
            except (json.JSONDecodeError, OSError):
                pass
        time.sleep(0.25)
        elapsed += 0.25
    return None


def cleanup_stale_results(max_age_seconds: int = 300):
    """Remove unclaimed result files older than *max_age_seconds*."""
    now = time.time()
    for path in RESULTS_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text())
            if now - data.get("_ts", 0) > max_age_seconds:
                path.unlink(missing_ok=True)
        except (json.JSONDecodeError, OSError):
            path.unlink(missing_ok=True)


# ── Background thread server (local dev only) ──────────────


def _run_server(port: int):
    try:
        uvicorn.run(webhook_app, host="0.0.0.0", port=port, log_level="warning")
    except OSError as e:
        logger.error("Webhook server failed to start on port %d: %s", port, e)


def ensure_webhook_server_running(port: int | None = None):
    """
    Start the FastAPI webhook receiver in a background thread.
    Used for local development only. On Heroku, server.py handles
    the webhook endpoint directly — this is skipped via env var.
    """
    if os.environ.get("_DOC2DATA_PROXY_MODE"):
        return

    if getattr(ensure_webhook_server_running, "_started", False):
        return

    if port is None:
        port = int(os.getenv("WEBHOOK_SERVER_PORT", "8000"))

    thread = threading.Thread(target=_run_server, args=(port,), daemon=True)
    thread.start()
    ensure_webhook_server_running._started = True
    logger.info("Webhook server started on port %d", port)
