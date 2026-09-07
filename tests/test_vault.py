"""Adversarial tests for storage, process locking, and encrypted backup recovery."""

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from localdesk.vault import Vault, MAGIC, migrate_plaintext
from localdesk.storage import Store
from localdesk.safety import InputError

PASSWORD = "synthetic vault password 9274"


class VaultTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.path = self.root / "app.vault"
        self.store = None

    def tearDown(self):
        if self.store:
            self.store.close()
        self.temp.cleanup()

    def open(self):
        self.store = Store(self.path, PASSWORD)
        return self.store

    def test_no_plaintext_database_on_disk(self):
        store = self.open()
        store.set("private", "SECRET_TEST_MARKER")
        raw = self.path.read_bytes()
        self.assertTrue(raw.startswith(MAGIC))
        self.assertNotIn(b"SECRET_TEST_MARKER", raw)
        self.assertFalse(list(self.root.glob("*.sqlite*")))
        self.assertFalse(list(self.root.glob("*-wal")))

    def test_roundtrip_correct_password(self):
        store = self.open()
        store.set("private", "value")
        store.close()
        self.store = None
        self.assertEqual(self.open().get("private"), "value")

    def test_wrong_password_does_not_modify_vault(self):
        self.open().set("private", "value")
        self.store.close()
        self.store = None
        before = self.path.read_bytes()
        with self.assertRaises(InputError):
            Store(self.path, "wrong synthetic password")
        self.assertEqual(before, self.path.read_bytes())

    def test_tampered_ciphertext_is_rejected(self):
        self.open().close()
        self.store = None
        raw = bytearray(self.path.read_bytes())
        raw[-1] ^= 1
        self.path.write_bytes(raw)
        with self.assertRaises(InputError):
            Store(self.path, PASSWORD)

    def test_truncated_header_is_rejected(self):
        self.path.write_bytes(MAGIC + b"bad")
        with self.assertRaises(InputError):
            Store(self.path, PASSWORD)

    def test_empty_existing_vault_is_not_overwritten(self):
        self.path.touch()
        with self.assertRaises(InputError):
            Store(self.path, PASSWORD)
        self.assertEqual(self.path.stat().st_size, 0)

    def test_ciphertext_uses_new_nonce(self):
        store = self.open()
        store.set("x", "same")
        first = self.path.read_bytes()
        store.set("x", "same")
        self.assertNotEqual(first, self.path.read_bytes())

    def test_second_writer_is_rejected(self):
        self.open()
        with self.assertRaises(InputError):
            Store(self.path, PASSWORD)

    def test_lock_released_on_close(self):
        self.open().close()
        self.store = None
        self.assertIsNotNone(self.open())

    def test_failed_write_restores_last_durable_state(self):
        store = self.open()
        store.set("x", "old")
        before = self.path.read_bytes()
        with patch(
            "localdesk.vault._atomic_ciphertext",
            side_effect=OSError("simulated disk full"),
        ):
            with self.assertRaises(OSError):
                store.set("x", "new")
        self.assertEqual(store.get("x"), "old")
        self.assertEqual(self.path.read_bytes(), before)

    def test_failed_sql_script_restores_schema(self):
        store = self.open()
        with self.assertRaises(sqlite3.Error):
            with store.connection() as db:
                db.executescript(
                    "CREATE TABLE unexpected(a); INSERT INTO no_such_table VALUES(1);"
                )
        self.assertIsNone(
            store.one("SELECT name FROM sqlite_master WHERE name='unexpected'")
        )

    def test_backup_is_encrypted_and_restorable(self):
        store = self.open()
        store.set("private", "restored")
        destination = self.root / "backup.vault"
        store.backup(destination)
        self.assertTrue(destination.read_bytes().startswith(MAGIC))
        other = Store(destination, PASSWORD)
        try:
            self.assertEqual(other.get("private"), "restored")
        finally:
            other.close()

    def test_backup_refuses_existing_path(self):
        store = self.open()
        destination = self.root / "backup.vault"
        destination.write_bytes(b"keep")
        with self.assertRaises(FileExistsError):
            store.backup(destination)
        self.assertEqual(destination.read_bytes(), b"keep")

    def test_memory_store_does_not_create_database(self):
        self.store = Store(self.path)
        self.store.set("test", "private")
        self.assertFalse(self.path.exists())
        with self.assertRaises(InputError):
            self.store.backup(self.root / "unrecoverable.vault")

    def test_short_password_is_rejected(self):
        with self.assertRaises(InputError):
            Store(self.path, "short")

    def test_closed_store_refuses_operations(self):
        store = self.open()
        store.close()
        with self.assertRaises(InputError):
            store.set("x", "y")

    def test_migration_preserves_source_and_records(self):
        source = self.root / "old.sqlite3"
        with sqlite3.connect(source) as db:
            db.execute("CREATE TABLE old_events(value)")
            db.execute("INSERT INTO old_events VALUES('legacy')")
        db.close()
        before = source.read_bytes()
        migrate_plaintext(source, self.path, PASSWORD)
        self.assertEqual(source.read_bytes(), before)
        self.assertEqual(
            self.open().one("SELECT value FROM old_events")["value"], "legacy"
        )

    def test_migration_refuses_existing_destination(self):
        source = self.root / "old.sqlite"
        source.write_bytes(b"not a db")
        self.path.write_bytes(b"keep")
        with self.assertRaises(InputError):
            migrate_plaintext(source, self.path, PASSWORD)
        self.assertEqual(self.path.read_bytes(), b"keep")

    @unittest.skipIf(
        os.name == "nt", "Creating symbolic links may need a Windows developer setting."
    )
    def test_vault_symlink_is_rejected(self):
        target = self.root / "target"
        target.write_bytes(b"keep")
        self.path.symlink_to(target)
        with self.assertRaises(InputError):
            Store(self.path, PASSWORD)
        self.assertEqual(target.read_bytes(), b"keep")

    @unittest.skipIf(os.name == "nt", "POSIX mode test.")
    def test_ciphertext_file_permissions(self):
        self.open()
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
