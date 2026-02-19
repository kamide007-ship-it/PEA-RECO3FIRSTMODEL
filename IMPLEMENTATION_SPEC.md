# RECO3 B2B/BtoC 実装仕様書

## ✅ 目的
現状のRECO3を、BtoB/BtoC両方で販売できるレベルに引き上げる。
「提案(Pull) → Good/Bad評価 → 自己学習 → 精度向上」ループを回す販売可能なシステムに拡張する。
PC + Web をこのアプリ単体で統合モニタリングできるように。
既存構成は壊さず、**差分で追加実装**する。

## 🎯 最重要思想（固定）
- **「止めない」がデフォルト** → 自動停止を使わない
- **「提案」と「通知」が中心** → Human-in-the-loop
- **実行は「承認付き」または「明示ON」のルールのみ**
- **監査ログ必須** → いつ・何を観測・何を提案・どう評価・どう学習したか

## 📐 全体アーキテクチャ（2モード）

### モードA（BtoC向け・軽量）: PWA のみ
- Web監視（HTTP/ステータス/応答時間/エラーレート）
- AI提案（ルール+LLM）
- Good/Bad通知と評価
- 統計ベース自己学習

### モードB（BtoB向け・強化）: PWA + PC Agent（任意）
- PC監視（プロセス/CPU/MEM/DISK/NET/ログ/異常検知）
- Web監視（同上）
- 制御はデフォルト提案のみ
- 実行は「承認付き」または「allowlist」のみ
- 監査ログ/RBAC/閉域運用対応

---

## 🗄️ 1. データモデル（SQLite）

### テーブル定義

```sql
-- 1. observations（観測記録）
CREATE TABLE observations (
  id TEXT PRIMARY KEY,
  ts DATETIME NOT NULL,
  source_type TEXT NOT NULL,  -- 'pc', 'web', 'ai'
  source_id TEXT NOT NULL,     -- URL ID or process name or 'ai_analysis'
  kind TEXT NOT NULL,          -- 'metric', 'log', 'output', 'health'
  payload_json TEXT NOT NULL,  -- JSON: {status_code, latency_ms, error_msg, etc}
  org_id TEXT,                 -- multi-tenant
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_obs_ts_source ON observations(ts, source_type);

-- 2. incidents（異常事象）
CREATE TABLE incidents (
  id TEXT PRIMARY KEY,
  ts_open DATETIME NOT NULL,
  ts_close DATETIME,
  severity TEXT NOT NULL,      -- 'low', 'medium', 'high', 'critical'
  title TEXT NOT NULL,
  summary TEXT,
  status TEXT NOT NULL,        -- 'open', 'ack', 'closed'
  root_cause TEXT,             -- 原因の仮説
  observation_ids TEXT,        -- JSON array: [obs_id1, obs_id2, ...]
  org_id TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_inc_ts_status ON incidents(ts_open, status);

-- 3. suggestions（提案）
CREATE TABLE suggestions (
  id TEXT PRIMARY KEY,
  incident_id TEXT NOT NULL,
  ts DATETIME NOT NULL,
  suggestion_type TEXT,        -- 'rule_based', 'ai_generated'
  action_json TEXT,            -- {action: 'SET_RATE_LIMIT', params: {...}}
  rationale TEXT,              -- 理由・説明
  confidence REAL,             -- 0.0 - 1.0
  status TEXT NOT NULL,        -- 'pending', 'accepted', 'rejected', 'applied'
  priority INT DEFAULT 0,      -- 学習により動的更新
  org_id TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(incident_id) REFERENCES incidents(id)
);
CREATE INDEX idx_sug_incident_status ON suggestions(incident_id, status);

-- 4. feedback（ユーザー評価）
CREATE TABLE feedback (
  id TEXT PRIMARY KEY,
  suggestion_id TEXT NOT NULL,
  user_id TEXT,                -- optional, anonymous OK
  vote TEXT NOT NULL,          -- 'good', 'bad'
  comment TEXT,                -- ユーザーコメント
  org_id TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(suggestion_id) REFERENCES suggestions(id)
);
CREATE INDEX idx_fb_suggestion ON feedback(suggestion_id);

-- 5. learn_rules（学習規則・統計）
CREATE TABLE learn_rules (
  id TEXT PRIMARY KEY,
  rule_key TEXT UNIQUE NOT NULL,  -- 'incident_severity_threshold', 'suggestion_priority_ai_good_ratio', etc
  enabled BOOLEAN DEFAULT TRUE,
  threshold_json TEXT,        -- {min_good_ratio: 0.7, bad_count_threshold: 5, ...}
  version INT DEFAULT 1,
  updated_ts DATETIME DEFAULT CURRENT_TIMESTAMP,
  notes TEXT,
  org_id TEXT
);

-- 6. models（ML モデル・成果物）
CREATE TABLE models (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,         -- 'suggestion_ranker_v1', 'incident_classifier_v1'
  version INT NOT NULL,
  artifact_path TEXT,         -- S3/ローカルパスまたはJSON embed
  updated_ts DATETIME DEFAULT CURRENT_TIMESTAMP,
  notes TEXT,
  org_id TEXT
);

-- 7. web_targets（Web監視対象）
CREATE TABLE web_targets (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  url TEXT NOT NULL,
  method TEXT DEFAULT 'GET',  -- 'GET', 'POST', 'HEAD'
  interval_sec INT DEFAULT 300,
  expected_status INT DEFAULT 200,
  expected_latency_ms INT DEFAULT 1000,
  enabled BOOLEAN DEFAULT TRUE,
  tags TEXT,                  -- JSON array: ['critical', 'payment', ...]
  org_id TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 8. agent_status（PC Agent ハートビート）
CREATE TABLE agent_status (
  agent_id TEXT PRIMARY KEY,
  last_seen DATETIME NOT NULL,
  payload_json TEXT,          -- {hostname, version, capabilities, ...}
  org_id TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 9. audit_log（監査ログ）
CREATE TABLE audit_log (
  id TEXT PRIMARY KEY,
  ts DATETIME NOT NULL,
  actor TEXT NOT NULL,        -- 'user:email', 'system:scheduler', 'agent:agent_id'
  event_type TEXT NOT NULL,   -- 'create_incident', 'create_suggestion', 'feedback_vote', 'rule_update', 'apply_action'
  ref_id TEXT,                -- incident_id, suggestion_id, etc
  payload_json TEXT,          -- {old_value, new_value, reason, ...}
  org_id TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_audit_ts ON audit_log(ts);
```

---

## 🌐 2. Web監視機能（アプリ単体）

### 2.1 スケジューラー
```python
# reco2/web_monitor_scheduler.py (新規)
def monitor_web_targets():
    """
    web_targets テーブルから enabled=TRUE の対象を取得
    → 周期的に HTTP GET/POST
    → observations テーブルに記録
    → 異常判定で incidents を生成/更新
    """
    # 実装方法:
    # - Option A: APScheduler （簡易でOK）
    # - Option B: リクエストトリガー + background thread （最小依存）
    # - Option C: Flask apscheduler extension

    for target in web_targets.list(enabled=True):
        result = http_check(target.url, timeout=target.expected_latency_ms)
        observations.create(
            source_type='web',
            source_id=target.id,
            kind='metric',
            payload_json={
                'status_code': result.status_code,
                'latency_ms': result.elapsed_ms,
                'body_length': len(result.body),
                'success': result.status_code == target.expected_status,
            }
        )

        # 異常判定
        if not result.success:
            incidents.create_or_update(
                target_id=target.id,
                severity='high' if result.status_code >= 500 else 'medium',
                title=f"{target.name}: HTTP {result.status_code}",
                ...
            )
```

### 2.2 Web監視API
```python
# app.py に追加

# CRUD
POST /api/web-targets              # 新規登録
GET /api/web-targets               # 一覧
GET /api/web-targets/{id}          # 詳細
PUT /api/web-targets/{id}          # 編集
DELETE /api/web-targets/{id}       # 削除

# 手動チェック
POST /api/web-targets/{id}/check   # 即座にチェック実行
```

---

## 📍 3. PC監視（Agent任意）

### 3.1 既存Agent API維持・強化
```python
# 既存維持:
POST /agent/heartbeat    # Agent→Server: 生存信号
GET /agent/pull          # Agent←Server: タスク取得
POST /agent/logs         # Agent→Server: ログ送信

# 追加:
POST /api/agent/register          # Agent登録
GET /api/agent/status             # Agent一覧
PUT /api/agent/{id}/config        # 監視設定変更
```

### 3.2 データ流：Agent→Server
Agent から以下を受信 → observations テーブルに保存：
- CPU/MEM/DISK/NET メトリクス
- システムログ
- プロセス異常
- ネットワーク接続異常

---

## 💡 4. 「止めない」提案（Pull）システム

### 4.1 提案生成フロー
```
incident open
  ↓
[Rule-based suggestion] + [AI suggestion]
  ↓
suggestions テーブルに保存（status='pending'）
  ↓
PWA に通知
  ↓
User: Good / Bad 評価
  ↓
feedback テーブルに保存
  ↓
（オプション）Apply ボタン（承認付き実行）
```

### 4.2 提案の種類

#### A. Rule-based（安全・再現性高い）
```python
# reco2/rule_engine.py (新規/拡張)
def generate_rule_suggestions(incident):
    """
    ルールマッチングで提案を生成
    例:
      - "HTTP 503" → "Consider restart service"
      - "CPU > 90%" → "Kill non-critical process"
      - "404 rate > 10%" → "Check recent deployment"
    """
    suggestions = []

    if incident.kind == 'http_5xx':
        suggestions.append({
            'action': 'NOTIFY_OPS',
            'rationale': 'High error rate detected',
            'confidence': 0.95,
        })

    return suggestions
```

#### B. AI提案（LLM）
```python
# reco2/ai_suggestion.py (新規)
def generate_ai_suggestions(incident, observations, feedback_history):
    """
    - incident の内容
    - 関連する observations（メトリクス、ログ）
    - 過去の feedback（Good/Bad パターン）

    → Claude/OpenAI に送信
    → 原因推定 & 対応案を生成

    ⚠️ "提案"のみ。実行はしない。
    """
    prompt = f"""
    インシデント: {incident.title}
    観測データ: {observations}
    過去の評価: {feedback_history}

    このインシデントの考えられる原因と対応案を提案してください。
    """

    response = llm.generate(prompt, ...)

    suggestion = {
        'suggestion_type': 'ai_generated',
        'rationale': response,
        'confidence': 0.7,  # AIは certainty が低い
        'action': None,     # 実行を伴わない提案
    }

    return suggestion
```

### 4.3 Suggestions API
```python
POST /api/incidents/{id}/suggestions       # 新規生成（手動トリガー）
GET /api/incidents/{id}/suggestions        # 一覧
GET /api/suggestions/{id}                  # 詳細
```

---

## 👍 5. Good/Bad評価UI（最重要）

### 5.1 PWA(/r3) に追加

#### Incidents セクション
```
[Open] | [Ack] | [Closed]

┌─ HTTP 503 on api.example.com (High)
│  ├─ Opened: 2min ago
│  ├─ Observations: 5 errors in last 10min
│  └─ [View Details] [Acknowledge] [Close]
│
└─ CPU > 90% on web-server-01
   ├─ Opened: 15min ago
   ├─ Observations: sustained high usage
   └─ [View Details] ...
```

#### Incident詳細
```
Title: HTTP 503 on api.example.com
Severity: HIGH
Status: Open

Observations Timeline:
  15:32 HTTP 503, latency 5000ms
  15:29 HTTP 200, latency 200ms
  15:26 HTTP 200, latency 180ms

Suggestions:
  ┌─ Rule-based: "Restart API service"
  │  Confidence: 95%
  │  Rationale: 503 error indicates service overload or crash
  │  [👍 GOOD] [👎 BAD] [Write comment...]
  │
  └─ AI: "Check recent deployment logs for errors"
     Confidence: 72%
     Rationale: Assuming recent code change caused memory leak...
     [👍 GOOD] [👎 BAD] [Write comment...]

Action Log:
  14:32 Incident opened
  14:45 2 suggestions generated
  14:50 User voted GOOD on "Restart API service"
```

### 5.2 実装詳細
```python
# templates/reco3.html + static/reco3.js に追加

# Good/Bad ボタン実装
POST /api/feedback
  {
    "suggestion_id": "sug_123",
    "vote": "good",  # or "bad"
    "comment": "This suggestion was helpful"
  }

# 画面内サイレント通知
onFeedbackSubmitted() {
  showToast("✓ Feedback saved", duration=2s, silent=true);
}
```

---

## 🧠 6. 自己学習（段階導入）

### 6.1 v1（即実装）: 統計ベース
```python
# reco2/learning_v1.py (新規)
def run_learning_job():
    """
    毎日 or 一定件数ごと に実行
    """

    # 1. Good/Bad 集計
    feedback_summary = feedback.aggregate(
        group_by='suggestion_type',
        period='7d'  # 過去7日
    )
    # → {
    #     'rule_based': {'total': 50, 'good': 45, 'bad': 5, 'good_ratio': 0.90},
    #     'ai_generated': {'total': 30, 'good': 18, 'bad': 12, 'good_ratio': 0.60}
    #   }

    # 2. ルール更新
    # "Rule-based" は Good ratio が高い
    # → 優先度UP、しきい値厳しく

    # "AI generated" は Good ratio が低い
    # → 優先度DOWN、confidence threshold UP

    # 3. 「似たincident」に対して過去Goodの提案を優先提示
    # （最初は URL/プロセス名マッチでOK）

    # 4. 結果を audit_log に記録
    audit_log.create(
        event_type='rule_update',
        payload_json={
            'old_rule_key': 'suggestion_type_priority',
            'old_value': {'rule_based': 1, 'ai_generated': 2},
            'new_value': {'rule_based': 1, 'ai_generated': 3},
            'reason': 'AI good_ratio dropped to 0.60',
        }
    )
```

### 6.2 v2（後段）: ML ベース
- 特徴量: incident 種別、メトリクス推移、ログコード、対象URL/プロセス名
- モデル: 軽量分類（good になりそうな提案のランキング）
- 学習: サーバー側でバッチ（夜間）

---

## 🔒 7. 実行（Apply）は「承認付き」で限定

### 7.1 実行可能なアクション（allowlist）
```python
ALLOWED_ACTIONS = {
    'SET_MODE': {
        'params': ['SAFE', 'NORMAL'],
        'requires_approval': True,
        'description': 'Switch operation mode'
    },
    'SET_RATE_LIMIT': {
        'params': ['target_id', 'limit_rps'],
        'requires_approval': True,
        'description': 'Set rate limit on endpoint'
    },
    'RESTART_PROCESS': {
        'params': ['process_name'],
        'requires_approval': True,
        'whitelist': ['nginx', 'api_service'],  # 明示的ホワイトリスト
        'description': 'Restart specified process'
    },
    'NOTIFY_OPS': {
        'params': [],
        'requires_approval': False,  # 通知のみ
        'description': 'Send alert to ops team'
    },
}
```

### 7.2 承認フロー
```python
# POST /api/suggestions/{id}/apply
# → 承認リクエスト生成
# → 管理者 UI で approve / reject
# → apply_log に記録

POST /api/suggestions/{id}/apply
  {
    "requester_id": "user_123",
    "action": "RESTART_PROCESS",
    "params": {"process_name": "nginx"}
  }

  Response: {
    "approval_request_id": "apr_123",
    "status": "pending",
    "expires_at": "2026-02-20T12:00:00Z"
  }

# 管理者
POST /api/approval-requests/{id}/approve
  {
    "approver_id": "admin_456",
    "comment": "Approved, proceeding with restart"
  }

  → audit_log に記録
  → 実行（agent に指示）
```

### 7.3 デフォルト設定
```python
# config.json に追加
{
  "apply_actions_enabled": false,  # デフォルト: 承認機能OFF
  "auto_apply_enabled": false,     # デフォルト: 自動実行OFF
  "allowed_auto_actions": [],      # 自動実行可能なアクション（明示指定）
}
```

---

## 📦 8. BtoB / BtoC パッケージング

### BtoC（軽量）
- PWA のみ
- Web監視（3 URL まで）
- ルール + AI 提案（confidence threshold 高い）
- Good/Bad 学習（個人レベル）
- 承認・実行機能: OFF

### BtoB（強化）
- PWA + Agent（任意導入）
- Web監視（無制限）
- PC監視（Agent経由）
- ルール + AI 提案
- Good/Bad 学習（チーム・組織レベル）
- 承認・実行機能: ON（allowlist 限定）
- 監査ログ完全保持
- RBAC / Slack 連携
- 閉域運用対応（ログ転送先選択可）

---

## 📖 9. ドキュメント更新

### README.md
- "止めない（提案中心）" が基本思想であることを明記
- "Good/Bad評価で自己学習" がコア機能
- PC Agent は任意（Web監視だけで動作）
- Datadog等との共存、責任分界

### /spec
- Web監視仕様
- フィードバック・学習仕様
- 段階導入（v1: 統計、v2: ML）

### /tech
- API 一覧
- データスキーマ（observations, incidents, suggestions, feedback）
- 学習ジョブ
- 承認フロー
- マルチテナント対応

### /b2b
- 制御基盤
- 承認ワークフロー
- チーム学習
- 監査ログ
- オンプレ/閉域対応

---

## ✅ 完了条件（MVP）

### Phase 1: Web監視 + 提案 + Good/Bad 学習
- [x] Web監視が動く（web_targets登録 → 周期チェック → incident生成）
- [x] incident に対する suggestions（ルール + AI）が生成される
- [x] PWA で Good/Bad 評価でき、feedback テーブルに保存される
- [x] 過去 Good 提案が次回優先表示される（簡易ランキング学習）
- [x] 監査ログが全操作を追える

### Phase 2: 承認付き実行（オプション）
- [ ] allowlist 操作のみ実行可能
- [ ] 承認リクエスト → 承認者 UI → 実行
- [ ] apply_log に全て記録

### Phase 3: PC Agent 統合（BtoB）
- [ ] Agent との連携
- [ ] PC メトリクス → observations
- [ ] Process control（allowlist + 承認付き）

---

## 🏗️ 実装ロードマップ（優先順）

| Phase | 期間 | 内容 | MVP完了後 |
|-------|------|------|---------|
| **1** | 2-3週 | Web監視 + 提案 + Good/Bad | MVP ✓ |
| **2** | 1-2週 | B2B/B2C パッケージング | MVP ✓ |
| **3** | 2-3週 | 承認付き実行 | 後段 |
| **4** | 2-3週 | PC Agent 統合 | 後段 |
| **5** | 後段 | ML 学習（v2） | 後段 |

