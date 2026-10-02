import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=True)

# Azure OpenAI / Foundry v1
endpoint = os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/")

openai_client = OpenAI(
    api_key=os.environ["AZURE_OPENAI_API_KEY"],
    base_url=f"{endpoint}/openai/v1/",
)

embedding_deployment = os.environ[
    "AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME"
]

# Azure AI Search
search_client = SearchClient(
    endpoint=os.environ["AZURE_SEARCH_SERVICE_ENDPOINT"],
    index_name=os.environ["AZURE_SEARCH_INDEX_NAME"],
    credential=AzureKeyCredential(
        os.environ["AZURE_SEARCH_API_KEY"]
    ),
)

people = [
    {
        "id": "person-001",
        "name": "青山 晴人",
        "age": 58,
        "chunk": "事業企画部に所属。事業戦略とプロジェクト推進の経験があります。",
    },
    {
        "id": "person-002",
        "name": "佐藤 美咲",
        "age": 32,
        "chunk": "AI開発チームに所属。生成AI、RAG、機械学習を使ったシステム開発を担当しています。",
    },
    {
        "id": "person-003",
        "name": "田中 悠斗",
        "age": 41,
        "chunk": "システム開発部に所属。Azureを使ったクラウド基盤と大規模Webシステムの設計経験があります。",
    },
]


def create_embedding(text: str) -> list[float]:
    response = openai_client.embeddings.create(
        model=embedding_deployment,
        input=text,
    )
    return response.data[0].embedding


documents = []

for person in people:
    text = (
        f"名前: {person['name']}\n"
        f"年齢: {person['age']}\n"
        f"説明: {person['chunk']}"
    )

    embedding = create_embedding(text)

    print(
        f"{person['name']}: "
        f"embedding dimensions = {len(embedding)}"
    )

    if len(embedding) != 1536:
        raise ValueError(
            f"Embedding dimension mismatch: "
            f"expected=1536, actual={len(embedding)}"
        )

    documents.append({
        **person,
        "embedding": embedding,
    })


results = search_client.upload_documents(
    documents=documents
)

print("\n--- Upload result ---")

for result in results:
    print(
        f"{result.key}: "
        f"succeeded={result.succeeded}, "
        f"error={result.error_message}"
    )