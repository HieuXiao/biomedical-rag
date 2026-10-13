import json
import threading
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core import config
from core.generator import build_pipeline, get_default_api_key

router = APIRouter()

MODEL_LIMITS = config.MODEL_LIMITS

USAGE_FILE = Path(__file__).resolve().parents[1] / "data" / "model_usage.json"
_usage_lock = threading.RLock()


# ---------------------------------------------------------------------------
# Usage tracking
# ---------------------------------------------------------------------------
def _default_usage_state():
    return {
        "usage_day": date.today().isoformat(),
        "model_usage": {name: 0 for name in MODEL_LIMITS},
    }


def _load_usage_state():
    if not USAGE_FILE.exists():
        state = _default_usage_state()
        USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
        USAGE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        return state["usage_day"], state["model_usage"]
    try:
        raw = json.loads(USAGE_FILE.read_text(encoding="utf-8"))
        usage_day = str(raw.get("usage_day", date.today().isoformat()))
        file_usage = raw.get("model_usage", {})
        merged_usage = {name: int(file_usage.get(name, 0)) for name in MODEL_LIMITS}
        return usage_day, merged_usage
    except Exception:
        state = _default_usage_state()
        USAGE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        return state["usage_day"], state["model_usage"]


def _save_usage_state():
    state = {"usage_day": _usage_day, "model_usage": _model_usage}
    USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    USAGE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


_usage_day, _model_usage = _load_usage_state()


def _reset_usage_if_new_day() -> None:
    global _usage_day, _model_usage
    today = date.today().isoformat()
    with _usage_lock:
        if _usage_day != today:
            _usage_day = today
            _model_usage = {name: 0 for name in MODEL_LIMITS}
            _save_usage_state()


def _get_usage_percent(model_name: str) -> int:
    with _usage_lock:
        limit = MODEL_LIMITS.get(model_name, 0)
        used = _model_usage.get(model_name, 0)
    if limit <= 0:
        return 0
    return min(100, int((used / limit) * 100))


def _increment_usage(model_name: str) -> None:
    if model_name in _model_usage:
        with _usage_lock:
            _model_usage[model_name] += 1
            _save_usage_state()


# ---------------------------------------------------------------------------
# Meta endpoints
# ---------------------------------------------------------------------------
@router.get("/health")
def health(request: Request):
    return {
        "status": "ok",
        "pipeline_ready": getattr(request.app.state, "pipeline", None) is not None,
        "features": {
            "deid": config.ENABLE_DEID,
            "graph": config.ENABLE_GRAPH,
            "reranker": config.ENABLE_RERANKER,
            "factcheck": config.ENABLE_FACTCHECK,
        },
    }


@router.get("/pipeline/info")
def pipeline_info():
    """Mô tả các tầng để frontend hiển thị sơ đồ kiến trúc động."""
    return {
        "stages": [
            {"id": "deid", "name": "Khử định danh PHI", "enabled": config.ENABLE_DEID,
             "desc": "Ẩn danh Tên, ID, Ngày, SĐT (regex tiếng Việt)"},
            {"id": "route", "name": "Intent Router", "enabled": True,
             "desc": "Phân luồng Phác đồ (GraphRAG) / Bệnh án (Hybrid)"},
            {"id": "graph", "name": "Knowledge Graph", "enabled": config.ENABLE_GRAPH,
             "desc": "Entity Matching → Traversal → Triple Textualization (Neo4j/in-memory)"},
            {"id": "retrieve", "name": "Hybrid Retrieval", "enabled": True,
             "desc": "Vector + BM25 → RRF → Rerank (bge-reranker-v2-m3)"},
            {"id": "generate", "name": "LLM Generation", "enabled": True,
             "desc": "Gemini + citation-enforced prompting (SSE streaming)"},
            {"id": "factcheck", "name": "Med-FactCheck", "enabled": config.ENABLE_FACTCHECK,
             "desc": "Grounding check phát hiện ảo giác y khoa"},
            {"id": "reid", "name": "Re-identification", "enabled": config.ENABLE_DEID,
             "desc": "Khôi phục token PHI về giá trị gốc (local)"},
        ],
        "models": config.AVAILABLE_MODELS,
    }


@router.get("/models")
def get_models():
    _reset_usage_if_new_day()
    models = []
    with _usage_lock:
        for model_name, limit in MODEL_LIMITS.items():
            used = _model_usage.get(model_name, 0)
            models.append({
                "name": model_name,
                "used": used,
                "limit": limit,
                "usage_percent": _get_usage_percent(model_name),
            })
    return {"models": models, "usage_day": _usage_day}


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------
class ChatRequest(BaseModel):
    message: str
    model: Optional[str] = None
    api_key: Optional[str] = None


def _resolve_pipeline(req: ChatRequest, request: Request):
    selected_model = (req.model or config.DEFAULT_MODEL).strip()
    user_api_key = (req.api_key or "").strip()

    if user_api_key:
        try:
            return build_pipeline(api_key=user_api_key, model_name=selected_model), selected_model
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Không khởi tạo được pipeline với API key/model đã cung cấp. Lỗi: {e}")

    default_api_key = get_default_api_key()
    if not default_api_key:
        raise HTTPException(
            status_code=400,
            detail="Chưa cấu hình API key hệ thống (GEMINI_API_KEY/GOOGLE_API_KEY). Hãy dán API key vào ô nhập trên UI.",
        )
    try:
        return build_pipeline(api_key=default_api_key, model_name=selected_model), selected_model
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Không khởi tạo được pipeline mặc định. Lỗi: {e}")


@router.post("/chat")
def chat_endpoint(req: ChatRequest, request: Request):
    """Chat non-streaming (giữ tương thích)."""
    try:
        _reset_usage_if_new_day()
        if not (req.message or "").strip():
            raise HTTPException(status_code=400, detail="Câu hỏi trống.")

        pipeline, selected_model = _resolve_pipeline(req, request)
        result = pipeline.run(req.message)
        _increment_usage(selected_model)

        answer_text = (result.get("answer") or "").strip()
        if not answer_text:
            answer_text = "Hệ thống đã truy xuất tài liệu nhưng không tạo được câu trả lời. Vui lòng thử diễn đạt lại."

        # Giữ 'sources' dạng chuỗi cho tương thích ngược, thêm trường cấu trúc mới.
        legacy_sources = [
            f"[{s['file_name']}] {s['snippet']}" for s in result.get("sources", [])
        ]
        return {
            "answer": answer_text,
            "sources": legacy_sources,
            "citations": result.get("sources", []),
            "pipeline": result.get("pipeline", {}),
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/stream")
def chat_stream_endpoint(req: ChatRequest, request: Request):
    """Chat streaming qua Server-Sent Events (SSE)."""
    _reset_usage_if_new_day()
    if not (req.message or "").strip():
        raise HTTPException(status_code=400, detail="Câu hỏi trống.")

    pipeline, selected_model = _resolve_pipeline(req, request)

    def event_generator():
        try:
            for event in pipeline.stream(req.message):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                if event.get("type") == "done":
                    _increment_usage(selected_model)
        except Exception as e:
            err = {"type": "error", "data": str(e)}
            yield f"data: {json.dumps(err, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
