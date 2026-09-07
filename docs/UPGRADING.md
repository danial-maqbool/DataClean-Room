# Upgrade and migration

Stop the old worker. Keep a separate backup before replacing source files.
Version 0.2.0 uses `.local-data/app.vault`, not a plaintext SQLite file.
The migration command reads the old database and writes a new encrypted copy. It preserves the source.

```sh
.venv/bin/python run.py migrate --source .local-data/app.sqlite3
.venv/bin/python run.py
```

Use `.venv\Scripts\python.exe` on Windows. Enter the same new passphrase for migration and startup.
The first public LocalFlow release used a different path:

```sh
.venv/bin/python run.py migrate --source .localflow/localflow.db
```

LocalFlow converts its old step-list workflow format into the new graph format.
The old run table is preserved in the migrated database. New runs use the new job-history table.
The converter does not execute a workflow during migration.

Check workflow definitions, folders, and records after migration. Create and verify an encrypted backup.
Old plaintext database files, WAL files, exports, and earlier backups remain on disk until you remove them yourself.
Deleting a file is not guaranteed secure erasure, especially on SSDs. Use OS disk encryption for storage protection.
Do not overwrite or delete the only old copy before verifying the migrated app.

## Restore an encrypted backup

Stop the app. Keep the current vault as a separate copy. Place a verified backup at `.local-data/app.vault`.
Use the passphrase that protected that backup. Keep the data directory private.
Exports and original documents are separate files. A database backup does not include them.
