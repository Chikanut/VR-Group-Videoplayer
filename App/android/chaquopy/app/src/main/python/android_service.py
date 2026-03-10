import os
import threading

import uvicorn

_server = None
_thread = None


def _run():
    global _server
    os.environ.setdefault("VRCLASSROOM_RUNTIME", "android")
    os.environ.setdefault("VRCLASSROOM_DISABLE_ADB", "1")
    os.environ.setdefault("VRCLASSROOM_ANDROID_SUBNET", "192.168.43")
    config = uvicorn.Config("server.main:app", host="0.0.0.0", port=8000, reload=False, log_level="info")
    _server = uvicorn.Server(config)
    _server.run()


def start_server():
    global _thread
    if _thread and _thread.is_alive():
        return
    _thread = threading.Thread(target=_run, daemon=True)
    _thread.start()


def stop_server():
    global _server
    if _server is not None:
        _server.should_exit = True
