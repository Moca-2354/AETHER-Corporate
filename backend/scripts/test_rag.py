import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=True)


# -----------------------------
# Microsoft Foundry / OpenAI v1
# -----------------------------
endpoint = os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/")

openai_client = OpenAI(
    api_key=os.environ["AZURE_OPENAI_API_KEY"],
    base_url=f"{endpoint}/openai/v1/",
)

chat_deployment = os.environ[
    "AZURE_OPENAI_DEPLOYMENT_NAME"
]

embedding_deployment = os.environ[
    "AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME"
]


# -----------------------------
# Azure AI Search
# -----------------------------
search_client = SearchClient(
    endpoint=os.environ["AZURE_SEARCH_SERVICE_ENDPOINT"],
    index_name=os.environ["AZURE_SEARCH_INDEX_NAME"],
    credential=AzureKeyCredential(
        os.environ["AZURE_SEARCH_API_KEY"]
    ),
)


def create_embedding(text: str) -> list[float]:
    response = openai_client.embeddings.create(
        model=embedding_deployment,
        input=text,
    )

    return response.data[0].embedding


def search_people(query: str, top_k: int = 2):
    query_vector = create_embedding(query)

    vector_query = VectorizedQuery(
        vector=query_vector,
        k_nearest_neighbors=top_k,
        fields="embedding",
        kind="vector",
    )

    results = search_client.search(
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

    return list(results)


def generate_answer(
    query: str,
    search_results: list
) -> str:

    context_parts = []

    for result in search_results:
        context_parts.append(
            f"""
名前: {result['name']}
年齢: {result['age']}
情報: {result['chunk']}
検索スコア: {result['@search.score']}
""".strip()
        )

    context = "\n\n".join(context_parts)

    response = openai_client.chat.completions.create(
        model=chat_deployment,
        messages=[
            {
                "role": "system",
                "content": (
                    "あなたは社内情報検索AIです。"
                    "必ず提供された社内情報を根拠として回答してください。"
                    "情報にない内容を推測してはいけません。"
                    "回答は簡潔な日本語にしてください。"
                ),
            },
            {
                "role": "user",
                "content": f"""
以下の社内情報を参考に質問へ回答してください。

【社内情報】
{context}

【質問】
{query}
""".strip(),
            },
        ],
    )

    return response.choices[0].message.content


def rag(query: str):
    print("=" * 60)
    print(f"質問: {query}")

    results = search_people(query)

    print("\n--- Search ---")

    for result in results:
        print(
            f"{result['name']} "
            f"score={result['@search.score']:.4f}"
        )

    answer = generate_answer(
        query,
        results,
    )

    print("\n--- AETHER Answer ---")
    print(answer)


queries = [
    "プロジェクト推進の経験がある人を教えて",
    "生成AIやRAGに詳しい人は誰ですか？",
    "Azureのクラウド基盤に詳しい人を教えて",
]

for query in queries:
    rag(query)