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
# Azure OpenAI / Foundry v1
# -----------------------------
endpoint = os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/")

openai_client = OpenAI(
    api_key=os.environ["AZURE_OPENAI_API_KEY"],
    base_url=f"{endpoint}/openai/v1/",
)

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


def vector_search(query: str):
    print(f"\n検索: {query}")

    query_vector = create_embedding(query)

    print(
        f"Query embedding dimensions = "
        f"{len(query_vector)}"
    )

    vector_query = VectorizedQuery(
        vector=query_vector,
        k_nearest_neighbors=3,
        fields="embedding",
        kind="vector",
    )

    results = search_client.search(
        search_text=None,
        vector_queries=[vector_query],
        select=["id", "name", "age", "chunk"],
        top=3,
    )

    for i, result in enumerate(results, start=1):
        print(
            f"\n{i}. {result['name']} "
            f"({result['age']}歳)"
        )
        print(f"score: {result['@search.score']}")
        print(result["chunk"])


queries = [
    "プロジェクト推進の経験がある人",
    "生成AIやRAGの経験がある人",
    "Azureやクラウド基盤に詳しい人",
]

for query in queries:
    vector_search(query)