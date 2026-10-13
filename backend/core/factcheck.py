"""
Med-FactCheck (grounding nhẹ).

Kiểm tra mức độ "bám nguồn" của câu trả lời so với ngữ cảnh đã truy xuất, nhằm
cảnh báo sớm nguy cơ ảo giác (hallucination) — đặc biệt nguy hiểm trong y khoa
(bịa liều, bịa chống chỉ định). Dùng độ trùng lắp từ khoá theo từng câu (rẻ,
không gọi thêm LLM). Đây là lớp cảnh báo hỗ trợ, KHÔNG thay thế thẩm định của
bác sĩ.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List

from core import config

_STOP = set("""
và là của có các một những được cho trong đã khi với này đó thì ở hay hoặc do nên
để về từ như theo cũng vẫn sẽ rất bị bởi mà ra vào lên xuống trên dưới sau trước
""".split())


def _tokens(text: str) -> set:
    toks = re.findall(
        r"[0-9a-zàáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵđ]+",
        (text or "").lower(),
    )
    return {t for t in toks if len(t) > 2 and t not in _STOP}


def _sentences(text: str) -> List[str]:
    parts = re.split(r"(?<=[.!?;:])\s+|\n+", text or "")
    return [p.strip() for p in parts if len(p.strip()) > 8]


@dataclass
class FactCheckResult:
    grounded_ratio: float = 1.0
    unsupported: List[str] = field(default_factory=list)
    checked_sentences: int = 0
    passed: bool = True
    note: str = ""


def check(answer: str, context_texts: List[str]) -> FactCheckResult:
    if not config.ENABLE_FACTCHECK or not answer or not context_texts:
        return FactCheckResult(note="bỏ qua (tắt hoặc thiếu dữ liệu)")

    ctx_tokens = set()
    for c in context_texts:
        ctx_tokens |= _tokens(c)

    if not ctx_tokens:
        return FactCheckResult(note="ngữ cảnh rỗng")

    sents = _sentences(answer)
    if not sents:
        return FactCheckResult(checked_sentences=0)

    grounded = 0
    unsupported: List[str] = []
    for s in sents:
        st = _tokens(s)
        if not st:
            grounded += 1
            continue
        shared = st & ctx_tokens
        overlap = len(shared) / len(st)
        # Câu dài cần >= 2 từ khoá trùng để tránh "ăn may" 1 từ phổ biến.
        min_shared = 2 if len(st) >= 5 else 1
        if overlap >= config.FACTCHECK_MIN_OVERLAP and len(shared) >= min_shared:
            grounded += 1
        else:
            unsupported.append(s)

    ratio = grounded / len(sents)
    passed = ratio >= 0.6
    note = "đạt" if passed else "cảnh báo: một số nội dung ít bám nguồn y văn"

    return FactCheckResult(
        grounded_ratio=round(ratio, 2),
        unsupported=unsupported[:5],
        checked_sentences=len(sents),
        passed=passed,
        note=note,
    )
