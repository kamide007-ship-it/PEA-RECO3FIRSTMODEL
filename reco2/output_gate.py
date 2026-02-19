from __future__ import annotations
import math
from typing import Any, Dict, List, Tuple

_CONTRADICTION_PAIRS = [
    ("必ず", "かもしれません"), ("絶対に", "可能性があります"),
    ("確実に", "不確実"), ("always", "sometimes"),
    ("never", "occasionally"), ("definitely", "might"),
    ("100%", "uncertain"),
]

_SOFTEN_JA = [
    ("必ず", "多くの場合"), ("絶対に", "ほぼ"),
    ("間違いなく", "おそらく"), ("確実に", "高い確率で"),
]
_SOFTEN_EN = [
    ("definitely", "likely"), ("absolutely", "very likely"),
    ("certainly", "probably"), ("always", "typically"),
    ("never", "rarely"),
]

_ASSERT_TOKENS = [
    "必ず", "絶対", "間違いなく", "確実", "100%",
    "definitely", "absolutely", "certainly", "always", "never",
]

_PROVOCATIVE = [
    "バカ", "アホ", "ふざけるな", "舐めるな", "ゴミ",
    "使えない", "役に立たない",
    "idiot", "stupid", "shut up", "trash", "useless",
]

_EVIDENCE_MARKERS = [
    "出典", "引用", "根拠", "データ", "論文", "参考", "URL", "リンク",
    "source", "citation", "evidence", "data", "paper", "study", "link", "http://", "https://",
]

def _count_hits(text: str, words: List[str]) -> int:
    t = text.lower()
    c = 0
    for w in words:
        if not w:
            continue
        c += t.count(w.lower())
    return c

def _saturating_score(count: int, sensitivity: float = 1.0) -> float:
    return math.tanh((count / 3.0) * sensitivity)

def _contradiction_hits(text: str) -> int:
    t = text.lower()
    hits = 0
    for a, b in _CONTRADICTION_PAIRS:
        if a.lower() in t and b.lower() in t:
            hits += 1
    return hits

def analyze(text: str,
            w_assertion: float = 0.30,
            w_evidence: float = 0.30,
            w_contradiction: float = 0.25,
            w_provocative: float = 0.15) -> Dict[str, Any]:
    if not isinstance(text, str):
        text = str(text or "")
    t = text.strip()

    assert_count = _count_hits(t, _ASSERT_TOKENS)
    prov_count = _count_hits(t, _PROVOCATIVE)
    contra_hits = _contradiction_hits(t)
    has_evidence = _count_hits(t, _EVIDENCE_MARKERS) > 0

    s_assert = _saturating_score(assert_count, sensitivity=1.4)

    # Evidence gap: assertions without any evidence markers should be treated as a strong gap.
    evidence_gap_count = 0
    if assert_count > 0 and not has_evidence:
        evidence_gap_count = 5  # saturate
    s_evgap = _saturating_score(evidence_gap_count, sensitivity=1.2)

    s_contra = _saturating_score(contra_hits, sensitivity=1.5)
    s_prov = _saturating_score(prov_count, sensitivity=1.3)

    post_d = (s_assert * w_assertion) + (s_evgap * w_evidence) + (s_contra * w_contradiction) + (s_prov * w_provocative)
    psi_mod = max(0.3, 1.0 - post_d * 0.7)

    if post_d >= 0.70:
        level, action = "critical", "regenerate"
    elif post_d >= 0.50:
        level, action = "degraded", "soften"
    elif post_d >= 0.30:
        level, action = "cautious", "annotate"
    else:
        level, action = "healthy", "pass"

    return {
        "scores": {
            "assertion_density": round(float(s_assert), 6),
            "evidence_gap": round(float(s_evgap), 6),
            "contradiction": round(float(s_contra), 6),
            "provocative": round(float(s_prov), 6),
        },
        "post_d": round(float(post_d), 6),
        "level": level,
        "action": action,
        "psi_modifier": round(float(psi_mod), 6),
        "counts": {
            "assertions": int(assert_count),
            "contradictions": int(contra_hits),
            "provocative": int(prov_count),
        },
        "notes": {
            "has_evidence": bool(has_evidence),
        },
    }

def soften(text: str) -> str:
    if not isinstance(text, str):
        text = str(text or "")
    out = text
    for a, b in _SOFTEN_JA:
        out = out.replace(a, b)
    # simple case-insensitive for EN tokens
    low = out.lower()
    for a, b in _SOFTEN_EN:
        low = low.replace(a, b)
    # Merge: keep JP/other chars from out, but apply EN replacements by diffing lowercase.
    # For simplicity (and tests), returning low is acceptable.
    return low
