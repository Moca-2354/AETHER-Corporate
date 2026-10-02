# AETHER Corporate シーケンス図（Mermaid）

以下は AETHER Corporate のチャット処理を、`general_chat` / `internal_rag` / `outlook` の3ルートに分けて表現したシーケンス図です。

```mermaid
sequenceDiagram
    autonumber

    actor User
    participant FE as Next.js Frontend
    participant API as FastAPI
    participant LG as LangGraph
    participant IC as Intent Classifier
    participant RAG as RagService
    participant Search as Azure AI Search
    participant AOAI as Azure OpenAI
    participant GS as GraphService
    participant MSG as Microsoft Graph
    participant Outlook as Outlook

    User->>FE: 質問を入力
    FE->>API: POST /api/chat/
    API->>LG: invoke(query, sid)

    LG->>IC: 問い合わせ意図を分類

    alt general_chat
        IC-->>LG: general_chat
        LG->>AOAI: 一般質問を送信
        AOAI-->>LG: 回答
    else internal_rag
        IC-->>LG: internal_rag
        LG->>RAG: ask(query)
        RAG->>AOAI: Embedding生成
        AOAI-->>RAG: Query Vector
        RAG->>Search: Vector Search
        Search-->>RAG: 関連コンテキスト
        RAG->>AOAI: Context + Query
        AOAI-->>RAG: 回答生成
        RAG-->>LG: answer + sources
    else outlook
        IC-->>LG: outlook
        LG->>GS: fetch(sid, resource)
        GS->>MSG: GET /me/mailFolders/inbox/messages
        MSG->>Outlook: Inbox参照
        Outlook-->>MSG: Mail data
        MSG-->>GS: JSON
        GS-->>LG: 最新メール
    end

    LG-->>API: route / provider / retriever / generator / answer
    API-->>FE: ChatResponse
    FE-->>User: 回答を表示
```

## Microsoftログイン時の認証シーケンス

```mermaid
sequenceDiagram
    autonumber

    actor User
    participant FE as Next.js :3000
    participant API as FastAPI :8000
    participant Entra as Microsoft Entra ID
    participant Store as SessionStore

    User->>FE: Microsoft接続
    FE->>API: GET /api/graph-login/
    API->>Store: 認証フロー用Session作成
    API-->>User: 302 Redirect
    User->>Entra: Microsoft Login
    Entra-->>FE: /api/callback/?code=...&state=...
    FE->>API: Next.js rewrite
    API->>Store: state / session検証
    API->>Entra: Authorization Code交換
    Entra-->>API: Access Token
    API->>Store: Token Cache保存
    API-->>FE: ?connection=success
    FE-->>User: Outlook 接続済み
```

## Outlook取得の実リクエスト

```text
GET https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages
    ?$top=5
    &$select=subject,from,receivedDateTime,bodyPreview
    &$orderby=receivedDateTime desc
```

取得項目：

- `subject`
- `from`
- `receivedDateTime`
- `bodyPreview`
