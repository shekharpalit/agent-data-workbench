"""Uvicorn launcher for the local FastAPI workbench."""

import secrets
import socket
import threading

import uvicorn

from .api import create_app
from .project import Project


class WorkbenchServer:
    """Own the loopback socket and Uvicorn lifecycle, including ephemeral port selection."""

    def __init__(self, project: Project, port: int = 0):
        if not 0 <= port <= 65535:
            raise ValueError("Port must be 0–65535")
        self.token = secrets.token_urlsafe(32)
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self._socket.bind(("127.0.0.1", port))
            self.server_port = self._socket.getsockname()[1]
            self.origin = f"http://127.0.0.1:{self.server_port}"
            self.app = create_app(project, origin=self.origin, token=self.token)
            self._server = uvicorn.Server(
                uvicorn.Config(
                    self.app,
                    host="127.0.0.1",
                    port=self.server_port,
                    access_log=False,
                    log_level="error",
                    proxy_headers=False,
                    server_header=False,
                    ws="none",
                )
            )
        except BaseException:
            self._socket.close()
            raise

    @property
    def started(self) -> bool:
        return self._server.started

    def serve_forever(self):
        self._server.run(sockets=[self._socket])

    def shutdown(self):
        self._server.should_exit = True

    def server_close(self):
        self._socket.close()


def serve(project: Project, *, port: int = 0, open_browser: bool = False):
    import webbrowser

    server = WorkbenchServer(project, port)
    url = server.origin + "/#token=" + server.token
    print(f"Local workbench: {url}", flush=True)
    print("Keep this URL private. Press Ctrl-C to stop.", flush=True)
    stopped = threading.Event()

    def open_when_ready():
        while not stopped.wait(0.05):
            if server.started:
                webbrowser.open(url)
                return

    if open_browser:
        threading.Thread(target=open_when_ready, daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stopped.set()
        server.server_close()
