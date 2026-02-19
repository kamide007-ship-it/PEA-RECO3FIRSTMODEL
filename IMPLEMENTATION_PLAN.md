# RECO3 B2B/B2C 販売可能化 - 最短実装計画

**目標**: 最短でBtoB/BtoC両方で販売できるレベルに（エージェントは任意）

## 優先度別実装ロードマップ

### 🎯 優先度 1（最重要）: Good/Bad学習 + Web監視（Phase 2 + Phase 3）

**理由**:
- エージェントなしでもWeb監視だけで価値が出る
- Good/Badが販売の核（自己学習がセリングポイント）
- 学習ジョブで継続的に品質向上を実演できる

**実装内容**:

#### 1-1. Web監視API (CRUD + 定期ポーリング)
```python
# app.py に追加
POST /api/monitors           # 監視URL登録
GET /api/monitors            # 一覧表示
GET /api/monitors/{id}       # 詳細
PUT /api/monitors/{id}       # 編集
DELETE /api/monitors/{id}    # 削除
POST /api/monitors/{id}/poll # 手動トリガー

# バックグラウンド: 定期ポーリング (リクエストトリガでOK)
GET /api/monitor/poll (内部ジョブ)
```

**実装ファイル**:
- `reco2/web_monitor.py` (新規) - HTTP ポーリング、タイムアウト/リトライ
- `reco2/monitor_store.py` (新規) - 監視対象の永続化
- `app.py` (修正) - CRUD ルーティング
- `static/monitors.html` + `monitors.js` (新規) - 監視管理UI

**データスキーマ**:
```json
{
  "web_monitors": [
    {
      "id": "monitor_uuid",
      "url": "https://api.example.com/health",
      "interval_sec": 300,
      "enabled": true,
      "last_check": "2026-02-19T...",
      "status": "ok|fail",
      "results": [
        {"ts": "...", "status_code": 200, "latency_ms": 45, "success": true},
        ...
      ]
    }
  ]
}
```

**プラン制限**:
- B2C Free: 3 URL
- B2C Pro: 10 URL
- B2B: 無制限

#### 1-2. Good/Bad フィードバック強化 + 学習ジョブ
```python
# 既存の /api/feedback を拡張
POST /api/feedback
  {
    "target_type": "suggestion|alert|analysis",
    "target_id": "session_id",
    "rating": 1 (GOOD) | -1 (BAD),
    "reason_tags": ["too_sensitive", "missed_issue", "helpful", "noise"],
    "monitor_id": "monitor_uuid (optional)",
    "context": {...}
  }

# 新規
GET /api/feedback/stats     # フィードバック集計
POST /api/learning/jobs     # 学習ジョブ実行
GET /api/learning/jobs      # 学習履歴
```

**実装ファイル**:
- `reco2/learning_engine.py` (新規) - patrol()の高度化、重み更新
- `reco2/feedback_stats.py` (新規) - フィードバック集計
- `app.py` (修正) - 新APIエンドポイント
- `reco2/engine.py` (修正) - 学習コンテキスト統合

**学習ロジック（v1）**:
```
毎日 or 一定件数ごとにpatrol()実行：
  - BADが多いアラート種別 → 感度↓ / クールダウン↑
  - GOODが多い提案パターン → 優先表示
  - "missed_issue" が多い → 感度↑ / 監視間隔短縮

結果: k, η パラメータ更新 → 次回評価に反映
```

**UI追加** (`/r3` PWA):
- 提案カード・アラート行に 👍 GOOD / 👎 BAD ボタン
- 音なしトースト表示で即座フィードバック
- 学習進捗表示："N件のフィードバックから学習中"
- `/feedback-stats` セクション (ドメイン別改善率)

**期間**: 16-18営業日
**チーム**: バックエンド1 + フロントエンド0.5
**期待効果**: MVP完成、学習ループ実装済み

---

### 🎯 優先度 2（高）: B2B/B2C切替 + プラン制限（Phase 1 + Phase 5 の一部）

**理由**: 販売・課金の前提

**実装内容**:

#### 2-1. 環境変数ベース PRODUCT_MODE 切替
```python
# 環境変数
PRODUCT_MODE=B2B|B2C           # デフォルト: B2B (コンサバ)
PRICING_TIER=free|pro|enterprise # デフォルト: free
```

**実装ファイル**:
- `reco2/product_mode.py` (新規) - モード検出 + 機能ゲート
- `app.py` (修正) - PRODUCT_MODE チェックミドルウェア
- `reco2/config.py` (修正) - プラン定義

**機能ゲート**:
```python
# 全API endpoint に適用
@require_feature("web_monitoring")
def api_monitors(): ...

@require_feature("automation")
def execute_control(): ...

@require_feature("agent")
def agent_heartbeat(): ...
```

#### 2-2. ページ・UI分け
```
B2B:
  /b2b    → B2B 向け説明（既存）
  /pricing → プラン比較（新規）
  /r3     → 管理画面（エージェント・監視・制御 可視化）

B2C:
  /b2c    → B2C 向け説明（新規）
  /pricing → プラン比較（新規、B2Cフォーカス）
  /r3     → 簡易ダッシュ（Web監視 + Good/Bad）
```

**実装ファイル**:
- `templates/b2c.html` (新規) - B2C ランディング
- `templates/pricing.html` (新規) - プラン比較（B2B/B2C）
- `templates/reco3.html` (修正) - モード別UI分岐
- `static/product_mode.js` (新規) - モード検出 + 表示切替

**期間**: 8-10営業日
**チーム**: フロントエンド1
**期待効果**: B2B/B2C ブランド分離、課金体系準備

---

### 🎯 優先度 3（中）: マルチテナント基盤（Phase 1 の一部）

**理由**: 複数ユーザー/組織対応の前提

**実装内容**:

#### 3-1. 基本的なマルチテナント対応
```python
# org_id/user_id コンテキスト化（後方互換保持）
def evaluate_payload(payload, org_id="default", user_id="anonymous"):
    # 内部で org_id/user_id で状態分離
    ...
```

**実装ファイル**:
- `reco2/tenant.py` (新規) - テナントコンテキスト管理
- `reco2/store.py` (修正) - org_id キー化、後方互換
- `reco2/engine.py` (修正) - evaluate_payload に org_id/user_id 注入
- `app.py` (修正) - リクエストからorg_id抽出（セッション or ヘッダ）

**データスキーマ**:
```json
{
  "version": "3.0",
  "multi_tenant": {
    "org_id:default": {
      "users": {
        "user_anonymous": {
          "k": 1.5, "eta": 0.01, "domains": {...}
        }
      },
      "web_monitors": [...],
      "feedback_history": [...]
    }
  }
}
```

**期間**: 8-10営業日
**チーム**: バックエンド1
**期待効果**: B2B チーム対応準備完了

---

### 🎯 優先度 4（低）: 段階導入制御（Phase 4）

**理由**: 後回し可能。まずは「提案」と「監視」で販売

**実装内容**:
- Alert-only ステージのみ実装
- Approval / Automation は v1.1 以降で

**期間**: 12-14営業日
**チーム**: バックエンド1 + QA
**期待効果**: 安全な制御実行、監査ログ基盤

---

### 🎯 優先度 5（オプション）: PCエージェント強化

**理由**: Web監視とフィードバック ループだけで販売可能

**実装内容**:
- 既存の `/agent/pull` `/agent/heartbeat` `/agent/logs` を維持
- UI表示は "エージェント接続: オフライン / オンライン"
- B2B Pro/Enterprise プランにのみ含める

**期間**: 不明（既存コードの評価後）
**チーム**: バックエンド0.5
**期待効果**: B2B フル機能対応

---

## 最短実装パス（4-6週間）

```
Week 1-2  [ 優先度1: Web監視 ]
          ├─ monitor CRUD API
          ├─ ポーリング機構
          └─ 監視UI

Week 2-3  [ 優先度1: Good/Bad + 学習 ]
          ├─ フィードバック拡張
          ├─ learning_engine (patrol高度化)
          ├─ フィードバックUI (Good/Bad ボタン)
          └─ 学習進捗表示

Week 3-4  [ 優先度2: PRODUCT_MODE + 計画3: マルチテナント ]
          ├─ PRODUCT_MODE 環境変数化
          ├─ 機能ゲート実装
          ├─ テナントコンテキスト
          └─ B2C/B2B ページ分け

Week 4-5  [ 優先度2: プラン制限 ]
          ├─ /pricing ページ
          ├─ URL数制限 (B2C: 3, Pro: 10, B2B: ∞)
          ├─ エージェント ゲート
          └─ 料金表記

Week 5-6  [ テスト + デプロイ準備 ]
          ├─ E2E テスト
          ├─ 負荷テスト (監視100+ URL)
          ├─ セキュリティレビュー
          └─ ドキュメント更新
```

**MVP 完成タイミング**: Week 4 終了時点
- Web監視が動く
- Good/Bad で学習できる
- B2B/B2C で分岐できる

---

## 実装上の禁止事項（重要）

### ❌ 禁止
1. **既存構造の破壊**: `/api/evaluate`, `/api/feedback`, `/api/status` の署名変更
2. **個人情報要求**: ユーザーに個人情報（名前、メール）入力必須にしない
3. **自動危険操作**: allowlist にない操作を自動実行しない
4. **後方互換性破壊**: 旧フォーマット state.json は自動マイグレーション

### ✅ 推奨
1. **差分追加のみ**: 既存キーは触らない、新キーを足す
2. **監査ログ先行**: 制御 前 にログ記録
3. **デフォルト保守的**: PRODUCT_MODE=B2B, stage=alert_only が初期値
4. **テスト駆動**: コード書く前にテスト仕様を明記

---

## 成功指標

### MVP 検収基準（Week 4 終了時）
- [ ] Web監視が3つ以上のURLで動作
- [ ] Good/Bad ボタンが機能、フィードバック記録される
- [ ] patrol() 実行で domain weight が更新される
- [ ] B2C Free / B2B Starter で UI/機能が異なる
- [ ] 既存 /api/evaluate に影響なし
- [ ] 監査ログが全操作を記録

### 販売準備完了（Week 6）
- [ ] /pricing ページで両プランが比較可能
- [ ] B2C/B2B 用 README更新
- [ ] SSL 対応、API キー保護確認
- [ ] ドメイン・SSL 証明書用意
- [ ] 決済フローの設計（Stripe等）

---

## 依存関係チェック

**必須ライブラリ**:
```txt
flask>=3.0        (既存)
gunicorn==22.0.0  (既存)
psutil>=5.9       (既存)
requests>=2.28    (新規: Web監視)
python-dateutil   (新規: ログ日時)
```

**既存テスト継続可能**: Yes（backward compat保持）

---

## 最初の実装ステップ（Day 1）

1. **ブランチ作成**: `claude/reco3-mvp-web-monitoring`
2. **reco2/web_monitor.py** 作成: HTTP ポーリング基本形
3. **app.py** に POST /api/monitors エンドポイント追加
4. **テスト**: curl で動作確認
5. **コミット**: "feat(web-monitoring): Add basic HTTP monitor CRUD"

---

## 質問テンプレート（実装中の判断）

実装中に以下が不明な場合、立ち止まって確認：

1. **データ重複**：「フィードバック」と「学習ジョブ結果」が両方必要？
   → YES: フィードバックは ユーザー入力、学習ジョブはシステム実行結果

2. **B2C でもエージェント表示**？
   → NO: Web監視 のみ。エージェントは B2B Pro/Enterprise

3. **Web監視ポーリングは cron?**
   → NO: リクエストトリガ (GET /api/monitor/poll) で十分

4. **audit_log のストレージ**？
   → state.json に追記 (後々 PostgreSQL へ移行可)

5. **Good/Bad は匿名？**
   → YES: user_id はセッション側で生成 (個人情報不要)

