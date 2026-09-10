import os
import time
import base64
import hashlib
import sqlite3
from typing import Optional, Dict, Any
from dataclasses import dataclass
from cryptography.fernet import Fernet


def _get_encryption_cipher() -> Fernet:
    """
    Derives a consistent 32-byte url-safe base64 key for Fernet encryption
    from JIRA_CLIENT_SECRET or SECRET_KEY or a fallback persistent machine key.
    """
    secret = (
        os.getenv("SECRET_KEY")
        or os.getenv("JIRA_CLIENT_SECRET")
        or "jira-connector-default-encryption-salt"
    )
    key_bytes = hashlib.sha256(secret.encode("utf-8")).digest()
    fernet_key = base64.urlsafe_b64encode(key_bytes)
    return Fernet(fernet_key)


@dataclass
class JiraConnectionRecord:
    user_id: str
    access_token: str
    refresh_token: Optional[str]
    expires_at: float
    cloud_id: Optional[str]
    site_name: Optional[str]
    site_url: Optional[str]
    account_email: Optional[str]
    display_name: Optional[str]
    avatar_url: Optional[str]
    created_at: float
    updated_at: float

    def is_expired(self, buffer_seconds: float = 60.0) -> bool:
        """Returns True if the token has expired or will expire within the buffer period."""
        return time.time() >= (self.expires_at - buffer_seconds)


class OAuthStore:
    """
    Secure SQLite-backed persistent token and connection storage for Jira Cloud OAuth 2.0 (3LO).
    Ensures per-user isolation and token encryption at rest.
    """

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            # Default to storage directory or workspace root
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.db_path = os.path.join(base_dir, "jira_oauth.db")
        else:
            self.db_path = db_path

        self.cipher = _get_encryption_cipher()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Initialize SQLite database tables if not existing."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS jira_connections (
                    user_id TEXT PRIMARY KEY,
                    access_token_encrypted TEXT NOT NULL,
                    refresh_token_encrypted TEXT,
                    expires_at REAL NOT NULL,
                    cloud_id TEXT,
                    site_name TEXT,
                    site_url TEXT,
                    account_email TEXT,
                    display_name TEXT,
                    avatar_url TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS oauth_states (
                    state TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL
                )
                """
            )
            conn.commit()

    def _encrypt(self, plain_text: Optional[str]) -> Optional[str]:
        if not plain_text:
            return None
        return self.cipher.encrypt(plain_text.encode("utf-8")).decode("utf-8")

    def _decrypt(self, encrypted_text: Optional[str]) -> Optional[str]:
        if not encrypted_text:
            return None
        try:
            return self.cipher.decrypt(encrypted_text.encode("utf-8")).decode("utf-8")
        except Exception:
            # Fallback if unencrypted legacy data exists
            return encrypted_text

    def save_state(self, state: str, user_id: str, ttl_seconds: int = 600) -> None:
        """Save a CSRF state token with an expiration time."""
        now = time.time()
        expires_at = now + ttl_seconds
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Clean up old expired states first
            cursor.execute("DELETE FROM oauth_states WHERE expires_at < ?", (now,))
            cursor.execute(
                """
                INSERT OR REPLACE INTO oauth_states (state, user_id, created_at, expires_at)
                VALUES (?, ?, ?, ?)
                """,
                (state, user_id, now, expires_at),
            )
            conn.commit()

    def validate_and_consume_state(self, state: str) -> Optional[str]:
        """
        Validates state token and deletes it to prevent replay attacks.
        Returns the associated user_id if valid, otherwise None.
        """
        now = time.time()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT user_id, expires_at FROM oauth_states WHERE state = ?",
                (state,),
            )
            row = cursor.fetchone()
            if not row:
                return None

            user_id = row["user_id"]
            expires_at = row["expires_at"]

            # Always consume the state
            cursor.execute("DELETE FROM oauth_states WHERE state = ?", (state,))
            conn.commit()

            if now > expires_at:
                return None
            return user_id

    def save_connection(
        self,
        user_id: str,
        access_token: str,
        refresh_token: Optional[str],
        expires_in: int = 3600,
        cloud_id: Optional[str] = None,
        site_name: Optional[str] = None,
        site_url: Optional[str] = None,
        account_email: Optional[str] = None,
        display_name: Optional[str] = None,
        avatar_url: Optional[str] = None,
        expires_at: Optional[float] = None,
    ) -> JiraConnectionRecord:
        """Upsert a user's Jira connection record with encrypted tokens."""
        now = time.time()
        if expires_at is None:
            expires_at = now + expires_in

        enc_access = self._encrypt(access_token)
        enc_refresh = self._encrypt(refresh_token)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO jira_connections (
                    user_id, access_token_encrypted, refresh_token_encrypted,
                    expires_at, cloud_id, site_name, site_url,
                    account_email, display_name, avatar_url,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    access_token_encrypted = excluded.access_token_encrypted,
                    refresh_token_encrypted = COALESCE(excluded.refresh_token_encrypted, jira_connections.refresh_token_encrypted),
                    expires_at = excluded.expires_at,
                    cloud_id = COALESCE(excluded.cloud_id, jira_connections.cloud_id),
                    site_name = COALESCE(excluded.site_name, jira_connections.site_name),
                    site_url = COALESCE(excluded.site_url, jira_connections.site_url),
                    account_email = COALESCE(excluded.account_email, jira_connections.account_email),
                    display_name = COALESCE(excluded.display_name, jira_connections.display_name),
                    avatar_url = COALESCE(excluded.avatar_url, jira_connections.avatar_url),
                    updated_at = excluded.updated_at
                """,
                (
                    user_id,
                    enc_access,
                    enc_refresh,
                    expires_at,
                    cloud_id,
                    site_name,
                    site_url,
                    account_email,
                    display_name,
                    avatar_url,
                    now,
                    now,
                ),
            )
            conn.commit()

        return JiraConnectionRecord(
            user_id=user_id,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            cloud_id=cloud_id,
            site_name=site_name,
            site_url=site_url,
            account_email=account_email,
            display_name=display_name,
            avatar_url=avatar_url,
            created_at=now,
            updated_at=now,
        )

    def update_tokens(
        self,
        user_id: str,
        access_token: str,
        refresh_token: Optional[str],
        expires_in: int,
    ) -> None:
        """Update tokens for an existing user after a refresh."""
        now = time.time()
        expires_at = now + (expires_in if expires_in > 0 else 3600)

        enc_access = self._encrypt(access_token)
        enc_refresh = self._encrypt(refresh_token) if refresh_token else None

        with self._get_connection() as conn:
            cursor = conn.cursor()
            if enc_refresh:
                cursor.execute(
                    """
                    UPDATE jira_connections
                    SET access_token_encrypted = ?,
                        refresh_token_encrypted = ?,
                        expires_at = ?,
                        updated_at = ?
                    WHERE user_id = ?
                    """,
                    (enc_access, enc_refresh, expires_at, now, user_id),
                )
            else:
                cursor.execute(
                    """
                    UPDATE jira_connections
                    SET access_token_encrypted = ?,
                        expires_at = ?,
                        updated_at = ?
                    WHERE user_id = ?
                    """,
                    (enc_access, expires_at, now, user_id),
                )
            conn.commit()

    def get_connection(self, user_id: str) -> Optional[JiraConnectionRecord]:
        """Retrieve and decrypt a user's Jira connection."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT user_id, access_token_encrypted, refresh_token_encrypted,
                       expires_at, cloud_id, site_name, site_url,
                       account_email, display_name, avatar_url,
                       created_at, updated_at
                FROM jira_connections
                WHERE user_id = ?
                """,
                (user_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None

            access_token = self._decrypt(row["access_token_encrypted"])
            refresh_token = self._decrypt(row["refresh_token_encrypted"])

            return JiraConnectionRecord(
                user_id=row["user_id"],
                access_token=access_token or "",
                refresh_token=refresh_token,
                expires_at=row["expires_at"],
                cloud_id=row["cloud_id"],
                site_name=row["site_name"],
                site_url=row["site_url"],
                account_email=row["account_email"],
                display_name=row["display_name"],
                avatar_url=row["avatar_url"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    def delete_connection(self, user_id: str) -> bool:
        """Remove a user's Jira connection. Returns True if a record was removed."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM jira_connections WHERE user_id = ?", (user_id,))
            conn.commit()
            return cursor.rowcount > 0
