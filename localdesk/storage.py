"""SQL convenience methods over an encrypted or ephemeral SQLite vault."""

from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from .vault import Vault


class Store:
    def __init__(self, path: Path, passphrase: str | None = None):
        self.path = path
        self.encrypted = passphrase is not None
        # Direct library calls without a password use memory only. They never
        # silently create a plaintext database. The CLI always asks for a key.
        self.vault = Vault(path, passphrase, ephemeral=passphrase is None)
        self.connection = self.vault.connection
        try:
            with self.connection() as db:
                db.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                    CREATE TABLE IF NOT EXISTS jobs(
                        id TEXT PRIMARY KEY, kind TEXT, status TEXT, created TEXT,
                        finished TEXT, progress INTEGER, message TEXT, result TEXT, error TEXT);
                    PRAGMA user_version=2;
                """
                )
        except BaseException:
            self.vault.close()
            raise

    def rows(self, sql: str, args: tuple = ()) -> list[dict]:
        with self.connection() as db:
            return [dict(row) for row in db.execute(sql, args).fetchall()]

    def one(self, sql: str, args: tuple = ()) -> dict | None:
        result = self.rows(sql, args)
        return result[0] if result else None

    def execute(self, sql: str, args: tuple = ()) -> int:
        with self.connection() as db:
            return db.execute(sql, args).lastrowid or 0

    def get(self, key: str, default: Any = None) -> Any:
        row = self.one("SELECT value FROM settings WHERE key=?", (key,))
        return json.loads(row["value"]) if row else default

    def set(self, key: str, value: Any) -> None:
        self.execute(
            "INSERT INTO settings(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(value, ensure_ascii=False)),
        )

    def backup(self, destination: Path) -> None:
        from .safety import InputError

        if not self.encrypted:
            raise InputError(
                "Demo databases have no recoverable encryption key. Start the password-protected app before creating backups."
            )
        self.vault.backup(destination)

    def close(self):
        self.vault.close()
