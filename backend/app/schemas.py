from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)

class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=4000)
    history: list[Message] = Field(default_factory=list, max_length=20)

    @field_validator("query")
    @classmethod
    def non_blank_query(cls, value):
        if not value.strip():
            raise ValueError("質問を入力してください")
        return value.strip()

    @model_validator(mode="after")
    def bounded_history(self):
        if sum(len(m.content) for m in self.history) > 24000:
            raise ValueError("会話履歴が長すぎます")
        return self

class Source(BaseModel):
    id: str
    name: str

class ChatResponse(BaseModel):
    user_query: str
    response: str
    sources: list[Source] = Field(default_factory=list)
    mode: Literal["demo", "live"]

class ServiceError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code, self.message = status_code, message
