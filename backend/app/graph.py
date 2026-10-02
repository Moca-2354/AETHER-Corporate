import logging
import httpx
import msal
from .config import Settings
from .schemas import ServiceError
from .sessions import SessionStore

logger = logging.getLogger(__name__)

class GraphService:
    def __init__(self, settings: Settings, store: SessionStore):
        self.settings, self.store = settings, store
        self.http = httpx.Client(timeout=20)

    def close(self):
        self.http.close()

    def _app(self, data):
        if self.settings.app_mode == "demo" or not self.settings.graph_configured:
            raise ServiceError(503, "Microsoft連携は未設定です。管理者に接続設定をご確認ください。")
        cache = msal.SerializableTokenCache()
        if data.get("token_cache"):
            cache.deserialize(data["token_cache"])
        app = msal.ConfidentialClientApplication(
            self.settings.client_id,
            authority="https://login.microsoftonline.com/consumers",
            client_credential=self.settings.client_secret.get_secret_value(),
            token_cache=cache,
        )

        return app, cache
    def begin(self):
        app, _ = self._app({})
        flow = app.initiate_auth_code_flow(scopes=self.settings.scope, redirect_uri=self.settings.redirect_uri)
        if "auth_uri" not in flow:
            raise ServiceError(502, "Microsoftの認証を開始できませんでした。")
        return self.store.create({"flow": flow}), flow["auth_uri"]

    def complete(self, sid, params):
        flow = self.store.consume(sid, "flow") if sid else None
        if not flow:
            raise ServiceError(400, "認証の有効期限が切れています。接続をやり直してください。")
        app, cache = self._app({})
        try:
            result = app.acquire_token_by_auth_code_flow(flow, params)
        except ValueError:
            raise ServiceError(400, "認証結果を確認できませんでした。接続をやり直してください。") from None
        if "access_token" not in result:
            raise ServiceError(401, "Microsoft認証が完了しませんでした。接続をやり直してください。")
        accounts = app.get_accounts()
        if not accounts:
            raise ServiceError(401, "Microsoftアカウントを確認できませんでした。")
        data = {"token_cache": cache.serialize(), "account_id": accounts[0]["home_account_id"],
                "user": {"displayName": accounts[0].get("name") or "Microsoftユーザー",
                         "userPrincipalName": accounts[0].get("username", "")}}
        new_sid = self.store.create(data)
        self.store.delete(sid)
        return new_sid

    def token(self, sid, force=False):
        data = self.store.get(sid)
        if not data or not data.get("account_id"):
            raise ServiceError(401, "Microsoftに接続してください。")
        app, cache = self._app(data)
        accounts = [a for a in app.get_accounts() if a["home_account_id"] == data["account_id"]]
        result = app.acquire_token_silent(self.settings.scope, account=accounts[0], force_refresh=force) if accounts else None
        if cache.has_state_changed:
            data["token_cache"] = cache.serialize()
            self.store.save(sid, data)
        if not result or "access_token" not in result:
            self.store.delete(sid)
            raise ServiceError(401, "Microsoftへの再接続が必要です。")
        return result["access_token"]

    def fetch(self, sid, resource):
        token = self.token(sid)
        try:
            response = self.http.get(f"https://graph.microsoft.com/v1.0/{resource}",
                                    headers={"Authorization": f"Bearer {token}"})
            if response.status_code == 401:
                token = self.token(sid, force=True)
                response = self.http.get(f"https://graph.microsoft.com/v1.0/{resource}",
                                        headers={"Authorization": f"Bearer {token}"})
            if response.status_code == 401:
                self.store.delete(sid)
                raise ServiceError(401, "Microsoftへの再接続が必要です。")
            if response.status_code == 403:
                raise ServiceError(403, "Microsoftのアクセス権限が不足しています。管理者にご確認ください。")
            if response.status_code == 429:
                raise ServiceError(429, "Microsoftへのアクセスが集中しています。しばらくしてからお試しください。")
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Microsoft Graph failed (%s)", type(exc).__name__)
            raise ServiceError(502, "Microsoftから情報を取得できませんでした。再度お試しください。") from None
