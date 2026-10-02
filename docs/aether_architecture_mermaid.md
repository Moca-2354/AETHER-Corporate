# AETHER Corporate 構成図（Mermaid）

以下は、2026年10月時点の **AETHER Corporate 秋フェーズ** の構成です。

- `general_chat`：Azure OpenAI
- `internal_rag`：Azure AI Search + Azure OpenAI
- `outlook`：Microsoft Graph
- オーケストレーション：LangGraph
- 認証：Microsoft Entra ID
- Frontend：Next.js
- Backend：FastAPI

> 現時点では Local LLM / Local RAG / Jev は未導入です。
> `internal_rag` は検証用データを用いた Azure AI Search ベースのRAGとして動作確認済みです。

```mermaid
flowchart LR
    USER[User]
    FE[Next.js Frontend]
    API[FastAPI Backend]

    subgraph AUTH["Authentication"]
        ENTRA[Microsoft Entra ID]
    end

    subgraph ORCH["AETHER Orchestration"]
        LG[LangGraph]
        IC[Intent Classifier]
    end

    subgraph ROUTES["Intent Routes"]
        GENERAL[general_chat]
        INTERNAL[internal_rag]
        OUTLOOK[outlook]
    end

    subgraph AZURE["Azure"]
        CHAT[Azure OpenAI<br/>aether-chat]
        EMB[Embedding<br/>text-embedding-3-small]
        SEARCH[Azure AI Search<br/>aether-people]
    end

    subgraph MICROSOFT["Microsoft 365"]
        GRAPH[Microsoft Graph]
        MAIL[Outlook]
    end

    USER --> FE
    FE -->|POST /api/chat/| API
    API --> LG
    LG --> IC

    IC --> GENERAL
    IC --> INTERNAL
    IC --> OUTLOOK

    GENERAL --> CHAT

    INTERNAL --> EMB
    EMB --> SEARCH
    SEARCH --> CHAT

    OUTLOOK --> GRAPH
    GRAPH --> MAIL

    FE -->|Login| ENTRA
    ENTRA -->|OAuth callback| API
```

## ルートごとの役割

| Route | 用途 | Provider | Retriever | Generator |
|---|---|---|---|---|
| `general_chat` | 一般知識・プログラミングなど | Azure | `none` | `aether-chat` |
| `internal_rag` | 組織内の検証用ナレッジ検索 | Azure | `azure_ai_search` | `aether-chat` |
| `outlook` | Outlookメール取得 | Microsoft | `microsoft_graph` | `none` |

## 将来構想

将来的には、機密性の高い社内情報を Local 側へ寄せる構成を想定しています。

```mermaid
flowchart LR
    QUERY[User Query]
    ROUTER[LangGraph / Intent Router]

    QUERY --> ROUTER

    ROUTER -->|General knowledge| CLOUD[Cloud LLM]
    ROUTER -->|Internal / Confidential| LOCAL[Local LLM + Local RAG]
    ROUTER -->|Microsoft 365| GRAPH[Microsoft Graph]

    CLOUD --> ANSWER[Answer]
    LOCAL --> ANSWER
    GRAPH --> ANSWER
```
