"""
Bộ định tuyến ý định (Intent Router).

Phân loại truy vấn của bác sĩ thành 2 luồng chính của kiến trúc:
  - GUIDELINE : hỏi về phác đồ, hướng dẫn, tương tác thuốc, liều dùng, chẩn đoán
                chuẩn  -> ưu tiên GraphRAG + Hybrid trên y văn.
  - EHR       : hỏi/tóm tắt hồ sơ bệnh án của 1 bệnh nhân cụ thể
                -> ưu tiên Hybrid Search SOAP-aware trên bệnh án.

Dùng heuristic từ khoá (rẻ, nhanh, không gọi LLM). Trả về nhãn + điểm tin cậy +
lý do, để hiển thị minh bạch trên UI và log.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List


GUIDELINE = "guideline"
EHR = "ehr"

_GUIDELINE_KEYWORDS = [
    "phác đồ", "hướng dẫn", "guideline", "điều trị", "liều", "liều dùng",
    "tương tác thuốc", "chống chỉ định", "chỉ định", "tác dụng phụ",
    "chẩn đoán", "khuyến cáo", "tiêu chuẩn", "icd", "thuốc", "phối hợp thuốc",
    "cơ chế", "biến chứng", "tầm soát", "mục tiêu điều trị",
]

_EHR_KEYWORDS = [
    "bệnh án", "hồ sơ", "bệnh nhân", "ca bệnh", "tóm tắt", "diễn tiến",
    "tiền sử", "nhập viện", "xuất viện", "điều dưỡng", "cận lâm sàng",
    "báo cáo mổ", "khám lâm sàng", "soap", "ghi chú", "theo dõi",
]

_NAME_LIKE = re.compile(r"\b(?:bệnh nhân|bn|ông|bà)\b\s+[A-ZĐ]", re.IGNORECASE)


@dataclass
class RouteDecision:
    intent: str
    confidence: float
    reason: str
    scores: dict


def route(query: str) -> RouteDecision:
    text = (query or "").lower()

    g_hits: List[str] = [k for k in _GUIDELINE_KEYWORDS if k in text]
    e_hits: List[str] = [k for k in _EHR_KEYWORDS if k in text]

    g_score = len(g_hits)
    e_score = len(e_hits)

    # Nếu nhắc đến tên bệnh nhân cụ thể -> thiên về EHR.
    if _NAME_LIKE.search(query or ""):
        e_score += 1
        e_hits.append("tên bệnh nhân")

    if e_score > g_score:
        intent = EHR
        chosen, other = e_score, g_score
        reason = f"Phát hiện ngữ cảnh bệnh án: {', '.join(e_hits[:4])}"
    else:
        intent = GUIDELINE
        chosen, other = g_score, e_score
        if g_hits:
            reason = f"Phát hiện ngữ cảnh y văn/phác đồ: {', '.join(g_hits[:4])}"
        else:
            reason = "Không có tín hiệu bệnh án rõ ràng — mặc định truy xuất y văn/phác đồ"

    total = chosen + other
    confidence = 0.6 if total == 0 else min(0.99, 0.5 + 0.5 * (chosen / max(total, 1)))

    return RouteDecision(
        intent=intent,
        confidence=round(confidence, 2),
        reason=reason,
        scores={"guideline": g_score, "ehr": e_score},
    )
