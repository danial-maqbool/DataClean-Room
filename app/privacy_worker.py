"""Run parsers in a child process with a parent-enforced deadline."""

import base64
import json
import sys


def main():
    try:
        if sys.platform == "linux":
            import resource

            resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
            resource.setrlimit(resource.RLIMIT_CPU, (120, 120))
            resource.setrlimit(resource.RLIMIT_FSIZE, (40 * 1024**2, 40 * 1024**2))
        request = json.loads(sys.stdin.read(38_000_001))
        raw = base64.b64decode(request["raw"], validate=True)
        from .native import process

        response = process(
            raw,
            str(request["suffix"]),
            str(request["action"]),
            request.get("options", {}),
        )
    except Exception as exc:
        response = {"error": str(exc)[:500] or "The native privacy operation failed."}
    print(json.dumps(response))


if __name__ == "__main__":
    main()
