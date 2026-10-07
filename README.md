# AETHER — FastAPI × Azure AI Chat

既存のDjangoチャットをFastAPIへ移行した、公開用の独立プロジェクトです。
フロントエンドはNext.js / React / TypeScript。黒、ネオンブルー、シアンを基調に、半透明の入力欄と控えめな発光を使っています。

元のプロジェクト・Git履歴・APIキー・社内データは引き継いでいません。
GitHubへのアップロードやAzure側の変更は行っていません。

## できること

- Azure OpenAIで質問をベクトル化し、Azure AI Searchでハイブリッド検索
- 「最年長」「一番年上」を含む質問では、年齢の降順で1件取得
- 検索結果と会話履歴を使ってAzure OpenAIで回答を生成
- Microsoftへのログイン、ユーザー情報の検証、最近のメール10件の取得
- MSALトークンキャッシュによる更新、Graphが401を返したときの再試行
- 会話の切り替え、新しいチャット、Markdown表示、回答コピー、受信停止、エラー表示
- 日本語IMEの変換確定を考慮したEnter送信、Shift + Enter改行
- モバイル向けの会話一覧、キーボード対応のOutlookパネル

会話履歴はReactのメモリ上に保持します。再読み込みすると消えます。
ブラウザのlocalStorageやサーバーDBに会話を永続保存しません。
質問と必要な会話履歴は、liveモードではFastAPIおよびAzureへ送信されます。

## 最初にデモを起動する

Python 3.12、Node.js 22 LTS、npmを用意してください。
以下はプロジェクトのルートを開いたPowerShellで実行します。

### 1. バックエンド

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

初期値は APP_MODE=demo です。Azure、Microsoftへの呼び出しは行いません。
デモ回答は固定テンプレートと架空の人物情報であり、AIによる実際の検索結果ではありません。

### 2. フロントエンド（別のターミナル）

```powershell
cd frontend
npm ci
Copy-Item .env.example .env.local
npm run dev
```

ブラウザで **http://localhost:3000** を開きます。
FastAPIのAPI仕様書は http://127.0.0.1:8000/docs です。

macOS / Linuxでは、venvの作成に python3.12 を、実行に .venv/bin/python を使用します。
requirements-lock.txt は作成時のWindows / Python 3.12環境で確認した依存バージョンです。
別環境で再解決する場合は requirements-dev.txt を使い、テストを実施してください。

## Azureへ接続する

backend/.env の APP_MODE を live に変更し、次の値を設定してバックエンドを再起動します。
古いコードに記載されたキーを公開用のソースへ貼り付けないでください。

| 設定 | 内容 |
|---|---|
| AZURE_SEARCH_SERVICE_ENDPOINT | 既存のAzure AI Searchのエンドポイント |
| AZURE_SEARCH_API_KEY | Searchの検索権限を持つキー |
| AZURE_SEARCH_INDEX_NAME | 既存のインデックス名 |
| AZURE_SEARCH_VECTOR_FIELD | 既存と同じ embedding が初期値 |
| AZURE_OPENAI_ENDPOINT | 既存のAzure OpenAIのエンドポイント |
| AZURE_OPENAI_API_KEY | Azure OpenAIのキー |
| AZURE_OPENAI_DEPLOYMENT_NAME | 実際に作成済みのチャット用デプロイ名 |
| AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME | 実際に作成済みのEmbedding用デプロイ名 |
| AZURE_OPENAI_API_VERSION | 元のコードと同じ 2024-02-01 が初期値 |

gpt-35-turbo-1 と text-embedding-3-large は元のコードのデプロイ名を初期値として残しています。
モデルやAPIバージョンの変更はしていません。利用可否はお使いのAzure環境に依存します。

既存のインデックスには id / name / age / chunk / embedding を想定します。
id・name・age・chunkは取得可能、ageは並べ替え可能である必要があります。
embeddingの次元数は既存のEmbeddingデプロイと一致させてください。
インデックス作成、データ投入、OCR処理は今回の範囲に含みません。

### セッション暗号鍵

次を実行して得られる値を backend/.env の SESSION_ENCRYPTION_KEY に保存します。

```powershell
.\.venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

この鍵は秘密情報です。変更すると保存済みのMicrosoft接続は再認証が必要になります。
Microsoftの認証フローとトークンキャッシュは、この鍵で暗号化してSQLiteへ保存します。
Cookieへ入るのはランダムなセッションIDだけです。

## Microsoft Graphを設定する

Microsoft Entra IDのアプリ登録で、次を設定します。

1. サポート対象のアカウントは、使用する組織のテナントに合わせます。
2. 認証のプラットフォームは「Web」にします。
3. リダイレクトURIに http://localhost:3000/api/callback/ を登録します。
4. Microsoft Graphの委任されたアクセス許可 User.Read / Mail.Read を設定します。
5. 組織の方針に応じて管理者の同意を実施します。
6. クライアントシークレットを作成し、**シークレットIDではなく値**を保存します。

backend/.env に CLIENT_ID / CLIENT_SECRET / TENANT_ID を設定します。
REDIRECT_URI はアプリ登録と完全に一致させてください。
既存の登録を使う場合は、上記のリダイレクトURIを追加してください。

ブラウザはフロントエンドの /api/ へアクセスし、Next.jsがFastAPIへ転送します。
これにより画面とAPIでCookieのホストを揃えます。
直接FastAPIのポートを使う旧リダイレクトURIも設定可能ですが、画面運用ではlocalhost:3000に統一してください。
liveモードのログインはFRONTEND_URLの正規URLから開始します。

初期設定の REQUIRE_LOGIN=true では、liveモードのチャットにもMicrosoftログインが必要です。
Microsoft設定なしでAzureのみをローカル検証する場合に限り REQUIRE_LOGIN=false にできます。
この設定ではチャットAPIへ到達できる人が検索できるため、外部公開しないでください。

Outlookは右上またはサイドバーから開きます。
件名・送信者・受信日時のみを取得します。本文取得、送信、削除、メールのRAG検索は行いません。
接続解除は本アプリのセッションを削除する操作で、Microsoft全体からのサインアウトではありません。

## Django版からの対応

| 元の構成 | 新しい構成 |
|---|---|
| Django settings.py | app/config.py + .env |
| Django urlpatterns | app/main.py のFastAPIルート |
| views.py のチャット | app/chat.py |
| views.py のGraph処理 | app/graph.py |
| Djangoセッション | app/sessions.py（暗号化SQLite） |
| Flask認証検証アプリ | FastAPI側へ統合。別起動は不要 |
| Next.jsのチャットページ | src/app/page.tsx と globals.css |
| SQLiteの会話モデル | 元々未実装。今回も会話の永続保存なし |
| Django管理画面 | 移植対象外 |

## API

| メソッド | パス | 用途 |
|---|---|---|
| POST | /api/chat/ | query、historyから回答生成 |
| GET | /api/graph-login/ | Microsoftログイン |
| GET | /api/callback/ | 認証後、フロントエンドへ戻る |
| GET | /api/verify-token/ | Graph /meで確認 |
| GET | /api/fetch-emails/ | 最近のメール10件 |
| GET | /api/session/ | モードとアプリ接続状態 |
| POST | /api/logout/ | アプリの接続解除 |
| GET | /api/health/ | APIの起動状態。Azureへの疎通は確認しない |

chatの query / history / response は従来の形式を維持します。
debug_info と検索原文は返さず、代わりに sources（id、name）を返します。
入力不正は422、未認証は401、回数制限は429、外部サービス障害は502です。
エラー本文は {"error":"利用者向けメッセージ"} です。
Cookie付きのPOSTには X-Aether-Request: 1 が必要です。フロントエンドは自動で付与します。
認証コールバックは従来のJSON応答から、画面へのリダイレクトに変更しました。

## 検証

```powershell
# backendで実行
.\.venv\Scripts\python.exe -m pytest -q

# frontendで実行
npm run typecheck
npm run build
npm audit
```

外部APIをモックしたテストで、検索分岐、履歴、秘密情報を含まないエラー、
認証stateの一回限りの利用、セッション暗号化、401時の更新などを確認します。
Azure / Entra / Graphの実接続は、利用者の環境設定後に確認してください。

## 運用時の範囲と制約

- 元の検索方式を維持しています。会話履歴による検索クエリの書き換えは未実装です。「その人」のような質問は人物名を含めてください。
- 最年長検索は全件を対象にします。部署条件のフィルター、同年齢者全員の取得、全件集計は未実装です。
- 文書単位のアクセス権フィルターは未実装です。同じインデックスを使う認証ユーザー全員が、その検索対象を閲覧できる前提です。
- 「受信を停止」はブラウザの待機を中断します。すでに開始したAzureの処理や課金停止は保証しません。
- セッションは初期値8時間で失効します。トークン更新はMSALのサーバー側キャッシュで管理します。
- レート制限はプロセス内、セッションDBはローカルSQLiteです。複数台運用では共有ストア・共有レート制限への置き換えが必要です。
- 公開運用はHTTPSとREQUIRE_LOGIN=trueを使用し、COOKIE_SECURE=true、FRONTEND_URL、CORS_ORIGINS、ALLOWED_HOSTS、REDIRECT_URIを実ドメインへ設定してください。
- Uvicornは --no-access-log で起動します。リバースプロキシ側でも、OAuthコールバックのcodeなどをログへ記録しない設定にしてください。
- Azureの鍵は管理者だけが扱い、最小権限のキーを使ってください。Djangoの秘密鍵や旧APIキーは本プロジェクトでは使用しません。

## 参照資料

- [FastAPIのlifespan](https://fastapi.tiangolo.com/advanced/events/)
- [FastAPIのCORS](https://fastapi.tiangolo.com/tutorial/cors/)
- [MSAL Python](https://msal-python.readthedocs.io/en/latest/index.html)
- [OpenAI Python SDK](https://developers.openai.com/api/reference/python)
