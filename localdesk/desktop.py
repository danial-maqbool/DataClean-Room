"""Explicitly armed desktop actions. No shell, eval, scripts, or unattended execution."""

from __future__ import annotations
import io
import time
from .safety import InputError, integer

TYPES = {"move", "click", "write", "press", "hotkey", "scroll", "wait", "screenshot"}


def validate_actions(actions):
    if not isinstance(actions, list) or not 1 <= len(actions) <= 50:
        raise InputError("A desktop step needs 1 to 50 actions.")
    validated = []
    for action in actions:
        if not isinstance(action, dict) or action.get("type") not in TYPES:
            raise InputError("Unknown desktop action.")
        kind = action["type"]
        item = {"type": kind}
        if kind in {"move", "click"}:
            item["x"] = integer(action.get("x"), 0, 100000, "Mouse x")
            item["y"] = integer(action.get("y"), 0, 100000, "Mouse y")
            if kind == "click":
                item["button"] = action.get("button", "left")
                if item["button"] not in {"left", "right", "middle"}:
                    raise InputError("Choose a valid mouse button.")
                item["clicks"] = integer(action.get("clicks", 1), 1, 3, "Click count")
        elif kind == "write":
            text = action.get("text", "")
            if not isinstance(text, str) or len(text) > 4000 or not text.isascii():
                raise InputError(
                    "Keyboard text must be ASCII and no longer than 4,000 characters."
                )
            item["text"] = text
        elif kind in {"press", "hotkey"}:
            keys = action.get("keys", [action.get("key", "enter")])
            if isinstance(keys, str):
                keys = [keys]
            if (
                not isinstance(keys, list)
                or not 1 <= len(keys) <= 5
                or any(not isinstance(k, str) or len(k) > 20 for k in keys)
            ):
                raise InputError("Use 1 to 5 named keys.")
            item["keys"] = keys
        elif kind == "scroll":
            item["amount"] = integer(
                action.get("amount", 1), -100, 100, "Scroll amount"
            )
        elif kind == "wait":
            value = action.get("seconds", 1)
            if (
                isinstance(value, bool)
                or not isinstance(value, (float, int))
                or not 0 <= value <= 10
            ):
                raise InputError("A wait must be between 0 and 10 seconds.")
            item["seconds"] = float(value)
        elif kind == "screenshot":
            item["filename"] = str(action.get("filename", "desktop.png"))
            if not item["filename"].lower().endswith(".png"):
                raise InputError("A desktop screenshot must use a .png file name.")
        validated.append(item)
    return validated


def execute(actions, context, write, *, permitted=False, dry_run=True, backend=None):
    actions = validate_actions(actions)
    if dry_run:
        return f"{len(actions)} desktop actions validated. No mouse, keyboard, or screenshot action was executed."
    if not permitted:
        raise InputError(
            "Desktop actions are locked. Start with --allow-desktop and confirm this specific run."
        )
    if backend is None:
        try:
            import pyautogui as backend
        except (ImportError, KeyError, OSError) as exc:
            raise InputError(
                "Desktop automation needs PyAutoGUI and an unlocked graphical user session."
            ) from exc
    backend.FAILSAFE = True
    backend.PAUSE = 0.15
    screen = backend.size()
    for action in actions:
        if action["type"] in {"move", "click"} and (
            action["x"] >= screen[0] or action["y"] >= screen[1]
        ):
            raise InputError("A mouse coordinate is outside the primary screen.")
        if action["type"] in {"press", "hotkey"} and any(
            k not in backend.KEYBOARD_KEYS for k in action["keys"]
        ):
            raise InputError("A named keyboard key is not supported.")
    deadline = time.monotonic() + 120

    def pause(seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            context.check()
            if time.monotonic() > deadline:
                raise InputError("Desktop actions reached the 120 second limit.")
            backend.failSafeCheck()
            time.sleep(min(0.05, max(0, end - time.monotonic())))

    # The user has time to move the pointer to a screen corner before input starts.
    pause(3)
    for action in actions:
        context.check()
        backend.failSafeCheck()
        if time.monotonic() > deadline:
            raise InputError("Desktop actions reached the 120 second limit.")
        kind = action["type"]
        if kind == "move":
            backend.moveTo(action["x"], action["y"], duration=0.2)
        elif kind == "click":
            backend.click(
                action["x"],
                action["y"],
                clicks=action["clicks"],
                interval=0.1,
                button=action["button"],
            )
        elif kind == "write":
            for start in range(0, len(action["text"]), 32):
                context.check()
                backend.failSafeCheck()
                backend.write(action["text"][start : start + 32], interval=0.01)
        elif kind == "press":
            backend.press(action["keys"])
        elif kind == "hotkey":
            backend.hotkey(*action["keys"])
        elif kind == "scroll":
            backend.scroll(action["amount"])
        elif kind == "wait":
            pause(action["seconds"])
        elif kind == "screenshot":
            stream = io.BytesIO()
            backend.screenshot().save(stream, format="PNG")
            write(action["filename"], stream.getvalue())
    return f"{len(actions)} confirmed desktop actions completed. Source-file state depends on the target application."
