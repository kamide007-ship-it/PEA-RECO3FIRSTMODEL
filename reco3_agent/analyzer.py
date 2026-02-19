from __future__ import annotations
import datetime, logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

_EMOTION = [
    "急いで", "今すぐ", "早く", "できない", "使えない", "お願い", "頼む", "なんで",
    "いい加減", "ふざけるな", "ちゃんとして", "まだ", "いつまで",
    "hurry", "asap", "right now", "useless", "seriously", "come on",
]

_OVERLOAD = [
    "全部", "大量", "無限", "いくらでも", "全部まとめて", "一気に", "全て",
    "all of", "tons of", "infinite", "everything", "as many as possible",
]

def _count_hits(text: str, words) -> int:
    t = (text or "").lower()
    c = 0
    for w in words:
        c += t.count(str(w).lower())
    return c

def score_emotional(text: str) -> float:
    c = _count_hits(text, _EMOTION)
    ex = (text or "").count("!") + (text or "").count("！")
    c += min(3, ex)
    return min(1.0, c / 3.0)

def score_overload(text: str) -> float:
    c = _count_hits(text, _OVERLOAD)
    return min(1.0, c / 3.0)

def _to_dt(ts: Any) -> datetime.datetime | None:
    if isinstance(ts, (int, float)):
        try:
            return datetime.datetime.fromtimestamp(float(ts))
        except (ValueError, OSError, OverflowError) as e:
            logger.debug(f"Failed to convert timestamp {ts} to datetime: {e}")
            return None
    if isinstance(ts, str):
        try:
            return datetime.datetime.fromisoformat(ts)
        except (ValueError, TypeError) as e:
            logger.debug(f"Failed to parse ISO format datetime {ts}: {e}")
            return None
    return None

def score_fatigue(state: Dict[str, Any]) -> float:
    now = datetime.datetime.now()

    # Night usage 23-05
    hour = now.hour
    night = 1.0 if (hour >= 23 or hour <= 5) else 0.0

    # burst: >20 sessions within 1 hour
    hist = state.get("session_history", []) or []
    cutoff = now - datetime.timedelta(hours=1)
    recent = 0
    for ts in hist:
        dt = _to_dt(ts)
        if dt and dt >= cutoff:
            recent += 1
    per_hour = 1.0 if recent > 20 else (recent / 20.0 if recent > 0 else 0.0)

    # daily: >50 per day
    today_key = now.date().isoformat()
    daily = int((state.get("daily_counts", {}) or {}).get(today_key, 0) or 0)
    per_day = 1.0 if daily > 50 else (daily / 50.0 if daily > 0 else 0.0)

    return max(night, per_hour, per_day)

def analyze_human(text: str, state: Dict[str, Any]) -> Dict[str, Any]:
    emo = score_emotional(text)
    ovl = score_overload(text)
    fat = score_fatigue(state or {})

    # Action is determined by content signals only (emotion + overload).
    # Fatigue alone should NOT block – it only promotes pass→warn and
    # applies a mild temperature reduction.
    content_max = max(emo, ovl)

    avg = (emo + ovl + fat) / 3.0
    composite = max(emo, ovl, fat) * 0.6 + avg * 0.4

    if content_max >= 0.75:
        action, t_mod = "cool", 0.3
    elif content_max >= 0.55:
        action, t_mod = "block", 0.4
    elif content_max >= 0.35:
        action, t_mod = "warn", 0.7
    else:
        action, t_mod = "pass", 1.0

    # Fatigue promotes pass→warn and reduces temperature mildly
    if fat > 0.5 and action == "pass":
        action = "warn"
        t_mod = 0.85

    return {
        "emotional": round(emo, 6),
        "overload": round(ovl, 6),
        "fatigue": round(fat, 6),
        "composite": round(composite, 6),
        "action": action,
        "temperature_modifier": t_mod,
    }
