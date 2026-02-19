"""HTTP client for RECO3 Agent → Server communication."""

import logging
import time
import requests

logger = logging.getLogger(__name__)

# Exponential backoff constants
MAX_RETRIES = 4
BASE_BACKOFF_SEC = 2


class RECOHttpClient:
    """HTTP client with retry, timeout, and agent auth headers."""

    def __init__(self, base_url: str, agent_id: str, api_key: str, timeout: int = 15):
        self.base_url = base_url.rstrip("/")
        self.agent_id = agent_id
        self.api_key = api_key
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "X-AGENT-ID": self.agent_id,
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        })
        self._consecutive_failures = 0

    def get(self, path: str) -> dict:
        """GET request with retries."""
        return self._request("GET", path)

    def post(self, path: str, data: dict = None) -> dict:
        """POST request with retries."""
        return self._request("POST", path, json_data=data)

    def _request(self, method: str, path: str, json_data: dict = None) -> dict:
        url = f"{self.base_url}{path}"
        last_error = None

        for attempt in range(MAX_RETRIES + 1):
            try:
                if method == "GET":
                    resp = self.session.get(url, timeout=self.timeout)
                else:
                    resp = self.session.post(url, json=json_data, timeout=self.timeout)

                resp.raise_for_status()
                self._consecutive_failures = 0
                return resp.json()

            except requests.exceptions.ConnectionError as e:
                last_error = e
                logger.warning(f"Connection error {url} (attempt {attempt + 1}): {e}")
            except requests.exceptions.Timeout as e:
                last_error = e
                logger.warning(f"Timeout {url} (attempt {attempt + 1}): {e}")
            except requests.exceptions.HTTPError as e:
                last_error = e
                if e.response is not None and e.response.status_code == 401:
                    logger.error(f"Authentication failed: {url}")
                    raise
                logger.warning(f"HTTP error {url} (attempt {attempt + 1}): {e}")
            except Exception as e:
                last_error = e
                logger.error(f"Unexpected error {url}: {e}")
                raise

            # Exponential backoff
            if attempt < MAX_RETRIES:
                wait = BASE_BACKOFF_SEC * (2 ** attempt)
                logger.info(f"Retrying in {wait}s...")
                time.sleep(wait)

        self._consecutive_failures += 1
        raise ConnectionError(f"Failed after {MAX_RETRIES + 1} attempts: {last_error}")

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures
