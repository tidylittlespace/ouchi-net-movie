# affiliate-engine

高単価アフィリエイト向けの半自動メディア運営システム。
現在のテーマは **「引っ越し後のネット環境とおうち映画」**（光回線・ホームルーター・引越し見積もり・動画配信）です。
**キーワード投入 → Claude が記事生成 → 人間が PR でレビュー → マージで自動公開 → リンク死活を毎日監視** までを GitHub だけで回します。サーバー代は 0 円（GitHub Pages）、かかるのは Claude API 代だけです（記事 1 本あたり数十円程度）。

```
keywords.csv ──▶ generate（現在は停止中。記事は Claude Code 上で作成）
                   │  Claude Opus 5.5 で記事生成 + 品質チェック
                   ▼
              プルリクエスト（要確認事項のチェックリスト付き）
                   │  あなたが事実確認・体験追記してマージ  ← 人間がやるのはここだけ
                   ▼
              deploy ──▶ GitHub Pages 公開（sitemap / RSS / 構造化データ付き）

offers.yaml ──▶ check-links (毎日) ──▶ リンク切れ・案件終了を通知
```

## なぜ「完全自動」にしていないか

AI 記事を無審査で大量公開するサイトは、Google の「大量生成コンテンツの不正使用」ポリシーで順位を落とされやすく、ASP の審査や提携も通りにくくなります。料金・キャンペーンの誤記は景品表示法上のリスクもあります。
そこで **作業の 9 割は自動、公開判断だけ人間** という設計にしています。生成された PR には Claude が「要確認」とした箇所のチェックリストが付くので、レビューは 1 記事 5〜10 分程度で済みます。

## 構成

| パス | 役割 |
|---|---|
| `config.yaml` | サイト名・運営者情報・生成設定・広告表記 |
| `data/offers.yaml` | 案件マスタ（ASP の広告リンクを一元管理） |
| `data/keywords.csv` | 記事化するキーワードのキュー |
| `data/experience/common.md` | 引っ越し・回線の一次体験メモ。全記事に渡される（**最重要**） |
| `data/experience/vod.md` | 映画・動画配信の体験メモ。vod カテゴリの記事に追加で渡される |
| `prompts/system.md` | 編集方針・出力形式のプロンプト |
| `engine/generate.py` | 記事生成（品質チェックで不合格なら保存しない） |
| `engine/build.py` | 静的サイト生成。`{{offer:slug}}` を広告ボックスに展開 |
| `engine/check_links.py` | 広告リンクの死活・案件終了日チェック |
| `.github/workflows/` | 生成（週次）・公開（マージ時）・リンク監視（日次） |

記事中の広告は `{{offer:hikari-a}}`（紹介ボックス）、`{{offer-table:hikari}}`（比較表）というショートコードで入るため、**リンク差し替えや案件終了は `offers.yaml` を直すだけで全記事に反映**されます。広告リンクには `rel="sponsored"`、全記事冒頭に PR 表記（ステマ規制対応）が自動で付きます。`offers.yaml` の `banner_html` に ASP のバナー広告コードを貼ると、紹介ボックスに表示されます。

ほかに、記事生成時に次のものが自動で入ります。

- **内部リンク** `{{post:slug}}`: 既存記事の一覧を Claude に渡し、関連記事へのリンクを 2〜4 本入れさせます。ビルド時に記事タイトルのリンクに変わり、リンク先がなければエラーで止まります。
- **図解**: 手順や判断の流れを Mermaid の図で描かせ、写真の代わりにしています。

体験メモは写真の代わりに **数字**（開通までの日数、時間帯別の速度、費用）を書く形式です。`（例）` が付いた行は Claude に渡されないので、自分の体験に書き換えてください。

## セットアップ

### 1. ローカルで動作確認

```bash
python -m venv .venv
```

```bash
.venv/Scripts/pip install -r requirements.txt
```

```bash
.venv/Scripts/python -m engine.generate --dry-run -n 1
```

```bash
.venv/Scripts/python -m engine.build
```

`public/index.html` をブラウザで開くと確認できます（`--dry-run` は API を呼ばずダミー記事を作ります。確認後 `content/posts/` のダミーと `keywords.csv` の status を戻してください）。

### 2. 自分用に設定する

1. **キーワードの方針**: 「光回線 おすすめ」「作品名 どこで見れる」のような大手が強いキーワードは避け、月の検索数 100〜1,000 程度で、引っ越し・トラブル・視聴環境など体験が活きるものを狙います（`keywords.csv` はその方針で作ってあります）。
2. **ASP に登録して提携申請**: A8.net、もしもアフィリエイト、afb、バリューコマース、アクセストレードなど。サイト審査があるため、最初に 5〜10 記事公開してから申請すると通りやすいです。
3. `data/offers.yaml` を承認された案件の広告リンクに置き換える。
4. `config.yaml` のサイト名・URL・運営者情報を書き換える。
5. `data/experience/common.md` と `vod.md` に自分の実体験を書く。ここが他の AI 記事との差になります。
6. `data/keywords.csv` にキーワードを追加。ラッコキーワードなどで「〇〇 おすすめ」「〇〇 評判」「〇〇 比較」のような購買意欲の高いものを優先度高めに。
   - `status` が `pending` のものだけが生成対象です。`hold` は保留扱いで生成されません。
   - サービス名の「評判」系（指名キーワード）は最も成約しやすい一方、その案件と提携していないと記事から申し込みへつなげられません。そのため `hold` にしてあります。ASP で提携が承認されたら `offers.yaml` に追加し、該当行を `pending` に変えてください。

### 3. GitHub で自動化する

1. このフォルダを GitHub リポジトリとして push する。
2. Settings → Secrets and variables → Actions で `ANTHROPIC_API_KEY` を登録。
3. Settings → Pages → Source を **GitHub Actions** にする。
4. Settings → Actions → General → Workflow permissions で **Allow GitHub Actions to create and approve pull requests** をオンにする。
5. Actions タブから `generate-articles` を手動実行して PR が作られることを確認。

※ 週次の自動生成（generate.yml）は、API キーを使わない運用のため削除済みです。再開するには、このファイルを復元して ANTHROPIC_API_KEY を Secrets に登録してください。

## API を使わずに運用する（Claude アプリで書く）

API 代をかけたくない場合は、Claude デスクトップアプリ（Claude Code）に「記事を3本書いて」と頼めば、`prompts/system.md` の方針どおりに記事を書いて `content/posts/` に保存できます。保存後は次のコマンドでショートコードと内部リンクを検証できます（エラーがなければ公開可能です）。

```bash
.venv/Scripts/python -m engine.build
```

## 運用のコツ

- **成果が出るまで 3〜6 か月**かかるのが普通です。最初の 30 記事は比較・評判系キーワードに集中。
- GA4 の ID を `config.yaml` に入れると、広告クリックが `affiliate_click` イベントとして記録されます。クリックの多い記事に体験・画像を足してリライトすると成約率が上がります。
- 公開済み記事を更新したら frontmatter に `updated: YYYY-MM-DD` を入れると更新日が表示されます。`draft: true` で非公開にできます。
- Google Search Console にサイトを登録し、`sitemap.xml` を送信してください。
