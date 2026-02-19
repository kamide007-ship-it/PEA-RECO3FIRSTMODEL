import os, json, urllib.request, logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class BaseLLMAdapter(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def generate(self, prompt: str, temperature: float = 0.7,
                 max_tokens: int = 1024,
                 system_prompt: str = "") -> Dict[str, Any]:
        """Returns { 'text': str, 'model': str, 'usage': dict|None }"""

class DummyAdapter(BaseLLMAdapter):
    def __init__(self, fixed_response: str = "これはダミー応答です。", **_kw):
        self._resp = fixed_response
    @property
    def name(self) -> str: return "dummy"
    def generate(self, prompt, temperature=0.7, max_tokens=1024, system_prompt=""):
        _ = (prompt, temperature, max_tokens, system_prompt)
        return {"text": self._resp, "model": "dummy-v1", "usage": None}

class ClaudeAdapter(BaseLLMAdapter):
    def __init__(self, api_key: Optional[str] = None, model: str = "claude-sonnet-4-5-20250929",
                 endpoint: str = "https://api.anthropic.com/v1/messages", **_kw):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
        self.model = model
        self.endpoint = endpoint
    @property
    def name(self) -> str: return "claude"
    def generate(self, prompt: str, temperature: float = 0.7, max_tokens: int = 1024, system_prompt: str = "") -> Dict[str, Any]:
        if not self.api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        payload = {
            "model": self.model,
            "max_tokens": int(max_tokens),
            "temperature": float(temperature),
            "system": system_prompt or "",
            "messages": [{"role": "user", "content": prompt}],
        }
        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(self.endpoint, data=data, method="POST")
            req.add_header("Content-Type", "application/json")
            req.add_header("x-api-key", self.api_key)
            req.add_header("anthropic-version", "2023-06-01")
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
            j = json.loads(raw)
            text_out = ""
            for item in j.get("content", []) or []:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_out += str(item.get("text", ""))
            return {"text": text_out, "model": str(j.get("model", self.model)), "usage": j.get("usage")}
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Claude API response: {e}")
            raise RuntimeError(f"Claude API response parsing failed: {e}")
        except urllib.error.HTTPError as e:
            logger.error(f"Claude API HTTP error {e.code}: {e.reason}")
            raise RuntimeError(f"Claude API error {e.code}: {e.reason}")
        except urllib.error.URLError as e:
            logger.error(f"Claude API network error: {e}")
            raise RuntimeError(f"Claude API network error: {e}")
        except (IOError, TimeoutError) as e:
            logger.error(f"Claude API IO/Timeout error: {e}")
            raise RuntimeError(f"Claude API IO/Timeout error: {e}")

class OpenAIAdapter(BaseLLMAdapter):
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o",
                 endpoint: str = "https://api.openai.com/v1/chat/completions", **_kw):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.model = model
        self.endpoint = endpoint
    @property
    def name(self) -> str: return "openai"
    def generate(self, prompt: str, temperature: float = 0.7, max_tokens: int = 1024, system_prompt: str = "") -> Dict[str, Any]:
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        payload = {"model": self.model, "messages": messages, "temperature": float(temperature), "max_tokens": int(max_tokens)}
        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(self.endpoint, data=data, method="POST")
            req.add_header("Content-Type", "application/json")
            req.add_header("Authorization", f"Bearer {self.api_key}")
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
            j = json.loads(raw)
            choice0 = (j.get("choices") or [{}])[0]
            msg = choice0.get("message") or {}
            text_out = str(msg.get("content", "")) if isinstance(msg, dict) else ""
            return {"text": text_out, "model": str(j.get("model", self.model)), "usage": j.get("usage")}
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse OpenAI API response: {e}")
            raise RuntimeError(f"OpenAI API response parsing failed: {e}")
        except urllib.error.HTTPError as e:
            logger.error(f"OpenAI API HTTP error {e.code}: {e.reason}")
            raise RuntimeError(f"OpenAI API error {e.code}: {e.reason}")
        except urllib.error.URLError as e:
            logger.error(f"OpenAI API network error: {e}")
            raise RuntimeError(f"OpenAI API network error: {e}")
        except (IOError, TimeoutError) as e:
            logger.error(f"OpenAI API IO/Timeout error: {e}")
            raise RuntimeError(f"OpenAI API IO/Timeout error: {e}")

def _resolve_auto() -> str:
    """環境変数から最適なアダプターを自動選択"""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "claude"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    return "dummy"

def create_adapter(name: str = "dummy", **kwargs) -> BaseLLMAdapter:
    if name == "auto":
        name = _resolve_auto()
    n = (name or "dummy").strip().lower()
    if n in ("dummy", "test"):
        return DummyAdapter(**kwargs)
    if n in ("claude", "anthropic"):
        return ClaudeAdapter(**kwargs)
    if n in ("openai", "gpt"):
        return OpenAIAdapter(**kwargs)
    raise ValueError(f"Unknown adapter: {name}")
