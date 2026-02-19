# RECO3 Voice AI Analysis — 乖離修正プロンプト

## プロジェクト概要
RECO3 Voice AI Analysis ランディングページ。桜+ガラスモーフィズムテーマ、4言語対応(JA/EN/ZH/KO)、オキシトシンタッチエフェクト、VOCORO Algorithm v3.0 + AI + RECO3(AI暴走制御システム)を搭載した声の解析サービス。

対象ファイル:
- `templates/index.html` (HTML)
- `static/app.js` (JavaScript)
- `static/app.css` (CSS)
- `app.py` (Flask backend)

---

## 修正すべき乖離一覧

### [致命的] 1. 音声データがバックエンドに送信されていない
**現状**: `runAnalysis(payload)` は引数 `payload`（`audio_data`, `audio_url`, `mime_type` を含む）を完全に無視し、ランダム値で `evalPayload` を作成して `/api/evaluate` に送信している。
**期待**: ユーザーが録音・アップロード・URL入力した音声データが実際にバックエンドに送られること。
**対象**: `static/app.js` の `runAnalysis()` 関数（L728付近）
**修正**: `payload` の内容（`audio_data`, `audio_url`, `mime_type`）を `evalPayload` に含めてバックエンドに送信する。シミュレーションの乱数値はバックエンドが実際の解析結果を返すまでのフォールバックとして残すが、音声データは必ず送ること。

### [致命的] 2. 言語切替で動的コンテンツが更新されない
**現状**: `setLang()` は `data-i18n` 属性を持つ静的要素のみ更新。解析結果表示中に言語を切り替えると、以下が旧言語のまま:
- レーダーチャートのラベル（Canvas描画）
- アドバイスカード（innerHTML生成）
- 感情メーター（innerHTML生成）
- 詳細プローズ（innerHTML生成）
- 結果サマリー（textContent設定）
- 関係性インサイトカード（innerHTML生成）
**期待**: 言語切替時に表示中の全結果が新言語で再レンダリングされること。
**修正**: `setLang()` の最後に、結果が表示中（`resultArea.style.display !== 'none'`）なら最後の `res` を保持して `showResult(lastRes)` を再呼び出しする。そのために `lastRes` をグローバルに保持する。

### [重大] 3. 「もう一度録音する」ボタンが録音を再開しない
**現状**: `dismissRerecord()` はパネルを非表示にするだけ。ボタンテキストは「もう一度録音する」だが、録音は開始されない。
**期待**: ボタン押下で再録音パネルを閉じ、録音を自動開始する。
**修正**: `dismissRerecord()` 内で `startRecording()` を呼ぶか、専用の `retryRecording()` 関数を作成して `dismissRerecord()` + `startRecording()` を実行する。

### [重大] 4. ファイルアップロード時のカード状態表示がない
**現状**: 録音カード(`cardRecord`)とURLカード(`cardUrl`)は active クラスが付くが、ファイルカード(`cardFile`)は選択しても視覚フィードバックがない。
**期待**: ファイル選択時にカードが一時的にアクティブになる。
**修正**: `handleFile()` で `cardFile` に active クラスを追加し、解析完了後に除去する。

### [重大] 5. 詳細プローズの文法エラー（全言語）
**現状**: `generateDetailProse()` の出力が不自然:
```
JA: "特に優れている点はと明瞭さと安定性これらの特徴は..."
EN: "Your standout qualities are and Clarity and StabilityThese qualities..."
```
`detail_strength` + `conn` + `strengths.join(conn)` の結合で、`detail_strength` の末尾と `conn` が重複し、接続詞が先頭に来る。
**期待**: 自然な文章になること。
**修正**: connectorの挿入ロジックを修正。`detail_strength` の後にスペースまたは読点を入れ、`conn` は strengths 間のみに使用する:
```js
// Before: ${dict.detail_strength}${conn}${strengths.join(conn)}
// After:  ${dict.detail_strength}${strengths.join(conn)}
// (detail_strength の i18n テキスト末尾に接続語を含めるか、ロジックで分離する)
```

### [重大] 6. XSS脆弱性 — `refresh()` のログ表示
**現状**: `tr.innerHTML` で `x.ts`, `x.domain`, `x.verdict`, `x.session_id` をAPIレスポンスからそのまま展開。悪意あるAPIレスポンスでXSS可能。
**修正**: `textContent` を使用するか、DOM APIで要素を生成する。

### [重大] 7. XSS脆弱性 — `generateAdvice()` のカード生成
**現状**: `dict[f.advKey]` を innerHTML で直接展開。i18nデータは内部制御なのでリスクは低いが、`dict[f.labelKey]` はユーザー入力ではないものの、一貫性のために `textContent` ベースにすべき。

### [中] 8. バックエンドのモジュール名が `reco2` のまま
**現状**: `app.py` の import 文が全て `from reco2.xxx` になっている。ブランディングは RECO3。
```python
from reco2.engine import evaluate_payload, record_feedback, patrol, get_status, get_logs
from reco2.store import ensure_state_file
from reco2.orchestrator import get_orchestrator
from reco2.config import load_config, public_config
from reco2 import input_gate, output_gate
```
**注意**: モジュールディレクトリ名が実際に `reco2/` の場合、import名の変更にはディレクトリ名変更も必要。ディレクトリ構造を確認してから対応すること。

### [中] 9. 再解析時に前回の結果がリセットされない
**現状**: 結果表示後に再度録音→解析すると、前回の結果エリアが表示されたまま解析が進む。解析オーバーレイは `analyze-section` 内の `position:absolute` で覆うが、スクロール位置によっては前回結果が見える。
**修正**: `runAnalysis()` の先頭で `resultArea.style.display = 'none'` を実行する。

### [中] 10. `refresh()` で `logs` が配列でない場合のクラッシュ
**現状**: `/api/logs` がエラーオブジェクトを返した場合、`logs.length` で TypeError。try/catch内だが、メトリクスも更新されない（先に処理されるため）。
**修正**: `Array.isArray(logs)` チェックを追加。

### [中] 11. `doFeedback()` のエラーがユーザーに見えない
**現状**: catch ブロックで `apiOut`（非表示パネル内の `<pre>`）にのみエラーを出力。ユーザーには何も表示されない。
**修正**: エラー時にユーザーに見えるフィードバック（トースト通知やインラインメッセージ）を表示する。

### [中] 12. レーダーチャートラベルが Canvas 外にはみ出す可能性
**現状**: `labelR = maxR + 22` でラベルを描画。長い文字列（特に ZH/KO）の場合、Canvas 320px の端に収まらない可能性。
**修正**: `ctx.measureText()` でテキスト幅を計算し、Canvas 端を超える場合は位置を調整する。

### [低] 13. `handleFile()` の `const blob = file;` が冗長
**現状**: `const blob = file;` とエイリアスを作っているが、`file` をそのまま使えば良い。
**修正**: `blob` 変数を削除し、直接 `file` を使う。

### [低] 14. `generateDetailProse()` の未使用パラメータ `_labels`
**現状**: `_labels` パラメータを受け取るが関数内で使用していない。
**修正**: パラメータを削除し、呼び出し側も修正する。

### [低] 15. CSS の `.btn-send` に `border` が2回宣言
**現状**: `border:none;` と `border:1px solid rgba(244,114,182,.20);` が同じルール内で宣言。後者が適用されるが混乱の元。
**修正**: `border:none;` を削除。

---

## サイレントエラー（前回修正済みだが検証すべき項目）

以下は前回のセッションで修正済みだが、マージ状態を確認すること:

1. ✅ `validateAudioBlob()` — `else if` で重複メッセージ防止
2. ✅ `startRecording()` — マイク拒否時のユーザー通知
3. ✅ `ctx.roundRect()` → `arcTo` フォールバック
4. ✅ `runAnalysis()` catch — `showRerecordPrompt()` でエラー表示
5. ✅ `drawWaveform()` — `analyserNode` null ガード
6. ✅ `analyserNode = null` in `stopRecording()`

---

## 実装の優先順位

1. **P0 (致命的)**: #1 音声データ送信、#2 言語切替の動的更新
2. **P1 (重大)**: #3 再録音ボタン、#5 プローズ文法、#6 XSS修正、#7 XSS修正
3. **P2 (中)**: #4 ファイルカード状態、#9 結果リセット、#10 logs配列チェック、#11 フィードバックエラー表示
4. **P3 (低)**: #8 reco2→reco3モジュール名、#12 ラベルはみ出し、#13-15 コード品質

---

## 修正完了後の確認チェックリスト

- [ ] 録音 → 停止 → 解析 → 結果表示が正常に動作する
- [ ] ファイルアップロード → 解析 → 結果表示が正常に動作する
- [ ] URL入力 → 解析 → 結果表示が正常に動作する
- [ ] 解析結果表示中に言語を切り替え → 全テキストが新言語で再レンダリング
- [ ] 再録音ボタン押下 → 録音が再開する
- [ ] 短い音声 → 再録音パネルが表示される（重複メッセージなし）
- [ ] マイク拒否 → エラーメッセージが表示される
- [ ] 解析失敗 → エラーメッセージが表示される
- [ ] ペアモード → 関係性・年齢選択 → 精度バーに反映
- [ ] 感情タブ → 6つのメーターと関係性カードが表示
- [ ] 詳細プローズ → 自然な文法で表示（4言語すべて）
- [ ] モバイル(560px以下) → レイアウト崩れなし
- [ ] 桜パーティクル → スムーズに動作
- [ ] オキシトシンエフェクト → ボタンクリックで発動
