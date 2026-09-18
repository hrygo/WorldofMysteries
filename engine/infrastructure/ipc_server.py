"""Authenticated local IPC foundation. No world handlers, DB writes or model access.

Developer entrypoint: python -m infrastructure.ipc_server --socket PATH --token-fd FD
The parent writes exactly 64 lowercase hexadecimal bytes to a dedicated pipe and
closes its write end. The FD number, never the credential, may appear in argv.
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import errno
import fcntl
import hmac
import os
from pathlib import Path
import re
import selectors
import signal
import socket
import stat
import sys
import time
from typing import Any

from pydantic import ValidationError

from contracts.envelope import EngineIPCEnvelope, HandshakeRequest, HandshakeResponse
from .ipc_framing import FrameError, read_frame, write_frame

CAPABILITIES = ("system.health", "system.shutdown")
TOKEN_PATTERN = re.compile(r"[0-9a-f]{64}")


class BootstrapError(RuntimeError):
    """Startup failed safely; messages contain no path, incoming data or credential."""


def read_bootstrap_token(fd: int, timeout: float = 5.0) -> str:
    """Consume a dedicated inherited pipe with a bounded size and absolute deadline."""
    try:
        if fd < 0 or not stat.S_ISFIFO(os.fstat(fd).st_mode):
            raise BootstrapError("A dedicated credential pipe is required")
        os.set_blocking(fd, False)
        data = bytearray()
        deadline = time.monotonic() + timeout
        with selectors.DefaultSelector() as selector:
            selector.register(fd, selectors.EVENT_READ)
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not selector.select(remaining):
                    raise BootstrapError("Credential pipe timed out")
                chunk = os.read(fd, 65 - len(data))
                if not chunk:
                    break
                data.extend(chunk)
                if len(data) > 64:
                    raise BootstrapError("Invalid bootstrap credential")
        token = data.decode("ascii")
        if TOKEN_PATTERN.fullmatch(token) is None:
            raise BootstrapError("Invalid bootstrap credential")
        return token
    except (OSError, UnicodeError, ValueError):
        raise BootstrapError("Invalid credential pipe") from None
    finally:
        if fd >= 0:
            with contextlib.suppress(OSError):
                os.close(fd)


class SocketLease:
    """Serialize startup; only remove an owned, unchanged, confirmed stale socket.

    The empty lock inode intentionally persists. Unlinking it after unlocking could
    let a third process acquire a different inode while the next owner is running.
    This is not an isolation boundary against arbitrary code running as this UID.
    """

    def __init__(self, path: Path):
        self.path = Path(os.path.abspath(path))
        self.directory_fd: int | None = None
        self.lock_fd: int | None = None
        self.identity: tuple[int, int] | None = None

    def _stat(self) -> os.stat_result:
        return os.stat(self.path.name, dir_fd=self.directory_fd, follow_symlinks=False)

    @staticmethod
    def _identity(info: os.stat_result) -> tuple[int, int]:
        return info.st_dev, info.st_ino

    def bind(self) -> socket.socket:
        if self.directory_fd is not None:
            raise BootstrapError("Socket lease is already active")
        sock: socket.socket | None = None
        try:
            # Application Support/Runtime is created privately by the parent App.
            self.directory_fd = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            parent = os.fstat(self.directory_fd)
            if parent.st_uid != os.getuid() or stat.S_IMODE(parent.st_mode) & 0o077:
                raise BootstrapError("Runtime directory must be private")
            self.lock_fd = os.open(self.path.name + ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW,
                                   0o600, dir_fd=self.directory_fd)
            lock = os.fstat(self.lock_fd)
            if (not stat.S_ISREG(lock.st_mode) or lock.st_uid != os.getuid()
                    or stat.S_IMODE(lock.st_mode) & 0o077 or lock.st_nlink != 1):
                raise BootstrapError("Unsafe runtime lock")
            fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                old = self._stat()
            except FileNotFoundError:
                old = None
            if old is not None:
                if not stat.S_ISSOCK(old.st_mode) or old.st_uid != os.getuid():
                    raise BootstrapError("Refusing to replace a non-owned socket")
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
                    probe.settimeout(0.2)
                    code = probe.connect_ex(str(self.path))
                if code != errno.ECONNREFUSED:
                    raise BootstrapError("Socket is active or cannot be safely replaced")
                if self._identity(self._stat()) != self._identity(old):
                    raise BootstrapError("Socket changed during recovery")
                os.unlink(self.path.name, dir_fd=self.directory_fd)
            if self._identity(os.stat(self.path.parent)) != self._identity(parent):
                raise BootstrapError("Runtime directory changed during startup")
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.bind(str(self.path))
            self.identity = self._identity(self._stat())
            os.chmod(self.path.name, 0o600, dir_fd=self.directory_fd, follow_symlinks=False)
            sock.setblocking(False)
            sock.listen(16)
            return sock
        except Exception:
            if sock is not None:
                sock.close()
            self.close()
            raise

    def close(self) -> None:
        if self.directory_fd is not None and self.identity is not None:
            with contextlib.suppress(FileNotFoundError):
                info = self._stat()
                if stat.S_ISSOCK(info.st_mode) and self._identity(info) == self.identity:
                    os.unlink(self.path.name, dir_fd=self.directory_fd)
            self.identity = None
        for name in ("lock_fd", "directory_fd"):
            fd = getattr(self, name)
            if fd is not None:
                os.close(fd)
                setattr(self, name, None)


def response(request: EngineIPCEnvelope, *, payload: dict[str, Any] | None = None,
             code: str | None = None) -> dict[str, Any]:
    wire = dict(kind="response", protocol_version="1.0", request_id=request.request_id,
                trace_id=request.trace_id, status="error" if code else "ok")
    if code:
        wire["error"] = {"code": code, "message": "The local request could not be completed.",
                         "retryable": False}
    else:
        wire["payload"] = payload if payload is not None else {}
    return EngineIPCEnvelope.model_validate(wire).model_dump()


class LocalIPCServer:
    """System-only transport. Each connection authenticates, then runs bounded FIFO I/O."""

    def __init__(self, path: Path, token: str, *, handshake_timeout: float = 5.0,
                 max_connections: int = 16):
        if TOKEN_PATTERN.fullmatch(token) is None:
            raise BootstrapError("Invalid bootstrap credential")
        if handshake_timeout <= 0 or max_connections < 1:
            raise ValueError("Invalid connection limits")
        self._token = token
        self._lease = SocketLease(path)
        self._handshake_timeout = handshake_timeout
        self._max_connections = max_connections
        self._server: asyncio.Server | None = None
        self._tasks: set[asyncio.Task[None]] = set()
        self._stopping = asyncio.Event()

    async def start(self) -> None:
        if self._server is not None or self._stopping.is_set():
            raise BootstrapError("Server cannot be started in its current state")
        sock = self._lease.bind()
        try:
            self._server = await asyncio.start_unix_server(self._accept, sock=sock,
                                                           cleanup_socket=False)
        except BaseException:
            sock.close()
            self._lease.close()
            raise

    def _accept(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        if len(self._tasks) >= self._max_connections or self._stopping.is_set():
            writer.close()
            return
        task = asyncio.create_task(self._handle(reader, writer))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _request(self, reader: asyncio.StreamReader,
                       writer: asyncio.StreamWriter) -> EngineIPCEnvelope:
        raw = await read_frame(reader)
        try:
            request = EngineIPCEnvelope.model_validate(raw)
            if request.kind != "request":
                raise FrameError("A client must send requests")
            return request
        except ValidationError:
            # Only echo validated correlation fields, never arbitrary error details.
            if (raw.get("kind") == "request" and all(isinstance(raw.get(k), str) and raw[k]
                    for k in ("request_id", "trace_id"))):
                stub = EngineIPCEnvelope(kind="request", protocol_version="1.0",
                                         request_id=raw["request_id"], trace_id=raw["trace_id"],
                                         method="system.handshake", payload={})
                code = ("protocol_version_mismatch" if isinstance(raw.get("protocol_version"), str)
                        and raw["protocol_version"] != "1.0" else "schema_invalid")
                await write_frame(writer, response(stub, code=code))
            raise FrameError("Invalid request envelope") from None

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            async with asyncio.timeout(self._handshake_timeout):
                req = await self._request(reader, writer)
                try:
                    hello = HandshakeRequest.model_validate(req.payload)
                except ValidationError:
                    hello = None
                if (req.method != "system.handshake" or hello is None
                        or not hmac.compare_digest(hello.session_token, self._token)):
                    await write_frame(writer, response(req, code="authorization_denied"))
                    return
                if "1.0" not in hello.supported_protocols:
                    await write_frame(writer, response(req, code="protocol_version_mismatch"))
                    return
                welcome = HandshakeResponse(engine_version="0.1.0", engine_build="ipc-foundation-1",
                                            python_version=".".join(map(str, sys.version_info[:3])),
                                            protocol_version="1.0", capabilities=list(CAPABILITIES))
                await write_frame(writer, response(req, payload=welcome.model_dump()))
                del hello
            while not self._stopping.is_set():
                req = await self._request(reader, writer)
                if req.method not in CAPABILITIES:
                    await write_frame(writer, response(req, code="method_not_supported"))
                elif req.payload:
                    await write_frame(writer, response(req, code="schema_invalid"))
                elif req.method == "system.health":
                    await write_frame(writer, response(req, payload={"transport_ready": True,
                        "world_ready": False, "model_ready": False, "voice_ready": False}))
                else:
                    await write_frame(writer, response(req, payload={"shutdown_requested": True}))
                    self._stopping.set()
                    return
        except (EOFError, FrameError, TimeoutError, ConnectionError, OSError):
            pass  # A failed connection never opens or mutates a world.
        finally:
            writer.close()
            with contextlib.suppress(ConnectionError, OSError, TimeoutError):
                async with asyncio.timeout(1.0):
                    await writer.wait_closed()

    def request_stop(self) -> None:
        self._stopping.set()

    async def wait_stopped(self) -> None:
        await self._stopping.wait()

    async def close(self) -> None:
        self._stopping.set()
        try:
            if self._server is not None:
                self._server.close()
            tasks = list(self._tasks)
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if self._server is not None:
                await self._server.wait_closed()
                self._server = None
        finally:
            self._lease.close()
            self._token = ""  # Best effort, not a promise of zeroized Python memory.


async def _run(path: Path, token: str) -> None:
    server = LocalIPCServer(path, token)
    loop = asyncio.get_running_loop()
    installed = []
    try:
        await server.start()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, server.request_stop)
            installed.append(sig)
        await server.wait_stopped()
    finally:
        for sig in installed:
            loop.remove_signal_handler(sig)
        await server.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Local Engine system transport")
    parser.add_argument("--socket", required=True, type=Path)
    parser.add_argument("--token-fd", required=True, type=int)
    args = parser.parse_args()
    try:
        token = read_bootstrap_token(args.token_fd)
        asyncio.run(_run(args.socket, token))
    except (BootstrapError, OSError, ValueError):
        print("Local Engine startup failed; check the private runtime and bootstrap channel.",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
