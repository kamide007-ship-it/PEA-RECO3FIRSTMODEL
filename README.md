# RECO3 - Flask Application

A Flask-based reasoning engine with dual LLM support (OpenAI GPT & Anthropic Claude) and configurable behavior analysis.

## Deployment on Render

### Required Environment Variables

- **`SECRET_KEY`** - Flask session secret (generate with `python -c "import secrets; print(secrets.token_hex(32))"`)

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

### Render Configuration

#### Start Command

```bash
gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --threads 4
```

#### Example Environment Variables Setup

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

## Local Development

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Set environment variables:
   ```bash
   export ANTHROPIC_API_KEY="your-key-here"
   export LLM_ADAPTER="anthropic"
   export ANTHROPIC_MODEL="claude-3-5-sonnet-latest"
   ```

3. Run locally:
   ```bash
   python app.py
   ```

Access at `http://localhost:5001`

## License

[Add your license here]
