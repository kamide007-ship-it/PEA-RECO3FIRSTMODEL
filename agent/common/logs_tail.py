"""Log file tailing for RECO3 PC Agent.
Watches specified log files and extracts ERROR/WARN entries.
"""

import logging
import os
import re
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Pattern to detect log levels in log lines
_LEVEL_PATTERN = re.compile(
    r"\b(ERROR|CRITICAL|FATAL|WARN(?:ING)?|INFO|DEBUG)\b", re.IGNORECASE
)

# Pattern to detect anomalies in output (NaN, inf, threshold)
_ANOMALY_PATTERN = re.compile(
    r"\b(nan|inf|-inf|NaN|Infinity|threshold exceeded|drift detected)\b", re.IGNORECASE
)


class LogTail:
    """Tails multiple log files and buffers ERROR/WARN entries."""

    def __init__(self, file_paths: list):
        self.file_paths = [p for p in file_paths if p]
        self._offsets = {}  # path -> last read offset
        for path in self.file_paths:
            if os.path.exists(path):
                # Start at end of file (don't replay history)
                self._offsets[path] = os.path.getsize(path)
            else:
                self._offsets[path] = 0

    def get_new_entries(self) -> list:
        """Read new lines from all watched files, return ERROR/WARN entries."""
        entries = []
        for path in self.file_paths:
            try:
                entries.extend(self._read_file(path))
            except Exception as e:
                logger.warning(f"Error reading {path}: {e}")
        return entries

    def _read_file(self, path: str) -> list:
        """Read new lines from a single file."""
        if not os.path.exists(path):
            return []

        current_size = os.path.getsize(path)
        offset = self._offsets.get(path, 0)

        # File was truncated/rotated
        if current_size < offset:
            offset = 0

        if current_size == offset:
            return []

        entries = []
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            f.seek(offset)
            for line in f:
                line = line.strip()
                if not line:
                    continue

                level_match = _LEVEL_PATTERN.search(line)
                level = level_match.group(1).upper() if level_match else "INFO"

                # Normalize WARN → WARNING → WARN
                if level.startswith("WARN"):
                    level = "WARN"
                if level == "FATAL":
                    level = "CRITICAL"

                # Only keep ERROR/WARN/CRITICAL
                if level in ("ERROR", "WARN", "CRITICAL"):
                    entries.append({
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "level": level,
                        "code": _extract_code(line),
                        "msg": line[:500],  # truncate long lines
                        "meta": {"file": path},
                    })

                # Also check for anomalies
                anomaly_match = _ANOMALY_PATTERN.search(line)
                if anomaly_match and level not in ("ERROR", "WARN", "CRITICAL"):
                    entries.append({
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "level": "WARN",
                        "code": "OUTPUT_ANOMALY",
                        "msg": line[:500],
                        "meta": {"file": path, "anomaly": anomaly_match.group(1)},
                    })

            self._offsets[path] = f.tell()

        return entries


def _extract_code(line: str) -> str:
    """Try to extract an error code from a log line."""
    # Common patterns: [ERR_CODE], (ERR_CODE), ERR-1234
    code_match = re.search(r"[\[\(]([A-Z_]{3,}[\d]*(?:_[A-Z_\d]+)*)[\]\)]", line)
    if code_match:
        return code_match.group(1)
    return ""
