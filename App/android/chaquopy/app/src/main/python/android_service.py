import os
import threading

import uvicorn

_server = None
_thread = None
_lock = threading.Lock()


def _run():
    global _server
    os.environ.setdefault("VRCLASSROOM_DISABLE_ADB", "1")
    os.environ.setdefault("VRCLASSROOM_ANDROID_SUBNET", "192.168.43")
    config = uvicorn.Config("server.main:app", host="0.0.0.0", port=8000, reload=False, log_level="info")
    _server = uvicorn.Server(config)
    _server.run()


def _is_running() -> bool:
    return _thread is not None and _thread.is_alive()


def start_server():
    global _thread
    with _lock:
        if _is_running():
            return
        _thread = threading.Thread(target=_run, daemon=True)
        _thread.start()


def ensure_server_running():
    start_server()


def stop_server():
    global _server
    if _server is not None:
        _server.should_exit = True
