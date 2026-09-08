"""Uvicorn launcher for the local FastAPI workbench."""

import ipaddress
import secrets
import socket
import threading
from urllib.parse import urlsplit

import uvicorn

from agent_data_workbench.api import create_app
from agent_data_workbench.workspace.project import Project


def validate_origin(origin: str) -> str:
    """Accept one explicit browser origin, never a URL path or wildcard host."""
    try:
        parsed = urlsplit(origin)
        hostname = parsed.hostname
        port = parsed.port
        if (
            parsed.scheme not in {"http", "https"}
            or not hostname
            or parsed.username is not None
            or parsed.password is not None
            or origin != f"{parsed.scheme}://{parsed.netloc}"
            or port == 0
            or parsed.netloc.endswith(":")
            or any(character.isspace() for character in origin)
        ):
            raise ValueError
        try:
            address = ipaddress.ip_address(hostname)
        except ValueError:
            labels = hostname.split(".")
            if any(
                not label
                or label.startswith("-")
                or label.endswith("-")
                or not all(
                    character.isascii() and (character.isalnum() or character == "-")
                    for character in label
                )
                for label in labels
            ):
                raise ValueError from None
        else:
            if address.is_unspecified:
                raise ValueError
            hostname = f"[{address.compressed}]" if address.version == 6 else str(address)
    except ValueError as exc:
        raise ValueError(
            "Public origin must be an http(s) origin with an explicit hostname, "
            "without credentials, paths, queries or fragments"
        ) from exc
    authority = hostname
    if port is not None and port != {"http": 80, "https": 443}[parsed.scheme]:
        authority += f":{port}"
    return f"{parsed.scheme}://{authority}"


class WorkbenchServer:
    """Own the socket and Uvicorn lifecycle, with loopback-only defaults."""

    def __init__(
        self,
        project: Project,
        port: int = 0,
        *,
        host: str = "127.0.0.1",
        public_origin: str | None = None,
        token: str | None = None,
    ):
        if not 0 <= port <= 65535:
            raise ValueError("Port must be 0–65535")
        if public_origin is not None:
            public_origin = validate_origin(public_origin)
        self.token = token or secrets.token_urlsafe(32)
        self._socket = socket.socket(
            socket.AF_INET6 if ":" in host else socket.AF_INET, socket.SOCK_STREAM
        )
        try:
            self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._socket.bind((host, port))
            self.server_port = self._socket.getsockname()[1]
            self.origin = public_origin or f"http://127.0.0.1:{self.server_port}"
            self.app = create_app(project, origin=self.origin, token=self.token)
            self._server = uvicorn.Server(
                uvicorn.Config(
                    self.app,
                    host=host,
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
