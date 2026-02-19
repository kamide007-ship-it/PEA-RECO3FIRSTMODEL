# RECO3 - Flask Application

A Flask-based reasoning engine with dual LLM support (OpenAI GPT & Anthropic Claude) and configurable behavior analysis.

## Deployment on Render

### Required Environment Variables

- **`SECRET_KEY`** - Flask session secret (generate with `python -c "import secrets; print(secrets.token_hex(32))"`)
  - **CRITICAL**: Required for PWA session authentication. Must be kept secret.
  - Sessions expire on server restart (development mode) or periodically in production.
  - If missing, defaults to dev key (UNSAFE for production).

### Optional API Keys

- **`OPENAI_API_KEY`** - OpenAI API key (for GPT models)
- **`ANTHROPIC_API_KEY`** - Anthropic API key (for Claude models)

### LLM Configuration Variables

Control which AI model is used and how "auto" selection works:

#### LLM Adapter Selection

- **`LLM_ADAPTER`** - `"auto"` | `"openai"` | `"anthropic"` | `"dummy"`
  - Default: `"auto"` (auto-selects based on available API keys)
  - `"auto"`: Automatically selects based on available keys and `AUTO_PREFERENCE`
  - `"openai"`: Forces OpenAI GPT (requires `OPENAI_API_KEY`)
  - `"anthropic"`: Forces Anthropic Claude (requires `ANTHROPIC_API_KEY`)
  - `"dummy"`: Test mode (no API key required)

#### Model Selection

- **`OPENAI_MODEL`** - OpenAI model identifier
  - Default: `"gpt-4o"`
  - Examples: `"gpt-4o-mini"`, `"gpt-4-turbo"`, etc.
  - Only used when adapter is `"openai"`

- **`ANTHROPIC_MODEL`** - Anthropic model identifier
  - Default: `"claude-sonnet-4-5-20250929"`
  - Examples: `"claude-3-5-sonnet-latest"`, `"claude-3-opus-latest"`, etc.
  - Only used when adapter is `"anthropic"`

#### Auto Selection Preference

- **`AUTO_PREFERENCE`** - `"anthropic_first"` | `"openai_first"`
  - Default: `"anthropic_first"`
  - When `LLM_ADAPTER="auto"` and both API keys are available:
    - `"anthropic_first"`: Prefers Claude
    - `"openai_first"`: Prefers OpenAI

### PWA Session Authentication

The `/r3` PWA interface uses server-side session authentication to protect `/api/r3/chat`:

1. User accesses `/r3` → Server sets `session["r3"]=True` → Session cookie sent to browser
2. Browser calls `/api/r3/chat` → Frontend sends cookie with `credentials: "include"` → Server validates session
3. If session is invalid/expired → Server returns 401 → Frontend shows "セッション切れ。ページを再読み込みしてください。"

**Important Notes:**
- Session data is stored server-side (not in cookie value)
- Session cookie is HttpOnly (cannot be accessed by JavaScript for security)
- CORS is single-origin (Render deployment assumes same domain)
- API keys are NOT embedded in frontend JavaScript

### API Key Protection Configuration

Control authentication for other API endpoints (PWA pages/static files are always public):

- **`API_KEY`** - The API key for protecting endpoints (required for enforce mode)
  - Generate with: `python -c "import secrets; print(secrets.token_hex(32))"`
  - **MUST** be kept secret and only set in Render (not in config.json or code)

- **`API_KEY_MODE`** - Authentication mode
  - Default: `"enforce"`
  - `"enforce"`: Require API key for /api/* endpoints
  - `"off"`: Disable authentication (development only)

- **`API_KEY_HEADER`** - HTTP header name to check for API key
  - Default: `"X-API-Key"`
  - Can be set to `"Authorization"` to use Bearer tokens instead

- **`API_KEY_BYPASS_PATHS`** - Comma-separated paths that don't require authentication
  - Default: `/, /r3, /health, /favicon.ico, /manifest.webmanifest, /static/manifest.webmanifest, /service-worker.js, /static/service-worker.js`
  - Use `/static/*` for all static files
  - Override this to customize which paths are public

#### Protected Endpoints

The following endpoints require a valid API_KEY when `API_KEY_MODE=enforce`:

- POST `/api/evaluate` - Payload evaluation
- POST `/api/feedback` - Record feedback
- POST `/api/patrol` - Trigger patrol
- GET `/api/status` - System status
- GET `/api/logs` - Session logs
- POST `/api/r3/chat` - Chat interface
- POST `/api/r3/analyze_input` - Input analysis
- POST `/api/r3/analyze_output` - Output analysis
- GET `/api/r3/config` - Configuration

#### Public Pages (No Authentication Required)

- GET `/` - Redirects to /r3
- GET `/r3` - PWA main interface
- GET `/static/*` - Static files (CSS, JS, images)
- GET `/health` - Health check

### Render Configuration

#### Start Command

```bash
gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --threads 4
```

#### Example Environment Variables Setup

**Complete Production Setup** (Claude with PWA session + API protection):
```
SECRET_KEY=<generate-with-python-secrets-module>
API_KEY=<generate-with-python-secrets-module>
ANTHROPIC_API_KEY=sk-ant-...
LLM_ADAPTER=anthropic
ANTHROPIC_MODEL=claude-3-5-sonnet-latest
API_KEY_MODE=enforce
API_KEY_HEADER=X-API-Key
```

**Minimal Setup** (Session auth for PWA only):
```
SECRET_KEY=<generate-with-python-secrets-module>
ANTHROPIC_API_KEY=sk-ant-...
LLM_ADAPTER=anthropic
ANTHROPIC_MODEL=claude-3-5-sonnet-latest
API_KEY_MODE=off
```

For **Anthropic Claude**:
```
LLM_ADAPTER=anthropic
ANTHROPIC_MODEL=claude-3-5-sonnet-latest
```

For **OpenAI GPT**:
```
LLM_ADAPTER=openai
OPENAI_MODEL=gpt-4o
```

For **Auto Selection** (Claude preferred if both keys exist):
```
LLM_ADAPTER=auto
AUTO_PREFERENCE=anthropic_first
```

For **Development** (disable all authentication):
```
API_KEY_MODE=off
```

## Configuration Priority

When determining LLM configuration, the system follows this priority order:

1. **Environment Variables** (highest priority)
   - `LLM_ADAPTER`, `OPENAI_MODEL`, `ANTHROPIC_MODEL`, `AUTO_PREFERENCE`
2. **instance/config.json**
   - `llm_adapter`, `llm_model` fields
3. **Built-in Defaults** (lowest priority)
   - OpenAI: `gpt-4o`
   - Claude: `claude-sonnet-4-5-20250929`

## API Endpoints

### Status Check
- **GET** `/api/status` - Returns current LLM configuration and system status
  ```json
  {
    "active_llm_adapter": "anthropic",
    "active_llm_model": "claude-3-5-sonnet-latest",
    "dual_keys": {
      "has_openai_key": false,
      "has_anthropic_key": true
    },
    ...
  }
  ```

### Health Check
- **GET** `/health` - Simple health status

### Chat API
- **POST** `/api/r3/chat` - Send a message for analysis and response

## API Usage Examples

### Testing Protected Endpoints

If `API_KEY_MODE=enforce` with `API_KEY=your-secret-key`:

**Without API key** (will fail with 401):
```bash
curl http://localhost:5001/api/status
# Response: {"error": "unauthorized"}
```

**With valid API key** (will succeed):
```bash
curl -H "X-API-Key: your-secret-key" http://localhost:5001/api/status
# Response: { "k": 1.5, "active_llm_adapter": "anthropic", ... }
```

**Using Authorization header instead**:
```bash
curl -H "Authorization: Bearer your-secret-key" http://localhost:5001/api/status
```

### Accessing Public Pages (No Key Required)

```bash
# PWA interface (always public)
curl http://localhost:5001/r3

# Static files (always public)
curl http://localhost:5001/static/manifest.json

# Health check (always public)
curl http://localhost:5001/health
```

### Making Chat Requests

```bash
API_KEY="your-secret-key"

curl -X POST http://localhost:5001/api/r3/chat \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "What is 2+2?",
    "domain": "general",
    "max_tokens": 1024
  }'
```

## Local Development

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Set environment variables (with auth disabled for dev):
   ```bash
   export ANTHROPIC_API_KEY="your-key-here"
   export LLM_ADAPTER="anthropic"
   export ANTHROPIC_MODEL="claude-3-5-sonnet-latest"
   export API_KEY_MODE=off
   ```

3. Run locally:
   ```bash
   python app.py
   ```

Access at `http://localhost:5001`

## Security Notes

- **Never** commit `SECRET_KEY`, `API_KEY`, or API keys to version control
- Use Render's **Environment Variables** to set these values
- `SECRET_KEY` must be at least 32 characters (generate: `python -c "import secrets; print(secrets.token_hex(32))"`)
- `API_KEY` should be a long random string (at least 32 characters)
- In production, always set `API_KEY_MODE=enforce` (the default)
- The `/r3` and `/static/*` paths are always public for PWA functionality
- `/api/r3/chat` requires valid server session (set by visiting `/r3` with cookies enabled)
- All other `/api/*` endpoints require a valid API key in enforce mode
- PWA service worker does NOT cache `/api/*` endpoints (ensures fresh data)

## License

[Add your license here]
