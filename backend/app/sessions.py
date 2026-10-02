"""Browser cookies contain opaque IDs; OAuth flows and tokens stay encrypted on the server."""
import hashlib
import json
import secrets
import sqlite3
import time
from pathlib import Path
from cryptography.fernet import Fernet, InvalidToken

class SessionStore:
    def __init__(self, path: str, key: str, ttl: int):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path, self.ttl = path, ttl
        self.cipher = Fernet(key.encode() if key else Fernet.generate_key())
        with self._connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, data BLOB NOT NULL, expires REAL NOT NULL)")

    def _connect(self):
        return sqlite3.connect(self.path, timeout=10)

    @staticmethod
    def _hash(sid):
        return hashlib.sha256(sid.encode()).hexdigest()

    def _encode(self, data):
        return self.cipher.encrypt(json.dumps(data).encode())

    def create(self, data: dict) -> str:
        sid = secrets.token_urlsafe(32)
        with self._connect() as db:
            db.execute("DELETE FROM sessions WHERE expires < ?", (time.time(),))
            db.execute("INSERT INTO sessions VALUES (?, ?, ?)",
                       (self._hash(sid), self._encode(data), time.time() + self.ttl))
        return sid

    def get(self, sid: str | None) -> dict | None:
        if not sid or len(sid) > 128:
            return None
        with self._connect() as db:
            row = db.execute("SELECT data FROM sessions WHERE id=? AND expires>?",
                             (self._hash(sid), time.time())).fetchone()
        if row:
            try:
                return json.loads(self.cipher.decrypt(row[0]))
            except (InvalidToken, ValueError):
                self.delete(sid)
        return None

    def save(self, sid: str, data: dict):
        # Do not recreate a logged-out session from an in-flight request.
        with self._connect() as db:
            db.execute("UPDATE sessions SET data=? WHERE id=? AND expires>?",
                       (self._encode(data), self._hash(sid), time.time()))

    def consume(self, sid: str, field: str):
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT data FROM sessions WHERE id=? AND expires>?",
                             (self._hash(sid), time.time())).fetchone()
            if not row:
                return None
            try:
                data = json.loads(self.cipher.decrypt(row[0]))
            except (InvalidToken, ValueError):
                return None
            value = data.pop(field, None)
            db.execute("UPDATE sessions SET data=? WHERE id=?", (self._encode(data), self._hash(sid)))
            return value

    def delete(self, sid: str | None):
        if sid:
            with self._connect() as db:
                db.execute("DELETE FROM sessions WHERE id=?", (self._hash(sid),))
