"""Authenticated encrypted snapshots of an in-memory SQLite database.

Only ciphertext reaches the database path. A process lock prevents concurrent
writers. The database key is derived once per unlock, not once per query.
"""

from __future__ import annotations
import os
import secrets
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from .safety import InputError

MAGIC = b"LOCALDESK-VAULT-2\x00"
MAX_VAULT_BYTES = 256 * 1024 * 1024


def derive_key(password: str, salt: bytes) -> bytes:
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

    if not isinstance(password, str) or not 12 <= len(password) <= 4096:
        raise InputError("Use a vault passphrase with 12 to 4096 characters.")
    return Scrypt(salt=salt, length=32, n=2**17, r=8, p=1).derive(
        password.encode("utf-8")
    )


class ProcessLock:
    """Nonblocking file lock, released by the OS when the process exits."""

    def __init__(self, path: Path):
        if path.is_symlink():
            raise InputError("A vault lock cannot be a symbolic link.")
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        self.fd = os.open(path, flags, 0o600)
        try:
            if os.name == "nt":
                import msvcrt

                if os.fstat(self.fd).st_size == 0:
                    os.write(self.fd, b"0")
                os.lseek(self.fd, 0, os.SEEK_SET)
                msvcrt.locking(self.fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            os.close(self.fd)
            self.fd = None
            raise InputError(
                "This data folder is already open. Use the running app or another data folder."
            ) from exc

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None


def _atomic_ciphertext(path: Path, content: bytes) -> None:
    if path.is_symlink():
        raise InputError("A vault path cannot be a symbolic link.")
    temporary = path.with_name("." + path.name + "." + secrets.token_hex(8) + ".tmp")
    try:
        with os.fdopen(
            os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb"
        ) as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)
        if os.name != "nt":
            fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
    finally:
        temporary.unlink(missing_ok=True)


class Vault:
    def __init__(self, path: Path, password: str | None, *, ephemeral: bool = False):
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.exceptions import InvalidTag

        self.path = path
        self.lock = threading.RLock()
        self.ephemeral = ephemeral
        self.closed = False
        self.process_lock = None
        self.db = None
        self.last_snapshot = b""
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_symlink() or any(p.is_symlink() for p in path.parents):
            raise InputError("Use a real directory for the vault, not a symbolic link.")
        try:
            if not ephemeral:
                self.process_lock = ProcessLock(path.with_suffix(path.suffix + ".lock"))
            raw = (
                b""
                if ephemeral or not path.exists()
                else (
                    path.read_bytes()
                    if path.stat().st_size <= MAX_VAULT_BYTES
                    else None
                )
            )
            if not ephemeral and path.exists() and raw == b"":
                raise InputError(
                    "The existing vault is empty or truncated. Restore a verified backup."
                )
            if raw is None:
                raise InputError("The encrypted database exceeds 256 MiB.")
            if raw and not raw.startswith(MAGIC):
                raise InputError(
                    "This database is not an encrypted v2 vault. Use the documented migration command."
                )
            if raw and len(raw) < len(MAGIC) + 16 + 12 + 16:
                raise InputError("The encrypted database is incomplete.")
            self.salt = raw[len(MAGIC) : len(MAGIC) + 16] if raw else os.urandom(16)
            key = os.urandom(32) if ephemeral else derive_key(password, self.salt)
            self.cipher = AESGCM(key)
            self.aad = MAGIC + self.salt
            self.db = sqlite3.connect(":memory:", timeout=15, check_same_thread=False)
            self.db.row_factory = sqlite3.Row
            if raw:
                offset = len(self.aad)
                try:
                    snapshot = self.cipher.decrypt(
                        raw[offset : offset + 12], raw[offset + 12 :], self.aad
                    )
                except InvalidTag as exc:
                    raise InputError(
                        "The passphrase is wrong or the encrypted database is damaged."
                    ) from exc
                self.db.deserialize(snapshot)
                self.last_snapshot = snapshot
                if self.db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise InputError(
                        "The decrypted database failed its integrity check."
                    )
            self.db.execute("PRAGMA temp_store=MEMORY")
            self.db.execute("PRAGMA journal_mode=MEMORY")
            self.db.execute("PRAGMA foreign_keys=ON")
            self.db.execute("PRAGMA trusted_schema=OFF")
            if not raw:
                self.db.execute("PRAGMA user_version=2")
                self.last_snapshot = self.db.serialize()
        except BaseException:
            self.close()
            raise

    def ciphertext(self, snapshot: bytes) -> bytes:
        nonce = os.urandom(12)
        return self.aad + nonce + self.cipher.encrypt(nonce, snapshot, self.aad)

    @contextmanager
    def connection(self):
        with self.lock:
            if self.closed:
                raise InputError("The vault is closed.")
            before_changes = self.db.total_changes
            before_schema = self.db.execute("PRAGMA schema_version").fetchone()[0]
            try:
                with self.db:
                    yield self.db
                changed = (
                    self.db.total_changes != before_changes
                    or self.db.execute("PRAGMA schema_version").fetchone()[0]
                    != before_schema
                )
                if changed:
                    snapshot = self.db.serialize()
                    if len(snapshot) > MAX_VAULT_BYTES - 256:
                        raise InputError(
                            "The database reached its 256 MiB safety limit. Remove old history."
                        )
                    if not self.ephemeral:
                        _atomic_ciphertext(self.path, self.ciphertext(snapshot))
                    self.last_snapshot = snapshot
            except BaseException:
                self.db.rollback()
                # executescript can commit implicitly. Restore the last durable
                # state as well as rolling back normal SQL transactions.
                if self.last_snapshot:
                    self.db.deserialize(self.last_snapshot)
                    self.db.execute("PRAGMA foreign_keys=ON")
                    self.db.execute("PRAGMA trusted_schema=OFF")
                    self.db.execute("PRAGMA temp_store=MEMORY")
                    self.db.execute("PRAGMA journal_mode=MEMORY")
                raise

    def backup(self, destination: Path):
        with self.lock:
            if self.closed:
                raise InputError("The vault is closed.")
            raw = self.ciphertext(self.db.serialize())
            with os.fdopen(
                os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb"
            ) as f:
                f.write(raw)
                f.flush()
                os.fsync(f.fileno())

    def close(self):
        with self.lock:
            if self.closed:
                return
            self.closed = True
            if self.db is not None:
                self.db.close()
                self.db = None
            self.last_snapshot = b""
            self.cipher = None
            if self.process_lock is not None:
                self.process_lock.close()


def migrate_plaintext(source: Path, destination: Path, password: str) -> None:
    """Copy a stopped legacy SQLite database into a verified encrypted vault.

    Preserve the source. Deleting a plaintext source is a separate user action.
    """
    if source.resolve() == destination.resolve() or destination.exists():
        raise InputError(
            "Choose a new destination. The source will not be overwritten."
        )
    if (
        source.is_symlink()
        or not source.is_file()
        or source.stat().st_size > MAX_VAULT_BYTES
    ):
        raise InputError("Choose a local SQLite database no larger than 256 MiB.")
    original = sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        if original.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise InputError("The source database failed its integrity check.")
        vault = Vault(destination, password)
        try:
            with vault.lock:
                original.backup(vault.db)
                vault.db.execute("PRAGMA journal_mode=MEMORY")
                snapshot = vault.db.serialize()
                _atomic_ciphertext(destination, vault.ciphertext(snapshot))
        finally:
            vault.close()
        verify = Vault(destination, password)
        verify.close()
    finally:
        original.close()
