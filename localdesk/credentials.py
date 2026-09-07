"""Optional OS-protected credentials for an explicitly installed user service."""

from __future__ import annotations
import hashlib
from pathlib import Path
from .safety import InputError


def account(data: Path) -> tuple[str, str]:
    return (
        "org.localfirst.vault",
        hashlib.sha256(str(data.resolve()).encode()).hexdigest(),
    )


def secure_backend():
    try:
        import keyring
        from keyring.backend import get_all_keyring
    except ImportError as exc:
        raise InputError("Install keyring before enabling automatic startup.") from exc
    allowed = (
        "keyring.backends.Windows",
        "keyring.backends.macOS",
        "keyring.backends.SecretService",
        "keyring.backends.kwallet",
    )
    choices = []
    for backend in get_all_keyring():
        try:
            if type(backend).__module__.startswith(allowed) and backend.priority > 0:
                choices.append(backend)
        except Exception:
            continue
    if not choices:
        raise InputError(
            "No supported secure OS credential store is available. Use an interactive vault password instead."
        )
    return max(choices, key=lambda b: b.priority)


def load_password(data: Path) -> str:
    service, user = account(data)
    try:
        result = secure_backend().get_password(service, user)
    except InputError:
        raise
    except Exception as exc:
        raise InputError("The OS credential store is locked or unavailable.") from exc
    if not result:
        raise InputError(
            "No vault password is saved. Run service --install from an interactive terminal first."
        )
    return result


def save_password(data: Path, password: str):
    service, user = account(data)
    try:
        secure_backend().set_password(service, user, password)
    except InputError:
        raise
    except Exception as exc:
        raise InputError(
            "The OS credential store did not save the vault password."
        ) from exc


def delete_password(data: Path):
    """Remove only this data folder's saved credential after service removal."""
    service, user = account(data)
    backend = secure_backend()
    try:
        if backend.get_password(service, user) is not None:
            backend.delete_password(service, user)
    except Exception as exc:
        raise InputError(
            "The service was removed, but its saved credential could not be deleted. Remove that credential in the OS credential manager."
        ) from exc
