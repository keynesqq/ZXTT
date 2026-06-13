"""ZXTT 本地 Web 服务：作战卡 + 快照 + 设置（对照 ZXReport app_server.py）。"""
from __future__ import annotations

import json
import mimetypes
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

from core.paths import DATA_DIR, ROOT

DEFAULT_PORT = 8765
MAX_POST_BYTES = 1 << 20
_heavy_post_lock = threading.Semaphore(1)


class PayloadTooLargeError(ValueError):
    pass


def _read_post_body(handler: BaseHTTPRequestHandler) -> bytes:
    try:
        length = int(handler.headers.get("Content-Length") or 0)
    except ValueError:
        length = 0
    if length < 0 or length > MAX_POST_BYTES:
        raise PayloadTooLargeError("请求体过大")
    return handler.rfile.read(length) if length else b"{}"


def _parse_post_json(handler: BaseHTTPRequestHandler) -> dict:
    raw = _read_post_body(handler)
    try:
        return json.loads(raw.decode("utf-8")) if raw else {}
    except (ValueError, UnicodeDecodeError):
        return {}


def _pid_path(port: int) -> Path:
    return DATA_DIR / f"server-{port}.pid"


def _start_lock_path(port: int) -> Path:
    return DATA_DIR / f"server-{port}.start.lock"


def _log_path() -> Path:
    return DATA_DIR / "server.log"


def _acquire_start_lock(port: int, *, timeout: float = 8.0) -> bool:
    path = _start_lock_path(port)
    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.time() + timeout
    while time.time() < deadline:
        if is_server_running(port):
            return False
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                os.write(fd, str(os.getpid()).encode())
            finally:
                os.close(fd)
            return True
        except FileExistsError:
            if is_server_running(port):
                return False
            time.sleep(0.15)
    return False


def _release_start_lock(port: int) -> None:
    _start_lock_path(port).unlink(missing_ok=True)


def is_server_running(port: int = DEFAULT_PORT) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def wait_for_server(port: int, *, timeout: float = 8.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if is_server_running(port):
            return True
        time.sleep(0.15)
    return False


def start_background_server(port: int = DEFAULT_PORT) -> int | None:
    if is_server_running(port):
        return None
    if not _acquire_start_lock(port):
        return None

    _log_path().parent.mkdir(parents=True, exist_ok=True)
    log_file = _log_path().open("a", encoding="utf-8")

    pyw = ROOT / ".venv" / "Scripts" / "pythonw.exe"
    executable = str(pyw) if pyw.is_file() else sys.executable
    cmd = [
        executable,
        str(ROOT / "run.py"),
        "serve",
        "--foreground",
        "--port",
        str(port),
        "--no-browser",
    ]
    kwargs: dict = {
        "cwd": str(ROOT),
        "stdout": log_file,
        "stderr": subprocess.STDOUT,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]

    try:
        if is_server_running(port):
            return None
        proc = subprocess.Popen(cmd, **kwargs)
    finally:
        log_file.close()
        _release_start_lock(port)
    _pid_path(port).write_text(str(proc.pid), encoding="utf-8")
    return proc.pid


def stop_server(port: int = DEFAULT_PORT) -> bool:
    pid_file = _pid_path(port)
    if not pid_file.is_file():
        return not is_server_running(port)

    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/F"],
                capture_output=True,
                check=False,
                creationflags=subprocess.CREATE_NO_WINDOW,  # type: ignore[attr-defined]
            )
        else:
            os.kill(pid, signal.SIGTERM)
    except (OSError, ValueError):
        pass
    finally:
        pid_file.unlink(missing_ok=True)

    deadline = time.time() + 3.0
    while time.time() < deadline:
        if not is_server_running(port):
            return True
        time.sleep(0.15)
    return False


def ensure_server(port: int = DEFAULT_PORT) -> str:
    if is_server_running(port):
        return "running"
    start_background_server(port)
    if not wait_for_server(port):
        raise OSError(f"后台服务未能在 127.0.0.1:{port} 启动，详见 data/server.log")
    return "started"


def open_in_browser(port: int = DEFAULT_PORT, start_path: str = "/") -> str:
    base = f"http://127.0.0.1:{port}"
    url = base + (start_path if start_path.startswith("/") else "/" + start_path)
    webbrowser.open(url)
    return url


def server_url(port: int = DEFAULT_PORT, start_path: str = "/") -> str:
    base = f"http://127.0.0.1:{port}"
    return base + (start_path if start_path.startswith("/") else "/" + start_path)


def _safe_file(rel: str) -> Path | None:
    try:
        path = (ROOT / rel).resolve()
        root = ROOT.resolve()
        if not str(path).startswith(str(root)) or not path.is_file():
            return None
        return path
    except OSError:
        return None


class AppHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        pass

    def _send_bytes(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, code: int, data: dict) -> None:
        self._send_bytes(code, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _send_html(self, html: str, code: int = 200) -> None:
        self._send_bytes(code, html.encode("utf-8"), "text/html; charset=utf-8")

    def _send_file(self, path: Path) -> None:
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        if path.suffix.lower() in (".html", ".htm"):
            ctype = "text/html; charset=utf-8"
        elif path.suffix.lower() == ".js":
            ctype = "application/javascript; charset=utf-8"
        self._send_bytes(200, path.read_bytes(), ctype)

    def do_GET(self) -> None:
        path = unquote(self.path.split("?", 1)[0])

        if path == "/api/health":
            self._send_json(200, {"ok": True, "service": "zxtt"})
            return

        if path == "/api/settings":
            from report.settings import build_settings_view

            self._send_json(200, build_settings_view())
            return

        if path == "/settings":
            from report.settings_html import build_settings_page

            self._send_html(build_settings_page())
            return

        if path in ("/", "/reports/index.html"):
            hub = _safe_file("reports/index.html")
            if hub is None:
                self.send_error(404)
                return
            self._send_file(hub)
            return

        if path in ("/snapshot", "/reports/snapshot.html"):
            snap = _safe_file("reports/snapshot.html")
            if snap is None:
                self.send_error(404)
                return
            self._send_file(snap)
            return

        if path.startswith("/reports/"):
            rel = path.lstrip("/")
            file_path = _safe_file(rel)
            if file_path:
                self._send_file(file_path)
                return

        if path.startswith("/data/"):
            rel = path.lstrip("/")
            file_path = _safe_file(rel)
            if file_path:
                self._send_file(file_path)
                return

        self.send_error(404)

    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0]
        heavy = path == "/api/settings"
        if heavy and not _heavy_post_lock.acquire(blocking=False):
            self._send_json(409, {"ok": False, "error": "服务器正处理其它任务，请稍后再试"})
            return
        try:
            self._handle_post(path)
        except PayloadTooLargeError:
            self._send_json(413, {"ok": False, "error": "请求体过大"})
        finally:
            if heavy:
                _heavy_post_lock.release()

    def _handle_post(self, path: str) -> None:
        if path != "/api/settings":
            self.send_error(404)
            return
        from report.settings import apply_settings

        payload = _parse_post_json(self)
        try:
            result = apply_settings(payload)
            self._send_json(200, result)
        except ValueError as e:
            self._send_json(400, {"ok": False, "error": str(e)})
        except Exception as e:
            self._send_json(500, {"ok": False, "error": str(e)})


def run_app_server(
    *,
    port: int = DEFAULT_PORT,
    open_browser: bool = True,
    start_path: str = "/",
) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", port), AppHandler)
    base = f"http://127.0.0.1:{port}"
    url = base + (start_path if start_path.startswith("/") else "/" + start_path)
    print(f"ZXTT: {base}")
    print(f"  作战卡 {base}/reports/index.html")
    print(f"  快照 {base}/reports/snapshot.html")
    print(f"  设置 {base}/settings")
    print("Ctrl+C 停止")

    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        server.server_close()
        _pid_path(port).unlink(missing_ok=True)


__all__ = [
    "DEFAULT_PORT",
    "ensure_server",
    "is_server_running",
    "open_in_browser",
    "run_app_server",
    "server_url",
    "start_background_server",
    "stop_server",
    "wait_for_server",
]
