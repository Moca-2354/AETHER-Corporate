import logging
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from threading import Lock
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, Response
from starlette.middleware.trustedhost import TrustedHostMiddleware
from .chat import ChatService
from .config import Settings
from .graph import GraphService
from .schemas import ChatRequest, ChatResponse, ServiceError
from .sessions import SessionStore
from pydantic import BaseModel
from app.services.rag_service import RagService
from .orchestration import AetherOrchestrator

COOKIE = "aether_session"
logger = logging.getLogger(__name__)

class RagTestRequest(BaseModel):
    message: str

def create_app(settings: Settings | None = None):
    settings = settings or Settings()

    rag_service = RagService(
        settings = settings
    )



    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store = SessionStore(
            settings.session_db,
            settings.session_encryption_key.get_secret_value(),
            settings.session_ttl_seconds,
        )

        graph_service = GraphService(settings, store)

        app.state.store = store
        app.state.chat = ChatService(settings)
        app.state.graph = graph_service

        app.state.orchestrator = AetherOrchestrator (
            settings = settings,
            rag_service = rag_service,
            graph_service = graph_service,
        )

        yield
        app.state.chat.close()
        app.state.graph.close()

    app = FastAPI(title="AETHER API", version="1.0.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.rag = rag_service
    # app.state.orchestrator = orchestrator
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
        allow_credentials=True, allow_methods=["GET", "POST"],
        allow_headers=[
            "Content-Type",
            "X-Aether-Request"
        ],
    )
    buckets = defaultdict(deque)
    rate_lock = Lock()

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        if request.method == "POST":
            origin = request.headers.get("origin")
            if origin and origin not in settings.cors_origins:
                return JSONResponse({"error": "許可されていない接続元です。"}, status_code=403)
            if request.cookies.get(COOKIE) and request.headers.get("x-aether-request") != "1":
                return JSONResponse({"error": "リクエストを確認できませんでした。"}, status_code=403)
            size = request.headers.get("content-length", "0")
            if not size.isdigit() or int(size) > 131072:
                return JSONResponse({"error": "リクエストが大きすぎます。"}, status_code=413)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.exception_handler(ServiceError)
    async def service_error(request, exc):
        return JSONResponse({"error": exc.message}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return JSONResponse({"error": "入力形式を確認してください。質問は4,000文字以内、履歴は20件以内で送信してください。"}, status_code=422)

    @app.exception_handler(Exception)
    async def unhandled(request, exc):
        logger.error("Request failed (%s)", type(exc).__name__)
        return JSONResponse({"error": "処理に失敗しました。少し時間をおいて再度お試しください。"}, status_code=500)

    def session(request):
        return app.state.store.get(request.cookies.get(COOKIE)) or {}

    def set_cookie(response, sid):
        response.set_cookie(COOKIE, sid, httponly=True, secure=settings.cookie_secure,
            samesite="lax", max_age=settings.session_ttl_seconds, path="/")

    @app.get("/api/health/")
    def health():
        return {"status": "ok", "mode": settings.app_mode}

    @app.post("/api/graph/test")
    def test_graph(
        request: RagTestRequest,
        http_request: Request,
    ):
        return http_request.app.state.orchestrator.invoke(
            request.message
        )

    @app.get("/api/session/")
    def session_info(request: Request):
        data = session(request)
        return {"mode": settings.app_mode, "authenticated": bool(data.get("account_id")),
                "graph_configured": settings.graph_configured and settings.app_mode == "live",
                "requires_login": settings.require_login and settings.app_mode == "live", "login_url": settings.frontend_url + "/api/graph-login/",
                "user": data.get("user")}

    @app.post("/api/chat/", response_model=ChatResponse)
    def chat(payload: ChatRequest, request: Request):
        data = session(request)
        if settings.app_mode == "live" and settings.require_login and not data.get("account_id"):
            raise ServiceError(401, "Microsoftに接続してからチャットをご利用ください。")
        key = data.get("account_id") or (request.client.host if request.client else "local")
        now = time.monotonic()
        with rate_lock:
            for stale in [k for k, values in buckets.items() if not values or values[-1] < now - 60]:
                del buckets[stale]
            bucket = buckets[key]
            while bucket and bucket[0] < now - 60:
                bucket.popleft()
            if len(bucket) >= settings.rate_limit_per_minute:
                raise ServiceError(429, "送信が集中しています。1分ほど待ってからお試しください。")
            bucket.append(now)
        result = request.app.state.orchestrator.invoke(
            payload.query,
            sid=request.cookies.get(COOKIE),
        )

        logger.info(
            "orchestrator result keys=%s route=%s answer_present=%s",
            list(result.keys()),
            result.get("route"),
            "answer" in result,
        )

        sources = [
            {
                "id": source["id"],
                "name": source["name"],
            }
            for source in result.get("sources", [])
        ]

        return ChatResponse(
            user_query=payload.query,
            response=result["answer"],
            sources=sources,
            mode=settings.app_mode,
        )

    @app.post("/api/rag/test")
    def test_rag(request: RagTestRequest):
        return rag_service.ask(request.message)


    @app.get("/api/graph-login/")
    def graph_login(request: Request):
        sid, url = app.state.graph.begin()
        app.state.store.delete(request.cookies.get(COOKIE))
        response = RedirectResponse(url, status_code=302)
        set_cookie(response, sid)
        return response

    # @app.get("/api/callback/")
    # def graph_callback(request: Request):
    #     old_sid = request.cookies.get(COOKIE)
    #     try:
    #         sid = app.state.graph.complete(old_sid, dict(request.query_params))
    #     except ServiceError:
    #         app.state.store.delete(old_sid)
    #         response = RedirectResponse(settings.frontend_url + "/?connection=error", status_code=303)
    #         response.delete_cookie(COOKIE, path="/")
    #         return response
    #     response = RedirectResponse(settings.frontend_url + "/?connection=success", status_code=303)
    #     set_cookie(response, sid)
    #     return response

    @app.get("/api/callback/")
    def graph_callback(request: Request):
        old_sid = request.cookies.get(COOKIE)

        try:
            sid = app.state.graph.complete(
                old_sid,
                dict(request.query_params)
            )

        except ServiceError as exc:
            logger.exception(
                "Microsoft callback failed: status=%s message=%s sid_exists=%s params=%s",
                exc.status_code,
                exc.message,
                bool(old_sid),
                list(request.query_params.keys()),
            )

            app.state.store.delete(old_sid)

            response = RedirectResponse(
                settings.frontend_url + "/?connection=error",
                status_code=303,
            )
            response.delete_cookie(COOKIE, path="/")
            return response

        response = RedirectResponse(
            settings.frontend_url + "/?connection=success",
            status_code=303,
        )

        set_cookie(response, sid)
        return response
    @app.get("/api/verify-token/")
    def verify(request: Request):
        user = app.state.graph.fetch(request.cookies.get(COOKIE), "me")
        return {"message": "アクセストークンは有効です。", "user_info":
                {k: user.get(k) for k in ("displayName", "userPrincipalName", "id")}}

    @app.get("/api/fetch-emails/")
    def fetch_emails(request: Request):
        result = app.state.graph.fetch(request.cookies.get(COOKIE),
            "me/messages?$top=10&$select=subject,from,receivedDateTime&$orderby=receivedDateTime%20desc")
        return result.get("value", [])

    @app.post("/api/logout/", status_code=204)
    def logout(request: Request):
        app.state.store.delete(request.cookies.get(COOKIE))
        response = Response(status_code=204)
        response.delete_cookie(COOKIE, path="/")
        return response

    return app

app = create_app()
