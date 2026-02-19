import os, json, urllib.request, urllib.error, logging
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, Any, Optional, Tuple
from reco3_agent.state import load_state, save_state, record_session
from reco3_agent.agent_gate import evaluate_input, evaluate_output

logger = logging.getLogger(__name__)

def _read_body(handler: BaseHTTPRequestHandler) -> bytes:
    n = int(handler.headers.get("Content-Length", "0") or "0")
    return handler.rfile.read(n) if n > 0 else b""

def _json_response(handler: BaseHTTPRequestHandler, code: int, payload: Dict[str, Any]) -> None:
    b = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(b)))
    handler.end_headers()
    handler.wfile.write(b)

def _forward(method: str, url: str, body: bytes, headers: Dict[str, str]) -> Tuple[int, Dict[str, str], bytes]:
    req = urllib.request.Request(url, data=body if method in ("POST", "PUT") else None, method=method)
    for k, v in headers.items():
        if k.lower() in ("host", "content-length"):
            continue
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.getcode(), dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        logger.info(f"HTTP error {e.code} from {url}")
        return e.code, dict(e.headers), e.read()
    except urllib.error.URLError as e:
        logger.error(f"Network error forwarding to {url}: {e}")
        return 502, {}, json.dumps({"error": "proxy_failed", "detail": str(e)}).encode("utf-8")
    except (IOError, TimeoutError) as e:
        logger.error(f"IO/Timeout error forwarding to {url}: {e}")
        return 502, {}, json.dumps({"error": "proxy_failed", "detail": str(e)}).encode("utf-8")
    except Exception as e:
        logger.error(f"Unexpected error in _forward for {url}: {e}")
        return 502, {}, json.dumps({"error": "proxy_failed", "detail": str(e)}).encode("utf-8")

def _extract_user_text(payload: Dict[str, Any]) -> Optional[str]:
    if isinstance(payload.get("messages"), list):
        for m in reversed(payload["messages"]):
            if isinstance(m, dict) and m.get("role") == "user":
                c = m.get("content")
                if isinstance(c, str):
                    return c
                if isinstance(c, list):
                    parts = []
                    for it in c:
                        if isinstance(it, dict) and it.get("type") in ("text", "input_text"):
                            parts.append(str(it.get("text", "")) or str(it.get("content", "")))
                    if parts:
                        return "\n".join(parts)
    if isinstance(payload.get("prompt"), str):
        return payload.get("prompt")
    return None

def _rewrite_payload(payload: Dict[str, Any], new_text: str) -> Dict[str, Any]:
    p = dict(payload)
    if isinstance(p.get("messages"), list):
        msgs = []
        replaced = False
        for m in p["messages"]:
            if isinstance(m, dict) and m.get("role") == "user" and not replaced:
                nm = dict(m)
                nm["content"] = new_text
                msgs.append(nm)
                replaced = True
            else:
                msgs.append(m)
        p["messages"] = msgs
    elif "prompt" in p:
        p["prompt"] = new_text
    return p

class ProxyHandler(BaseHTTPRequestHandler):
    server_version = "RECO3Proxy/1.0"

    def do_POST(self):
        enabled = os.getenv("RECO3_ENABLED", "1") != "0"
        reco3_url = os.getenv("RECO3_APP_URL", "http://127.0.0.1:5001")
        target = os.getenv("RECO3_TARGET", "https://api.openai.com")

        body = _read_body(self)
        try:
            payload = json.loads(body.decode("utf-8") or "{}")
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse request JSON: {e}")
            payload = {}
        except (UnicodeDecodeError, ValueError) as e:
            logger.warning(f"Failed to decode request body: {e}")
            payload = {}

        st = load_state()
        st = record_session(st)
        save_state(st)

        if enabled:
            user_text = _extract_user_text(payload) or ""
            ev = evaluate_input(user_text, st, reco3_url)
            if ev.get("action") in ("block", "cool"):
                return _json_response(self, 403, {"error": "blocked", "reason": ev.get("action"), "analysis": ev})
            if ev.get("rewrite"):
                payload = _rewrite_payload(payload, ev.get("text", user_text))
                body = json.dumps(payload).encode("utf-8")

        url = target.rstrip("/") + self.path
        code, rh, rb = _forward("POST", url, body, dict(self.headers))

        if enabled:
            try:
                outj = json.loads(rb.decode("utf-8"))
                txt = ""
                if isinstance(outj.get("choices"), list) and outj["choices"]:
                    msg = outj["choices"][0].get("message") or {}
                    if isinstance(msg, dict):
                        txt = str(msg.get("content", ""))
                evaluate_output(txt, reco3_url)
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse output response JSON: {e}")
            except (UnicodeDecodeError, ValueError) as e:
                logger.warning(f"Failed to decode output response: {e}")
            except Exception as e:
                logger.error(f"Unexpected error evaluating output: {e}")

        self.send_response(code)
        for k, v in rh.items():
            if k.lower() in ("transfer-encoding", "content-encoding"):
                continue
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(rb)))
        self.end_headers()
        self.wfile.write(rb)

    def log_message(self, format, *args):
        return

def run_proxy(port: int = 8100, bind: str = "127.0.0.1"):
    httpd = HTTPServer((bind, int(port)), ProxyHandler)
    httpd.serve_forever()
