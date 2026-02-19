from __future__ import annotations
import math
from typing import Any, Dict, List, Tuple

_AMBIGUITY_JA = [
    "なんか", "とか", "なんとなく", "適当に", "いい感じに", "うまく",
    "よしなに", "それっぽく", "ざっくり", "てきとう", "ふわっと",
    "なんでもいい", "おまかせ", "どうにか",
]
_AMBIGUITY_EN = [
    "something like", "somehow", "whatever", "kind of", "sort of",
    "just do it", "figure it out", "make it work",
    "anything", "stuff", "things",
]
_ASSERTION_JA = [
    "絶対", "必ず", "断言して", "確実に", "100%", "間違いない",
    "保証して", "確定で", "例外なく", "完全に正しい",
]
_ASSERTION_EN = [
    "absolutely", "definitely", "guarantee", "must be", "certainly",
    "without doubt", "100%", "always true", "never wrong", "prove that",
]
_EMOTION_JA = [
    "急いで", "今すぐ", "早く", "できないの", "使えない",
    "お願いだから", "頼むから", "なんで", "いい加減にして",
    "ふざけるな", "ちゃんとして", "まだ", "いつまで",
]
_EMOTION_EN = [
    "hurry", "asap", "right now", "useless",
    "please just", "why can't", "come on",
    "seriously", "for god's sake", "how hard can it be",
]
_UNREALISTIC_JA = [
    "全て解決", "完璧に", "一瞬で", "万能な", "無限に",
    "失敗しない", "バグのない", "最強の", "究極の", "永久に",
    "全自動で", "ワンクリックで", "何でもできる",
]
_UNREALISTIC_EN = [
    "solve everything", "perfect", "instantly", "omnipotent", "infinite",
    "never fail", "bug-free", "ultimate", "forever",
    "fully automatic", "one click", "do anything", "solve all",
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
    # Spec: tanh(count / 3.0 * sensitivity)
    return math.tanh((count / 3.0) * sensitivity)

def analyze(text: str,
            w_ambiguity: float = 0.20,
            w_assertion: float = 0.25,
            w_emotion: float = 0.30,
            w_unrealistic: float = 0.25) -> Dict[str, Any]:
    if not isinstance(text, str):
        text = str(text or "")

    # keyword hits
    c_amb = _count_hits(text, _AMBIGUITY_JA) + _count_hits(text, _AMBIGUITY_EN)
    c_ass = _count_hits(text, _ASSERTION_JA) + _count_hits(text, _ASSERTION_EN)
    c_emo = _count_hits(text, _EMOTION_JA) + _count_hits(text, _EMOTION_EN)
    c_unr = _count_hits(text, _UNREALISTIC_JA) + _count_hits(text, _UNREALISTIC_EN)

    # punctuation boosts (emotion/pressure)
    ex = text.count("!") + text.count("！")
    if ex:
        c_emo += min(3, ex)

    # sensitivities tuned so that 1-2 strong tokens lift risk (without over-triggering)
    s_amb = _saturating_score(c_amb, sensitivity=1.1)
    s_ass = _saturating_score(c_ass, sensitivity=1.8)
    s_emo = _saturating_score(c_emo, sensitivity=2.0)
    s_unr = _saturating_score(c_unr, sensitivity=1.8)

    pre_d = (s_amb * w_ambiguity) + (s_ass * w_assertion) + (s_emo * w_emotion) + (s_unr * w_unrealistic)

    # Escalation: multiple simultaneous pressures increase risk (interaction effect)
    active = sum(1 for x in (c_amb, c_ass, c_emo, c_unr) if x > 0)
    if active >= 3:
        pre_d = min(1.0, pre_d * 1.25)
    elif active == 2 and (c_emo > 0 and (c_ass > 0 or c_unr > 0)):
        pre_d = min(1.0, pre_d * 1.10)

    if pre_d >= 0.70:
        level, action, t_mod = "critical", "cool_down", 0.3
    elif pre_d >= 0.50:
        level, action, t_mod = "high", "conditional", 0.5
    elif pre_d >= 0.30:
        level, action, t_mod = "moderate", "clarify", 0.7
    else:
        level, action, t_mod = "low", "proceed", 1.0

    warnings = []
    if c_amb:
        warnings.append("曖昧な表現が含まれます")
    if c_ass:
        warnings.append("断定要求が含まれます")
    if c_emo:
        warnings.append("感情的圧力が検出されました")
    if c_unr:
        warnings.append("非現実的な前提が含まれます")

    return {
        "scores": {
            "ambiguity": round(float(s_amb), 6),
            "assertion_demand": round(float(s_ass), 6),
            "emotional_pressure": round(float(s_emo), 6),
            "unrealistic": round(float(s_unr), 6),
        },
        "pre_d": round(float(pre_d), 6),
        "risk_level": level,
        "action": action,
        "temperature_modifier": t_mod,
        "warnings": warnings,
    }

def rebuild_prompt(user_input: str, analysis: Dict[str, Any]) -> Tuple[str, str]:
    level = (analysis or {}).get("risk_level", "low")
    if level == "critical":
        return "", "critical"
    if level == "low":
        return user_input, "none"
    if level == "moderate":
        return "[指針: 不確実な点は明記し、根拠を添えて回答してください。]\n" + user_input, "moderate"
    return "[重要指針: 断定を避け、根拠を明示し、不明な点は「わかりません」と答えてください。]\n" + user_input, "high"