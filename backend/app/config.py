from pathlib import Path
from typing import Literal
from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=Path(__file__).resolve().parents[1] / ".env",
                                     env_file_encoding="utf-8", extra="ignore")
    app_mode: Literal["demo", "live"] = "demo"
    frontend_url: str = "http://localhost:3000"
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    allowed_hosts: list[str] = ["localhost", "127.0.0.1", "testserver"]
    cookie_secure: bool = False
    session_db: str = ".runtime/sessions.sqlite3"
    session_encryption_key: SecretStr = SecretStr("")
    session_ttl_seconds: int = Field(default=28800, ge=300, le=604800)
    require_login: bool = True
    azure_search_service_endpoint: str = ""
    azure_search_api_key: SecretStr = SecretStr("")
    azure_search_index_name: str = ""
    azure_search_vector_field: str = "embedding"
    azure_openai_endpoint: str = ""
    azure_openai_api_key: SecretStr = SecretStr("")
    azure_openai_deployment_name: str = "gpt-35-turbo-1"
    azure_openai_embedding_deployment_name: str = "text-embedding-3-large"
    azure_openai_api_version: str = "2024-02-01"
    client_id: str = ""
    client_secret: SecretStr = SecretStr("")
    tenant_id: str = ""
    redirect_uri: str = "http://localhost:3000/api/callback/"
    scope: list[str] = ["User.Read", "Mail.Read"]
    rate_limit_per_minute: int = Field(default=20, ge=1, le=1000)

    @property
    def graph_configured(self) -> bool:
        return bool(self.client_id and self.client_secret.get_secret_value() and self.tenant_id)

    @model_validator(mode="after")
    def validate_live_settings(self):
        if self.app_mode == "live":
            for name in ["azure_search_service_endpoint", "azure_search_api_key",
                         "azure_search_index_name", "azure_openai_endpoint",
                         "azure_openai_api_key", "session_encryption_key"]:
                value = getattr(self, name)
                value = value.get_secret_value() if isinstance(value, SecretStr) else value
                if not value:
                    raise ValueError(f"{name.upper()} is required in live mode")
            if self.require_login and not self.graph_configured:
                raise ValueError("Microsoft settings are required when REQUIRE_LOGIN=true")
        if "*" in self.cors_origins:
            raise ValueError("CORS_ORIGINS must list explicit origins")
        return self
