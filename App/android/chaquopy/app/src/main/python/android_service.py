import os
import threading
import logging

import uvicorn

_server = None
_thread = None
_logger = logging.getLogger("vrclassroom.android_service")


def _run():
    global _server
    os.environ.setdefault("VRCLASSROOM_RUNTIME", "android")
    os.environ.setdefault("VRCLASSROOM_DISABLE_ADB", "1")
    runtime = os.environ.get("VRCLASSROOM_RUNTIME", "<unset>")
    subnet = os.environ.get("VRCLASSROOM_ANDROID_SUBNET")
    _logger.info(
        "android_service старт: VRCLASSROOM_RUNTIME=%s, VRCLASSROOM_ANDROID_SUBNET=%s",
        runtime,
        subnet if subnet is not None else "<unset>",
    )
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
