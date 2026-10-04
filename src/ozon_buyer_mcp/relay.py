from __future__ import annotations

import asyncio
import os
import time
import uuid
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
import uvicorn

SERVER_TOKEN = (os.getenv("OZON_RELAY_SERVER_TOKEN") or "").strip()
WORKER_TOKEN = (os.getenv("OZON_WORKER_TOKEN") or "").strip()
JOB_TIMEOUT = int(os.getenv("OZON_RELAY_JOB_TIMEOUT", "120"))

queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
waiters: dict[str, asyncio.Future] = {}
last_worker_seen = 0.0


def _bearer(request: Request) -> str:
    value = request.headers.get("authorization", "")
    return value[7:] if value.startswith("Bearer ") else ""


async def health(request: Request) -> JSONResponse:
    age = (time.time() - last_worker_seen) if last_worker_seen else None
    return JSONResponse({
        "ok": True,
        "worker_online": bool(age is not None and age < 40),
        "worker_last_seen_seconds": round(age, 1) if age is not None else None,
        "queued": queue.qsize(),
        "waiting": len(waiters),
    })


async def submit(request: Request) -> JSONResponse:
    if not SERVER_TOKEN or _bearer(request) != SERVER_TOKEN:
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
    body = await request.json()
    op = str(body.get("op") or "")
    payload = body.get("payload") or {}
    if op not in {"search-dom", "market-search-dom", "delivery-dom", "fetch-json"}:
        return JSONResponse({"ok": False, "error": "unsupported operation"}, status_code=400)

    job_id = uuid.uuid4().hex
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    waiters[job_id] = future
    await queue.put({"id": job_id, "op": op, "payload": payload})
    try:
        result = await asyncio.wait_for(future, timeout=JOB_TIMEOUT)
        return JSONResponse(result)
    except asyncio.TimeoutError:
        return JSONResponse({"ok": False, "error": "local marketplace worker timeout"}, status_code=504)
    finally:
        waiters.pop(job_id, None)


async def next_job(request: Request) -> JSONResponse:
    global last_worker_seen
    if not WORKER_TOKEN or _bearer(request) != WORKER_TOKEN:
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
    last_worker_seen = time.time()
    try:
        job = await asyncio.wait_for(queue.get(), timeout=25)
        return JSONResponse({"ok": True, "job": job})
    except asyncio.TimeoutError:
        return JSONResponse({"ok": True, "job": None})


async def result(request: Request) -> JSONResponse:
    global last_worker_seen
    if not WORKER_TOKEN or _bearer(request) != WORKER_TOKEN:
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
    last_worker_seen = time.time()
    body = await request.json()
    job_id = str(body.get("id") or "")
    response = body.get("response")
    future = waiters.get(job_id)
    if future is None:
        return JSONResponse({"ok": False, "error": "unknown or expired job"}, status_code=404)
    if not future.done():
        future.set_result(response if isinstance(response, dict) else {"ok": False, "error": "invalid worker response"})
    return JSONResponse({"ok": True})


app = Starlette(routes=[
    Route("/health", health, methods=["GET"]),
    Route("/submit", submit, methods=["POST"]),
    Route("/next", next_job, methods=["GET"]),
    Route("/result", result, methods=["POST"]),
])


def main() -> None:
    if not SERVER_TOKEN or not WORKER_TOKEN:
        raise RuntimeError("OZON_RELAY_SERVER_TOKEN and OZON_WORKER_TOKEN are required")
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")), log_level="info")


if __name__ == "__main__":
    main()
