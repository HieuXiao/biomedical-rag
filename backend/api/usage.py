"""Theo dõi hạn mức sử dụng model theo ngày (dùng chung giữa các router)."""

from __future__ import annotations

import json
import threading
from datetime import date
from pathlib import Path

from core import config

MODEL_LIMITS = config.MODEL_LIMITS
USAGE_FILE = Path(__file__).resolve().parents[1] / "data" / "model_usage.json"
_lock = threading.RLock()


def _default_state():
    return {"usage_day": date.today().isoformat(), "model_usage": {n: 0 for n in MODEL_LIMITS}}


def _load():
    if not USAGE_FILE.exists():
        state = _default_state()
        USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
        USAGE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        return state["usage_day"], state["model_usage"]
    try:
        raw = json.loads(USAGE_FILE.read_text(encoding="utf-8"))
        day = str(raw.get("usage_day", date.today().isoformat()))
        fu = raw.get("model_usage", {})
        return day, {n: int(fu.get(n, 0)) for n in MODEL_LIMITS}
    except Exception:
        state = _default_state()
        USAGE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        return state["usage_day"], state["model_usage"]


_usage_day, _model_usage = _load()


def _save():
    USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    USAGE_FILE.write_text(
        json.dumps({"usage_day": _usage_day, "model_usage": _model_usage}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def reset_if_new_day():
    global _usage_day, _model_usage
    today = date.today().isoformat()
    with _lock:
        if _usage_day != today:
            _usage_day = today
            _model_usage = {n: 0 for n in MODEL_LIMITS}
            _save()


def usage_percent(model_name: str) -> int:
    with _lock:
        limit = MODEL_LIMITS.get(model_name, 0)
        used = _model_usage.get(model_name, 0)
    return min(100, int((used / limit) * 100)) if limit > 0 else 0


def increment(model_name: str):
    if model_name in _model_usage:
        with _lock:
            _model_usage[model_name] += 1
            _save()


def snapshot():
    reset_if_new_day()
    with _lock:
        models = [
            {"name": n, "used": _model_usage.get(n, 0), "limit": lim, "usage_percent": usage_percent(n)}
            for n, lim in MODEL_LIMITS.items()
        ]
        return {"models": models, "usage_day": _usage_day}
