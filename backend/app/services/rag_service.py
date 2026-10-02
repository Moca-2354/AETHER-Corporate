from openai import OpenAI
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery

from app.config import Settings


class RagService:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()

        endpoint = self.settings.azure_openai_endpoint.rstrip("/")

        # Microsoft Foundry / OpenAI v1
        self.openai_client = OpenAI(
            api_key=self.settings.azure_openai_api_key.get_secret_value(),
            base_url=f"{endpoint}/openai/v1/",
        )

        self.chat_deployment = (
            self.settings.azure_openai_deployment_name
        )

        self.embedding_deployment = (
            self.settings.azure_openai_embedding_deployment_name
        )

        # Azure AI Search
        self.search_client = SearchClient(
            endpoint=self.settings.azure_search_service_endpoint,
            index_name=self.settings.azure_search_index_name,
            credential=AzureKeyCredential(
                self.settings.azure_search_api_key.get_secret_value()
            ),
        )

        self.vector_field = (
            self.settings.azure_search_vector_field
        )

    def create_embedding(self, text: str) -> list[float]:
        response = self.openai_client.embeddings.create(
            model=self.embedding_deployment,
            input=text,
        )

        return response.data[0].embedding

    def search_people(
        self,
        query: str,
        top_k: int = 2,
    ) -> list[dict]:
        query_vector = self.create_embedding(query)

        vector_query = VectorizedQuery(
            vector=query_vector,
            k_nearest_neighbors=top_k,
            fields=self.vector_field,
            kind="vector",
        )

        results = self.search_client.search(
            search_text=None,
            vector_queries=[vector_query],
            select=[
                "id",
                "name",
                "age",
                "chunk",
            ],
            top=top_k,
        )

        return [dict(result) for result in results]

    def generate_answer(
        self,
        query: str,
        results: list[dict],
    ) -> str:
        context = "\n\n".join(
            (
                f"名前: {result['name']}\n"
                f"年齢: {result['age']}\n"
                f"情報: {result['chunk']}"
            )
            for result in results
        )

        response = self.openai_client.chat.completions.create(
            model=self.chat_deployment,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "あなたは社内情報検索AIです。"
                        "提供された社内情報のみを根拠として回答してください。"
                        "情報に存在しない内容は推測しないでください。"
                        "簡潔な日本語で回答してください。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"【社内情報】\n{context}\n\n"
                        f"【質問】\n{query}"
                    ),
                },
            ],
        )

        return response.choices[0].message.content

    def ask(
        self,
        query: str,
        top_k: int = 2,
    ) -> dict:
        results = self.search_people(
            query=query,
            top_k=top_k,
        )

        answer = self.generate_answer(
            query=query,
            results=results,
        )

        return {
            "answer": answer,
            "sources": [
                {
                    "id": result["id"],
                    "name": result["name"],
                    "age": result["age"],
                    "chunk": result["chunk"],
                    "score": result.get("@search.score"),
                }
                for result in results
            ],
        }