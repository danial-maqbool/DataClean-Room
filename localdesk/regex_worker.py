"""Small regular-expression worker. The parent enforces a one-second limit."""

import json
import re
import sys

if __name__ == "__main__":
    data = json.load(sys.stdin)
    match = re.search(data["pattern"], data["text"])
    print(
        json.dumps(
            (match.group(1) if match.lastindex else match.group(0)) if match else ""
        )
    )
