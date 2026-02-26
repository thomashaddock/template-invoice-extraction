"""
Combined entry point for Heroku deployment.

Heroku only routes external traffic to a single $PORT. This server
listens on $PORT and handles two responsibilities:

  1. POST /webhook  →  receives CrewAI crew completion callbacks
  2. Everything else →  reverse-proxied to Streamlit (internal port 8501)

Streamlit is started as a subprocess on an internal port that is NOT
externally routable. The file-based result store in webhook_server.py
bridges results between this process and the Streamlit subprocess.
"""
import asyncio
import logging
import os
import subprocess
import sys
import time

import httpx
import uvicorn
import websockets
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from starlette.responses import Response

from webhook_server import receive_webhook

logger = logging.getLogger(__name__)

STREAMLIT_PORT = 8501
PORT = int(os.environ.get("PORT", 8080))

from contextlib import asynccontextmanager

_http_client: httpx.AsyncClient | None = None


@asynccontextmanager
async def _lifespan(application: FastAPI):
    global _http_client
    _http_client = httpx.AsyncClient(
        base_url=f"http://127.0.0.1:{STREAMLIT_PORT}",
        timeout=30.0,
    )
    yield
    await _http_client.aclose()


app = FastAPI(title="Doc2Data", docs_url=None, redoc_url=None, lifespan=_lifespan)

app.add_api_route("/webhook", receive_webhook, methods=["POST"])


@app.get("/health")
async def health():
    return {"status": "ok", "streamlit_port": STREAMLIT_PORT}


# ── HTTP reverse proxy ──────────────────────────────────────


def _get_http_client() -> httpx.AsyncClient:
    return _http_client


HOP_BY_HOP = frozenset({"host", "connection", "transfer-encoding", "keep-alive", "upgrade"})


@app.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"],
)
async def proxy_http(request: Request, path: str = ""):
    client = _get_http_client()

    url = f"/{path}"
    qs = str(request.query_params)
    if qs:
        url += f"?{qs}"

    headers = {k: v for k, v in request.headers.items() if k.lower() not in HOP_BY_HOP}

    try:
        resp = await client.request(
            method=request.method,
            url=url,
            headers=headers,
            content=await request.body(),
            follow_redirects=False,
        )
    except httpx.ConnectError:
        return Response(content="Streamlit is starting up...", status_code=503)

    resp_headers = dict(resp.headers)
    for h in ("transfer-encoding", "content-encoding", "content-length"):
        resp_headers.pop(h, None)

    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=resp_headers,
    )


# ── WebSocket reverse proxy (Streamlit uses /_stcore/stream) ─


@app.websocket("/{path:path}")
async def proxy_ws(websocket: WebSocket, path: str = ""):
    await websocket.accept()

    ws_url = f"ws://127.0.0.1:{STREAMLIT_PORT}/{path}"
    qs = str(websocket.query_params)
    if qs:
        ws_url += f"?{qs}"

    upstream = None
    try:
        upstream = await websockets.connect(
            ws_url,
            max_size=2**24,
            open_timeout=10,
            ping_interval=20,
            ping_timeout=20,
            compression=None,
        )
        logger.info("WS proxy connected to upstream %s", ws_url)
    except Exception as e:
        logger.error("WS proxy failed to connect to %s: %s", ws_url, e)
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
        return

    async def client_to_upstream():
        try:
            while True:
                msg = await websocket.receive()
                msg_type = msg.get("type", "")
                if msg_type == "websocket.disconnect":
                    break
                if "text" in msg:
                    await upstream.send(msg["text"])
                elif "bytes" in msg:
                    await upstream.send(msg["bytes"])
        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.error("WS client->upstream error: %s", e)

    async def upstream_to_client():
        try:
            async for message in upstream:
                if isinstance(message, str):
                    await websocket.send_text(message)
                else:
                    await websocket.send_bytes(message)
        except Exception as e:
            logger.error("WS upstream->client error: %s", e)

    try:
        tasks = [
            asyncio.create_task(client_to_upstream()),
            asyncio.create_task(upstream_to_client()),
        ]
        _, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for t in pending:
            t.cancel()
    except Exception as e:
        logger.error("WS proxy relay error: %s", e)
    finally:
        try:
            await upstream.close()
        except Exception:
            pass
        try:
            await websocket.close()
        except Exception:
            pass


# ── Streamlit subprocess management ─────────────────────────


def _start_streamlit() -> subprocess.Popen:
    env = os.environ.copy()
    env["_DOC2DATA_PROXY_MODE"] = "1"

    cmd = [
        sys.executable, "-m", "streamlit", "run",
        "app/main.py",
        f"--server.port={STREAMLIT_PORT}",
        "--server.address=127.0.0.1",
        "--server.headless=true",
        "--server.enableCORS=false",
        "--server.enableXsrfProtection=false",
        "--server.enableWebsocketCompression=false",
        "--browser.gatherUsageStats=false",
    ]
    return subprocess.Popen(cmd, env=env)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Heroku's buildpack sets WEB_CONCURRENCY=2, which makes uvicorn
    # try multi-worker mode. That requires an import string, not an app
    # object. Force single-worker since we manage Streamlit ourselves.
    os.environ.pop("WEB_CONCURRENCY", None)

    logger.info("Starting Streamlit subprocess on port %d...", STREAMLIT_PORT)
    proc = _start_streamlit()

    time.sleep(3)
    logger.info("Starting FastAPI proxy on port %d...", PORT)

    try:
        uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info", workers=1)
    except KeyboardInterrupt:
        pass
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
