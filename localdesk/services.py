"""Install and remove one visible, per-user background service. No administrator access."""

from __future__ import annotations
import getpass
import hashlib
import json
import os
import plistlib
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET
from .safety import InputError, unique_write


def service_label(root: Path, data: Path) -> str:
    slug = re.sub("[^a-z0-9]", "", root.name.lower())[:32] or "app"
    return (
        "org.localfirst."
        + slug
        + "."
        + hashlib.sha256(str(data.resolve()).encode()).hexdigest()[:10]
    )


def service_spec(
    root: Path,
    data: Path,
    port: int,
    *,
    platform: str | None = None,
    home: Path | None = None,
    executable: str | None = None,
) -> dict:
    platform = platform or sys.platform
    home = home or Path.home()
    root, data = root.resolve(), data.resolve()
    exe = executable or sys.executable
    if any(
        "\n" in str(v) or "\r" in str(v) or "\x00" in str(v) for v in (root, data, exe)
    ):
        raise InputError("Service paths cannot contain control characters.")
    if not isinstance(port, int) or not 1024 <= port <= 65535:
        raise InputError("Choose a fixed local service port from 1024 to 65535.")
    label = service_label(root, data)
    args = [
        exe,
        str(root / "run.py"),
        "worker",
        "--keyring",
        "--no-browser",
        "--data-dir",
        str(data),
        "--port",
        str(port),
    ]
    if platform.startswith("linux"):

        def quote(s):
            return (
                '"'
                + s.replace("\\", "\\\\")
                .replace('"', '\\"')
                .replace("%", "%%")
                .replace("$", "$$")
                + '"'
            )

        content = "\n".join(
            [
                "[Unit]",
                "Description=Local First " + root.name,
                "After=graphical-session.target",
                "",
                "[Service]",
                "Type=simple",
                "ExecStart=" + " ".join(quote(x) for x in args),
                "Restart=on-failure",
                "RestartSec=30",
                "UMask=0077",
                "NoNewPrivileges=yes",
                "",
                "[Install]",
                "WantedBy=default.target",
                "",
            ]
        )
        return {
            "label": label,
            "path": home / ".config/systemd/user" / f"{label}.service",
            "content": content.encode(),
            "install": [
                ["systemctl", "--user", "daemon-reload"],
                ["systemctl", "--user", "enable", "--now", label + ".service"],
            ],
            "remove": [["systemctl", "--user", "disable", "--now", label + ".service"]],
            "status": ["systemctl", "--user", "is-active", label + ".service"],
        }
    if platform == "darwin":
        path = home / "Library/LaunchAgents" / f"{label}.plist"
        content = plistlib.dumps(
            {
                "Label": label,
                "ProgramArguments": args,
                "RunAtLoad": True,
                "KeepAlive": {"SuccessfulExit": False},
                "ProcessType": "Background",
                "Umask": 63,
            }
        )
        domain = f"gui/{getattr(os, 'getuid', lambda: 501)()}"
        return {
            "label": label,
            "path": path,
            "content": content,
            "install": [["launchctl", "bootstrap", domain, str(path)]],
            "remove": [["launchctl", "bootout", domain + "/" + label]],
            "status": ["launchctl", "print", domain + "/" + label],
        }
    if platform == "win32":
        if (
            Path(exe).name.lower() == "python.exe"
            and Path(exe).with_name("pythonw.exe").exists()
        ):
            args[0] = str(Path(exe).with_name("pythonw.exe"))
        ns = "http://schemas.microsoft.com/windows/2004/02/mit/task"
        ET.register_namespace("", ns)

        def el(parent, name, text=None, **attributes):
            x = ET.SubElement(parent, "{" + ns + "}" + name, attributes)
            if text is not None:
                x.text = text
            return x

        task = ET.Element("{" + ns + "}Task", {"version": "1.4"})
        reg = el(task, "RegistrationInfo")
        el(reg, "Description", "Visible local app service: " + root.name)
        triggers = el(task, "Triggers")
        logon = el(triggers, "LogonTrigger")
        el(logon, "Enabled", "true")
        el(logon, "UserId", getpass.getuser())
        principals = el(task, "Principals")
        principal = el(principals, "Principal", id="User")
        el(principal, "UserId", getpass.getuser())
        el(principal, "LogonType", "InteractiveToken")
        el(principal, "RunLevel", "LeastPrivilege")
        settings = el(task, "Settings")
        el(settings, "MultipleInstancesPolicy", "IgnoreNew")
        el(settings, "DisallowStartIfOnBatteries", "false")
        el(settings, "StopIfGoingOnBatteries", "false")
        el(settings, "ExecutionTimeLimit", "PT0S")
        el(settings, "Enabled", "true")
        actions = el(task, "Actions", Context="User")
        execute = el(actions, "Exec")
        el(execute, "Command", args[0])
        el(execute, "Arguments", subprocess.list2cmdline(args[1:]))
        el(execute, "WorkingDirectory", str(root))
        path = data / (label + ".xml")
        return {
            "label": label,
            "path": path,
            "content": ET.tostring(task, encoding="utf-16", xml_declaration=True),
            "install": [
                ["schtasks", "/Create", "/TN", label, "/XML", str(path)],
                ["schtasks", "/Run", "/TN", label],
            ],
            "remove": [
                ["schtasks", "/End", "/TN", label],
                ["schtasks", "/Delete", "/TN", label, "/F"],
            ],
            "status": ["schtasks", "/Query", "/TN", label, "/FO", "LIST"],
        }
    raise InputError(
        "Automatic startup supports Windows, macOS, and Linux user sessions."
    )


def install(root: Path, data: Path, port: int):
    spec = service_spec(root, data, port)
    path = spec["path"]
    if path.exists():
        raise InputError(
            "This service file already exists. Remove this app service before installing it again."
        )
    unique_write(path, spec["content"])
    try:
        for command in spec["install"]:
            result = subprocess.run(
                command, capture_output=True, text=True, timeout=30, check=False
            )
            if result.returncode:
                raise InputError(
                    "The OS rejected service installation: "
                    + (result.stderr or result.stdout)[:400]
                )
    except BaseException:
        # Keep the definition for diagnosis. Do not claim success or remove
        # unrelated OS jobs during cleanup.
        raise
    return {
        "installed": True,
        "label": spec["label"],
        "definition": str(path),
        "scope": "current user",
    }


def remove(root: Path, data: Path, port: int):
    spec = service_spec(root, data, port)
    path = spec["path"]
    if not path.is_file() or path.is_symlink() or path.read_bytes() != spec["content"]:
        raise InputError(
            "The service definition is missing or was changed. Refusing to remove an unrelated service."
        )
    failures = []
    for command in spec["remove"]:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=30, check=False
        )
        # Ending an already stopped Windows task is harmless. The following
        # deletion still has to succeed before the definition is removed.
        if result.returncode and not (command[0] == "schtasks" and "/End" in command):
            failures.append((result.stderr or result.stdout)[:300])
    if failures:
        raise InputError(
            "The OS could not fully remove the service: " + "; ".join(failures)
        )
    path.unlink()
    return {"removed": True, "label": spec["label"]}
