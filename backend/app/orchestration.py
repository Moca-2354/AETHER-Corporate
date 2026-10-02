from typing import Any, TypedDict

from langgraph.graph import StateGraph, START, END
from openai import OpenAI

from .config import Settings
from .services.rag_service import RagService
from .graph import GraphService


class AetherState(TypedDict, total=False):
    message: str
    sid: str | None
    route: str
    provider: str
    retriever: str
    generator: str
    answer: str
    sources: list[dict]


class AetherOrchestrator:
    def __init__(
        self,
        settings,
        rag_service,
        graph_service: GraphService,
    ):
        self.settings = settings
        self.rag_service = rag_service
        self.graph_service = graph_service

        endpoint = settings.azure_openai_endpoint.rstrip("/")

        self.openai_client = OpenAI(
            api_key=settings.azure_openai_api_key.get_secret_value(),
            base_url=f"{endpoint}/openai/v1/",
        )

        self.chat_deployment = (
            settings.azure_openai_deployment_name
        )

        builder = StateGraph(AetherState)

        # ① Intent判定
        builder.add_node(
            "classifier",
            self._classifier,
        )

        # ② 各処理ノード
        builder.add_node(
            "internal_rag",
            self._internal_rag,
        )

        builder.add_node(
            "general_chat",
            self._general_chat,
        )

        builder.add_node(
            "outlook",
            self._outlook,
        )

        # START → classifier
        builder.add_edge(
            START,
            "classifier",
        )

        # classifier → 各ルート
        builder.add_conditional_edges(
            "classifier",
            self._route,
            {
                "internal_rag": "internal_rag",
                "general_chat": "general_chat",
                "outlook": "outlook",
            },
        )

        # 各ルート → END
        builder.add_edge(
            "internal_rag",
            END,
        )

        builder.add_edge(
            "general_chat",
            END,
        )

        builder.add_edge(
            "outlook",
            END,
        )

        self.graph = builder.compile()

    # --------------------------------
    # Intent Classifier
    # --------------------------------
    def _classifier(
        self,
        state: AetherState,
    ) -> dict:
        message = state["message"]

        response = self.openai_client.chat.completions.create(
            model=self.chat_deployment,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "ユーザーの質問を次の3種類のうち"
                        "必ず1つに分類してください。\n\n"

                        "internal_rag:\n"
                        "社内人物、部署、社内文書、社内知識、"
                        "社内プロジェクトなどについての質問\n\n"

                        "outlook:\n"
                        "メール、Outlook、受信箱、送信者、"
                        "メール確認などMicrosoft Outlookに"
                        "関係する依頼\n\n"

                        "general_chat:\n"
                        "上記以外の一般的な質問\n\n"

                        "回答は internal_rag / outlook / "
                        "general_chat のいずれか1語だけにしてください。"
                    ),
                },
                {
                    "role": "user",
                    "content": message,
                },
            ],
        )

        route = (
            response.choices[0]
            .message.content
            .strip()
            .lower()
        )

        allowed = {
            "internal_rag",
            "general_chat",
            "outlook",
        }

        if route not in allowed:
            route = "general_chat"

        return {
            "route": route,
        }

    def _route(
        self,
        state: AetherState,
    ) -> str:
        return state["route"]

    # --------------------------------
    # 社内RAG
    # --------------------------------
    def _internal_rag(
        self,
        state: AetherState,
    ) -> dict:
        result = self.rag_service.ask(
            state["message"]
        )

        return {
            "route": "internal_rag",

            # 現時点ではAzure生成
            "provider": "azure",
            "retriever": "azure_ai_search",
            "generator": "aether-chat",

            "answer": result["answer"],
            "sources": result["sources"],
        }

    # --------------------------------
    # 一般質問
    # --------------------------------
    def _general_chat(
        self,
        state: AetherState,
    ) -> dict:
        response = self.openai_client.chat.completions.create(
            model=self.chat_deployment,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "あなたはAETHERです。"
                        "ユーザーの一般的な質問に"
                        "簡潔で正確な日本語で回答してください。"
                    ),
                },
                {
                    "role": "user",
                    "content": state["message"],
                },
            ],
        )

        return {
            "route": "general_chat",
            "provider": "azure",
            "retriever": "none",
            "generator": "aether-chat",
            "answer": response.choices[0].message.content,
            "sources": [],
        }

    # --------------------------------
    # Outlook
    # --------------------------------
    def _outlook(
        self,
        state: AetherState,
    ) -> dict:
        sid = state.get("sid")

        if not sid:
            return {
                "route": "outlook",
                "provider": "microsoft",
                "retriever": "microsoft_graph",
                "generator": "none",
                "answer": "Microsoftに接続してからOutlookをご利用ください。",
                "sources": [],
            }

        data = self.graph_service.fetch(
            sid,
            (
                "me/mailFolders/inbox/messages"
                "?$top=5"
                "&$select=subject,from,receivedDateTime,bodyPreview"
                "&$orderby=receivedDateTime%20desc"
            ),
        )

        messages = data.get("value", [])

        if not messages:
            answer="最近届いたoutlookメールは見つかりませんでした"
        else:
            lines=[]

            for i, message in enumerate(messages, start=1):
                sender = (
                    message.get("from", {})
                    .get("emailAddress", {})
                    .get("name", "送信者不明")
                )

                subject = message.get("subject") or "件名なし"
                received = message.get("receivedDateTime", "")
                preview = message.get("bodyPreview", "")

                lines.append(
                    f"{i}. {subject}\n"
                    f"送信者: {sender}\n"
                    f"受信日時: {received}\n"
                    f"{preview}"
                )
                answer = (
                "最近届いたOutlookメールです。\n\n"
                + "\n\n".join(lines)
                )

        return {
            "route": "outlook",
            "provider": "microsoft",
            "retriever": "microsoft_graph",
            "generator": "none",
            "answer": answer,
            "sources": [],
        }

    def invoke(
        self,
        message: str,
        sid: str | None = None,
    ) -> AetherState:
        return self.graph.invoke(
            {
                "message": message,
                "sid": sid,
            }
        )