#!/usr/bin/env python3
"""Entry point for VR Classroom Control Server."""
import os
import threading
import time
import webbrowser

import uvicorn

from server.config import load_config
from server.main import app


def open_browser_on_start(port: int) -> None:
    """Open local UI in default browser shortly after server launch."""
    # Small delay allows uvicorn to bind the port before browser loads the page.
    time.sleep(1.5)
    url = f"http://127.0.0.1:{port}"
    try:
        opened = webbrowser.open(url)
        if opened:
            print(f"[INFO] Browser opened: {url}", flush=True)
        else:
            print(f"[WARN] Could not auto-open browser. Open manually: {url}", flush=True)
    except Exception as exc:
        print(f"[WARN] Browser auto-open failed ({exc}). Open manually: {url}", flush=True)

if __name__ == "__main__":
    os.environ.setdefault("VRCLASSROOM_RUNTIME", "desktop")
    config = load_config()
    port = config.get("serverPort", 8000)

    print("=" * 52, flush=True)
    print(" VR Classroom Control Server (Windows EXE)", flush=True)
    print("=" * 52, flush=True)
    print(f"[INFO] Starting server on http://127.0.0.1:{port}", flush=True)
    print("[INFO] Press Ctrl+C to stop server", flush=True)

    threading.Thread(target=open_browser_on_start, args=(port,), daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=port, reload=False)
