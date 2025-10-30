# app/debug.py
from fastapi import APIRouter
from typing import Dict, Any
from collections import deque
import time
import threading

router = APIRouter()
_lock = threading.Lock()
_relay_requests = deque(maxlen=50)  # ring buffer of recent relay requests

def trace_relay_request(name: str, on: bool, via: str, result: Dict[str, Any]) -> None:
    item = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
        "name": name,
        "on": on,
        "via": via,
        "result": result,
    }
    with _lock:
        _relay_requests.append(item)

@router.get("/relay_requests")
def relay_requests() -> Dict[str, Any]:
    """Get the last 50 relay set requests for debugging."""
    with _lock:
        return {"count": len(_relay_requests), "items": list(_relay_requests)}
