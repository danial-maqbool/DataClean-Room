"""Start an encrypted local app, a user worker, or a temporary demonstration."""

from __future__ import annotations
import argparse
import getpass
import json
import os
import sys
import tempfile
from pathlib import Path


def main() -> int:
    if sys.version_info < (3, 11):
        print("Install Python 3.11 or later.", file=sys.stderr)
        return 2
    root = Path(__file__).resolve().parent
    config = json.loads((root / "project.json").read_text(encoding="utf-8"))
    parser = argparse.ArgumentParser(description=config["tagline"])
    parser.add_argument(
        "command",
        nargs="?",
        choices=["serve", "worker", "doctor", "service", "migrate"],
        default="serve",
    )
    parser.add_argument("--port", type=int, default=config["port"])
    parser.add_argument("--data-dir", type=Path, default=root / ".local-data")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Use temporary example data and an in-memory database.",
    )
    parser.add_argument(
        "--keyring",
        action="store_true",
        help="Unlock with the explicitly saved OS credential.",
    )
    parser.add_argument(
        "--passphrase-env",
        metavar="VARIABLE",
        help="Read and remove a password from this environment variable.",
    )
    parser.add_argument(
        "--allow-desktop",
        action="store_true",
        help="Permit per-run confirmation of mouse and keyboard actions.",
    )
    parser.add_argument(
        "--install", action="store_true", help="Install the per-user service."
    )
    parser.add_argument(
        "--remove", action="store_true", help="Remove this app service."
    )
    parser.add_argument(
        "--source", type=Path, help="Stopped legacy SQLite file for migration."
    )
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("Port must be between 0 and 65535.")
    from localdesk.documents import advanced_capabilities
    from localdesk.safety import InputError

    if args.command == "doctor":
        print(
            json.dumps(
                {
                    "python": sys.version,
                    "platform": sys.platform,
                    "capabilities": advanced_capabilities(),
                },
                indent=2,
            )
        )
        return 0
    if args.allow_desktop and (args.command == "worker" or args.command == "service"):
        parser.error(
            "Desktop actions require an interactive app. They are not enabled in a background service."
        )
    if args.demo and args.command not in {"serve", "worker"}:
        parser.error("Demo mode cannot install services or migrate data.")
    temporary = (
        tempfile.TemporaryDirectory(prefix="localfirst-demo-") if args.demo else None
    )
    raw_data = args.data_dir.expanduser().absolute()
    if not temporary and (
        raw_data.is_symlink() or any(parent.is_symlink() for parent in raw_data.parents)
    ):
        print("Use a real local data folder, not a symbolic link.", file=sys.stderr)
        return 1
    data = Path(temporary.name) if temporary else raw_data.resolve()
    try:
        if (
            args.command == "serve"
            and not args.demo
            and not args.no_browser
            and (data / "app.vault.lock").exists()
        ):
            import http.client, webbrowser

            try:
                connection = http.client.HTTPConnection(
                    "127.0.0.1", args.port, timeout=2
                )
                connection.request("GET", "/healthz")
                response = connection.getresponse()
                health = json.loads(response.read(4096))
                connection.close()
                if response.status == 200 and health.get("name") == config["name"]:
                    webbrowser.open(f"http://127.0.0.1:{args.port}")
                    print(
                        "Opened the existing local app. The worker still runs separately."
                    )
                    return 0
            except (OSError, ValueError):
                pass
        if args.command == "service" and args.remove:
            from localdesk.services import remove

            result = remove(root, data, args.port)
            from localdesk.credentials import delete_password

            delete_password(data)
            print(json.dumps(result, indent=2))
            return 0
        password = None
        if not args.demo:
            if args.keyring and not (args.command == "service" and args.install):
                from localdesk.credentials import load_password

                password = load_password(data)
            elif args.passphrase_env:
                password = os.environ.pop(args.passphrase_env, None)
                if not password:
                    raise InputError(
                        "The named password environment variable is empty."
                    )
            else:
                if not sys.stdin.isatty():
                    raise InputError(
                        "Run from a terminal to unlock the vault. For a worker, use the OS keyring. Use --demo for a temporary demonstration."
                    )
                password = getpass.getpass("Vault passphrase (12 or more characters): ")
                if not (data / "app.vault").exists():
                    if password != getpass.getpass("Repeat vault passphrase: "):
                        raise InputError("The passphrases do not match.")
        if args.command == "migrate":
            if not args.source:
                parser.error("Migration needs --source PATH.")
            from localdesk.vault import migrate_plaintext

            migrate_plaintext(args.source, data / "app.vault", password)
            print(
                "Encrypted copy verified. The plaintext source is unchanged. Remove old plaintext copies only after checking the migrated app."
            )
            return 0
        if (
            config["slug"] == "localflow"
            and not args.demo
            and (root / ".localflow/localflow.db").exists()
            and not (data / "app.vault").exists()
        ):
            raise InputError(
                'The first public LocalFlow database exists. Stop the old app, then run migrate --source "'
                + str(root / ".localflow/localflow.db")
                + '".'
            )
        if (
            not args.demo
            and (data / "app.sqlite3").exists()
            and not (data / "app.vault").exists()
        ):
            raise InputError(
                'A legacy plaintext database exists. Run migrate --source "'
                + str(data / "app.sqlite3")
                + '" first.'
            )
        if args.command == "service":
            if not args.install:
                parser.error("Use service --install or service --remove.")
            from localdesk.vault import Vault
            from localdesk.credentials import save_password
            from localdesk.services import install

            vault = Vault(data / "app.vault", password)
            vault.close()
            save_password(data, password)
            print(json.dumps(install(root, data, args.port), indent=2))
            return 0
        from app.service import Application
        from localdesk.server import serve

        app = Application(
            root, data, passphrase=password, allow_desktop=args.allow_desktop
        )
        password = None
        try:
            serve(
                app,
                config,
                args.port,
                not (args.no_browser or args.command == "worker"),
            )
        except OSError:
            app.close()
            raise
        return 0
    except (InputError, ImportError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        if temporary:
            temporary.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
