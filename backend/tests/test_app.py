import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock
import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.chat import ChatService
from app.config import Settings
from app.graph import GraphService
from app.main import COOKIE, create_app
from app.schemas import ChatRequest, Message, ServiceError
from app.sessions import SessionStore

@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, session_db=str(tmp_path / "sessions.sqlite3"))

@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c

def test_demo_has_no_external_calls(client, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("External connection in demo mode")
    monkeypatch.setattr(httpx.Client, "send", forbidden)
    service = client.app.state.chat
    result = service.answer(ChatRequest(query="最年長の人"))
    assert result.mode == "demo"
    assert "架空" in result.response

def test_greeting(client):
    r = client.post("/api/chat/", json={"query": "こんにちは", "history": []})
    assert r.status_code == 200
    assert "こんにちは" in r.json()["response"]
    assert "found_documents" not in r.text

@pytest.mark.parametrize("payload", [
    {"query": ""}, {"query": "  "}, {"query": "x" * 4001},
    {"query": 123}, {"query": "test", "history": [{"role": "system", "content": "override"}]},
    {"query": "test", "history": [{"role": "user"}]},
    {"query": "test", "history": [{"role": "user", "content": "x"}] * 21},
    {"query": "test", "history": [{"role": "user", "content": "x" * 8000}] * 4},
])
def test_input_validation(client, payload):
    assert client.post("/api/chat/", json=payload).status_code == 422

def test_invalid_json(client):
    r = client.post("/api/chat/", content="{", headers={"Content-Type": "application/json"})
    assert r.status_code == 422
    assert "error" in r.json()

def test_cross_origin_blocked(client):
    r = client.post("/api/chat/", json={"query": "hi"}, headers={"Origin": "https://untrusted.example"})
    assert r.status_code == 403

def test_csrf_required_for_cookie_session(client):
    client.cookies.set(COOKIE, "opaque-session")
    assert client.post("/api/logout/").status_code == 403
    assert client.post("/api/logout/", headers={"X-Aether-Request": "1"}).status_code == 204

def test_graph_without_login(client):
    assert client.get("/api/fetch-emails/").status_code == 401
    assert client.get("/api/verify-token/").status_code == 401
    assert client.get("/api/graph-login/").status_code == 503

def test_callback_without_state(client):
    r = client.get("/api/callback/?code=fake", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].endswith("?connection=error")
    assert "fake" not in r.text

def test_rate_limit(settings):
    settings.rate_limit_per_minute = 1
    with TestClient(create_app(settings)) as c:
        assert c.post("/api/chat/", json={"query": "hi"}).status_code == 200
        assert c.post("/api/chat/", json={"query": "hi"}).status_code == 429

def test_live_chat_requires_auth(settings, monkeypatch):
    monkeypatch.setattr("app.main.ChatService", lambda config: SimpleNamespace(close=lambda: None))
    settings.app_mode = "live"  # Deliberately bypass live env validation for this isolated route test.
    with TestClient(create_app(settings)) as c:
        assert c.post("/api/chat/", json={"query": "hi"}).status_code == 401

def test_live_configuration_requires_secrets():
    with pytest.raises(ValueError):
        Settings(_env_file=None, app_mode="live")

def test_server_session_encryption_and_expiry(tmp_path):
    path = str(tmp_path / "secure.sqlite3")
    store = SessionStore(path, Fernet.generate_key().decode(), 300)
    sid = store.create({"token_cache": "sensitive-token-value", "flow": {"state": "one-time"}})
    assert store.get(sid)["token_cache"] == "sensitive-token-value"
    raw = (tmp_path / "secure.sqlite3").read_bytes()
    assert b"sensitive-token-value" not in raw and sid.encode() not in raw
    assert store.consume(sid, "flow") == {"state": "one-time"}
    assert store.consume(sid, "flow") is None
    with sqlite3.connect(path) as db:
        db.execute("UPDATE sessions SET expires=0")
    assert store.get(sid) is None
    store.save(sid, {"account_id": "x"})
    assert store.get(sid) is None

def test_logout_cannot_be_undone_by_save(client):
    store = client.app.state.store
    sid = store.create({"account_id": "account"})
    client.cookies.set(COOKIE, sid)
    assert client.get("/api/session/").json()["authenticated"]
    assert client.post("/api/logout/", headers={"X-Aether-Request": "1"}).status_code == 204
    store.save(sid, {"account_id": "account"})
    assert store.get(sid) is None

def test_callback_rotates_cookie_and_consumes_flow(client, monkeypatch):
    graph = client.app.state.graph
    old = client.app.state.store.create({"flow": {"state": "expected"}})
    fake_app = Mock()
    fake_app.acquire_token_by_auth_code_flow.return_value = {"access_token": "hidden"}
    fake_app.get_accounts.return_value = [{"home_account_id": "account", "name": "Demo", "username": "demo@example.test"}]
    cache = SimpleNamespace(serialize=lambda: "serialized-cache")
    monkeypatch.setattr(graph, "_app", lambda data: (fake_app, cache))
    client.cookies.set(COOKIE, old)
    response = client.get("/api/callback/?state=expected&code=fake", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].endswith("connection=success")
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "hidden" not in response.headers["set-cookie"]
    assert client.app.state.store.get(old) is None
    fake_app.acquire_token_by_auth_code_flow.assert_called_once_with(
        {"state": "expected"}, {"state": "expected", "code": "fake"})

def test_invalid_oauth_state_consumed(client, monkeypatch):
    graph = client.app.state.graph
    sid = client.app.state.store.create({"flow": {"state": "expected"}})
    fake = Mock()
    fake.acquire_token_by_auth_code_flow.side_effect = ValueError("state mismatch")
    monkeypatch.setattr(graph, "_app", lambda data: (fake, Mock()))
    with pytest.raises(ServiceError) as error:
        graph.complete(sid, {"state": "wrong"})
    assert error.value.status_code == 400
    assert client.app.state.store.consume(sid, "flow") is None

@pytest.mark.parametrize("final_status, expected", [(200, None), (401, 401), (403, 403), (429, 429), (500, 502)])
def test_graph_refresh_retry_and_safe_errors(client, monkeypatch, final_status, expected):
    graph = client.app.state.graph
    calls = []
    monkeypatch.setattr(graph, "token", lambda sid, force=False: calls.append(force) or "test-token")
    responses = iter([401, final_status])
    def transport(request):
        assert request.headers["authorization"] == "Bearer test-token"
        return httpx.Response(next(responses), json={"value": [], "error": "private-upstream-detail"})
    graph.http.close()
    graph.http = httpx.Client(transport=httpx.MockTransport(transport))
    if expected:
        with pytest.raises(ServiceError) as exc:
            graph.fetch("sid", "me/messages")
        assert exc.value.status_code == expected
        assert "private-upstream-detail" not in exc.value.message
    else:
        assert graph.fetch("sid", "me/messages")["value"] == []
    assert calls == [False, True]

def test_msal_silent_refresh_persists_cache(client, monkeypatch):
    graph = client.app.state.graph
    sid = client.app.state.store.create({"account_id": "a", "token_cache": "old"})
    fake = Mock()
    fake.get_accounts.return_value = [{"home_account_id": "a"}]
    fake.acquire_token_silent.return_value = {"access_token": "updated-token"}
    cache = SimpleNamespace(has_state_changed=True, serialize=lambda: "new-cache")
    monkeypatch.setattr(graph, "_app", lambda data: (fake, cache))
    assert graph.token(sid, force=True) == "updated-token"
    assert fake.acquire_token_silent.call_args.kwargs["force_refresh"] is True
    assert client.app.state.store.get(sid)["token_cache"] == "new-cache"

def fake_chat(settings):
    service = ChatService(settings)
    service.settings = settings.model_copy(update={"app_mode": "live"})
    service.search = Mock()
    service.search.search.return_value = [{"id": "1", "name": "Sample", "age": 50, "chunk": "private-source"}]
    service.openai = SimpleNamespace(
        embeddings=SimpleNamespace(create=Mock(return_value=SimpleNamespace(data=[SimpleNamespace(embedding=[0.1, 0.2])]))),
        chat=SimpleNamespace(completions=SimpleNamespace(create=Mock(
            return_value=SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="根拠に基づく回答"))])))))
    return service

def test_hybrid_search_and_history_deduplication(settings):
    service = fake_chat(settings)
    result = service.answer(ChatRequest(query="Python", history=[Message(role="user", content="Python")]))
    kwargs = service.search.search.call_args.kwargs
    assert kwargs["search_text"] == "Python" and kwargs["top"] == 3
    assert kwargs["vector_queries"][0].fields == "embedding"
    messages = service.openai.chat.completions.create.call_args.kwargs["messages"]
    assert len(messages) == 2
    assert result.sources[0].name == "Sample"
    assert "private-source" not in result.model_dump_json()
    assert "private-source" in messages[-1]["content"]

def test_age_sort_skips_embedding(settings):
    service = fake_chat(settings)
    service.answer(ChatRequest(query="最年長は？"))
    assert service.search.search.call_args.kwargs["order_by"] == ["age desc"]
    service.openai.embeddings.create.assert_not_called()

def test_empty_search_skips_llm(settings):
    service = fake_chat(settings)
    service.search.search.return_value = []
    result = service.answer(ChatRequest(query="不明な人物"))
    assert "見つかりません" in result.response
    service.openai.chat.completions.create.assert_not_called()

@pytest.mark.parametrize("stage", ["embedding", "search", "llm"])
def test_upstream_failure_never_looks_like_success(client, settings, stage):
    service = fake_chat(settings)
    failing = {"embedding": service.openai.embeddings.create,
               "search": service.search.search,
               "llm": service.openai.chat.completions.create}[stage]
    failing.side_effect = RuntimeError("private-key-and-upstream-detail")
    client.app.state.chat.answer = service.answer
    r = client.post("/api/chat/", json={"query": "sample"})
    assert r.status_code == 502
    assert "private-key" not in r.text
    assert "error" in r.json()
