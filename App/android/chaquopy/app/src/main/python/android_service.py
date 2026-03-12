import json
import os
import threading
import logging
import traceback

import uvicorn

_server = None
_thread = None
_logger = logging.getLogger("vrclassroom.android_service")
_status_lock = threading.Lock()
_status = {
    "state": "idle",
    "message": "",
    "traceback": "",
}


def _set_status(state, message="", traceback_text=""):
    with _status_lock:
        _status["state"] = state
        _status["message"] = message
        _status["traceback"] = traceback_text


def _get_status_snapshot():
    with _status_lock:
        return dict(_status)


def _trim_traceback(traceback_text, *, max_lines=8):
    lines = [line.rstrip() for line in traceback_text.splitlines() if line.strip()]
    return "\n".join(lines[-max_lines:])


def _run():
    global _server
    _set_status("starting", "Initializing embedded server")

    try:
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
        _set_status("running", "Embedded server thread is running")
        _server.run()
        if _get_status_snapshot()["state"] != "failed":
            _set_status("stopped", "Embedded server stopped")
    except Exception as exc:
        tb = _trim_traceback(traceback.format_exc())
        _logger.exception("Embedded Android server failed")
        _set_status("failed", str(exc) or exc.__class__.__name__, tb)
    finally:
        _server = None


def start_server():
    global _thread
    if _thread and _thread.is_alive():
        return
    _set_status("starting", "Starting embedded server thread")
    _thread = threading.Thread(target=_run, daemon=True)
    _thread.start()


def stop_server():
    global _server
    if _server is not None:
        _set_status("running", "Stopping embedded server")
        _server.should_exit = True
    elif not (_thread and _thread.is_alive()):
        _set_status("stopped", "Embedded server is not running")


def get_status():
    return json.dumps(_get_status_snapshot())
