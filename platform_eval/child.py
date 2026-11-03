"""One evaluation per process: isolate research globals and reclaim model memory."""

import json
import os
import sys
import threading
from pathlib import Path

from .config import Settings
from .research import execute


def main():
    supervisor = int(os.getenv("RAG_SUPERVISOR_PID", str(os.getppid())))

    def watch_parent():
        while True:
            if os.getppid() != supervisor:
                os._exit(74)
            threading.Event().wait(2)

    threading.Thread(target=watch_parent, daemon=True).start()
    request = json.loads(Path(sys.argv[1]).read_text())
    execute(Settings(), **request)


if __name__ == "__main__":
    main()
