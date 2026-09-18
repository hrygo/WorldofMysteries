"""Real independent-process UDS tests. No database/AI success is simulated."""
import asyncio
import json
import os
from pathlib import Path
import secrets
import socket
import stat
import struct
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from jsonschema import Draft202012Validator

from infrastructure.ipc_framing import encode_frame
from infrastructure.ipc_server import BootstrapError, LocalIPCServer, SocketLease, read_bootstrap_token

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "contracts/protocol/engine_ipc.schema.json").read_text())
VALIDATOR = Draft202012Validator(SCHEMA)


def request(method="system.health", payload=None, request_id="req_1"):
    return dict(kind="request", protocol_version="1.0", trace_id="trace_中文",
                request_id=request_id, method=method, payload={} if payload is None else payload)


def recv_exact(client, n):
    result = b""
    while len(result) < n:
        part = client.recv(n - len(result))
        if not part:
            raise EOFError
        result += part
    return result


def receive(client):
    size = struct.unpack("!I", recv_exact(client, 4))[0]
    assert 0 < size <= 1024 * 1024
    value = json.loads(recv_exact(client, size))
    VALIDATOR.validate(value)
    return value


class RunningEngine:
    def __init__(self, path, token=None):
        self.path = path
        self.token = token or secrets.token_hex(32)
        read_fd, write_fd = os.pipe()
        env = dict(os.environ, PYTHONPATH=str(ROOT / "engine"))
        try:
            self.process = subprocess.Popen([sys.executable, "-m", "infrastructure.ipc_server",
                "--socket", str(path), "--token-fd", str(read_fd)], cwd=ROOT, env=env,
                pass_fds=(read_fd,), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        finally:
            os.close(read_fd)
        try:
            os.write(write_fd, self.token.encode())
        finally:
            os.close(write_fd)
        self.output = None

    def ready(self):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise AssertionError(f"Engine exited with {self.process.returncode}")
            try:
                with self.client():
                    return self
            except (OSError, EOFError):
                time.sleep(0.02)
        raise AssertionError("Engine did not become ready")

    def client(self, token=None):
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(2)
        try:
            client.connect(str(self.path))
            client.sendall(encode_frame(request("system.handshake", {
                "app_version": "0.1.0", "app_build": "test", "supported_protocols": ["1.0"],
                "session_token": token or self.token})))
            hello = receive(client)
            assert hello["status"] == "ok"
            assert set(hello["payload"]["capabilities"]) == {"system.health", "system.shutdown"}
            return client
        except BaseException:
            client.close()
            raise

    def stop(self):
        if self.process.poll() is None:
            self.process.terminate()
        try:
            self.output = self.process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.output = self.process.communicate(timeout=3)
            pytest.fail("Engine failed to terminate with active or partial connections")
        assert all(self.token.encode() not in output for output in self.output)


@pytest.fixture
def runtime():
    # Short canonical paths are required by macOS sockaddr_un; pytest tmp_path may exceed it.
    with tempfile.TemporaryDirectory(prefix="wom-ipc-") as directory:
        yield Path(directory).resolve() / "engine.sock"


@pytest.fixture
def engine(runtime):
    running = RunningEngine(runtime)
    try:
        yield running.ready()
    finally:
        running.stop()


def test_real_process_handshake_health_and_reconnect(engine):
    assert engine.process.pid != os.getpid()
    assert stat.S_IMODE(engine.path.stat().st_mode) == 0o600
    assert engine.token not in " ".join(engine.process.args)
    for _ in range(2):
        with engine.client() as client:
            client.sendall(encode_frame(request()))
            reply = receive(client)
            assert reply["request_id"] == "req_1" and reply["trace_id"] == "trace_中文"
            assert reply["payload"] == {"transport_ready": True, "world_ready": False,
                                         "model_ready": False, "voice_ready": False}


def test_private_pipe_consumed_and_closed():
    r, w = os.pipe()
    os.write(w, b"a" * 64)
    os.close(w)
    assert read_bootstrap_token(r) == "a" * 64
    with pytest.raises(OSError):
        os.fstat(r)


@pytest.mark.parametrize("data", [b"", b"a" * 63, b"a" * 65, b"Z" * 64, b"\xff" * 64,
                                 b"a" * 64 + b"\n"])
def test_invalid_pipe_credentials(data):
    r, w = os.pipe()
    os.write(w, data)
    os.close(w)
    with pytest.raises(BootstrapError):
        read_bootstrap_token(r)


def test_pipe_no_eof_has_absolute_timeout():
    r, w = os.pipe()
    try:
        os.write(w, b"a" * 64)
        with pytest.raises(BootstrapError):
            read_bootstrap_token(r, timeout=0.03)
    finally:
        os.close(w)


def test_regular_file_is_not_bootstrap_pipe(tmp_path):
    file = tmp_path / "secret"
    file.write_text("a" * 64)
    fd = os.open(file, os.O_RDONLY)
    with pytest.raises(BootstrapError):
        read_bootstrap_token(fd)
    assert file.read_text() == "a" * 64


@pytest.mark.parametrize("hello", [request(), request("system.handshake", {}),
    request("system.handshake", {"app_version": "1", "app_build": "1",
        "supported_protocols": ["1.0"], "session_token": "0" * 64})])
def test_unauthenticated_request_never_opens_service(engine, hello):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(2)
        client.connect(str(engine.path))
        client.sendall(encode_frame(hello))
        assert receive(client)["error"]["code"] == "authorization_denied"
        assert client.recv(1) == b""


@pytest.mark.parametrize("method", ["world.open", "story.submit_advice", "story.cancel_pending_turn", "invented"])
def test_missing_business_methods_fail_closed(engine, method):
    with engine.client() as client:
        client.sendall(encode_frame(request(method)))
        assert receive(client)["error"]["code"] == "method_not_supported"
        client.sendall(encode_frame(request()))
        assert receive(client)["payload"]["world_ready"] is False


def test_version_and_schema_errors(engine):
    for changes, code in [({"protocol_version": "2.0"}, "protocol_version_mismatch"),
                          ({"method": None}, "schema_invalid")]:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(2)
            client.connect(str(engine.path))
            client.sendall(encode_frame({**request(), **changes}))
            assert receive(client)["error"]["code"] == code
            assert client.recv(1) == b""


def test_multiple_and_fragmented_requests_keep_correlation(engine):
    with engine.client() as client:
        one = encode_frame(request(request_id="req_fragmented"))
        for part in (one[:1], one[1:3], one[3:8], one[8:]):
            client.sendall(part)
        assert receive(client)["request_id"] == "req_fragmented"
        client.sendall(b"".join(encode_frame(request(request_id=f"req_{n}")) for n in range(10)))
        assert [receive(client)["request_id"] for _ in range(10)] == [f"req_{n}" for n in range(10)]


def test_parallel_clients(engine):
    def call(n):
        with engine.client() as client:
            client.sendall(encode_frame(request(request_id=f"parallel_{n}")))
            return receive(client)["request_id"]
    with ThreadPoolExecutor(max_workers=6) as pool:
        assert set(pool.map(call, range(12))) == {f"parallel_{n}" for n in range(12)}


@pytest.mark.parametrize("raw", [struct.pack("!I", 0), struct.pack("!I", 1024 * 1024 + 1),
    struct.pack("!I", 2) + b"[]", struct.pack("!I", 13) + b'{"x":1,"x":2}'])
def test_malformed_frames_close_only_their_connection(engine, raw):
    with engine.client() as client:
        client.sendall(raw)
        assert client.recv(1) == b""
    with engine.client() as healthy:
        healthy.sendall(encode_frame(request()))
        assert receive(healthy)["status"] == "ok"


def test_authenticated_shutdown_cleans_owned_socket(engine):
    with engine.client() as client:
        client.sendall(encode_frame(request("system.shutdown")))
        assert receive(client)["payload"] == {"shutdown_requested": True}
    assert engine.process.wait(timeout=3) == 0
    assert not engine.path.exists()


def test_signal_exit_with_idle_and_partial_connections(engine):
    with engine.client(), socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as partial:
        partial.connect(str(engine.path))
        partial.sendall(b"\x00")
        engine.process.terminate()
        assert engine.process.wait(timeout=3) == 0
    assert not engine.path.exists()


def test_second_process_cannot_steal_live_socket(engine):
    identity = engine.path.stat().st_ino
    second = RunningEngine(engine.path)
    try:
        assert second.process.wait(timeout=3) == 1
        assert engine.path.stat().st_ino == identity
        with engine.client() as client:
            client.sendall(encode_frame(request()))
            assert receive(client)["status"] == "ok"
    finally:
        second.stop()


def test_crash_restart_and_old_token_rejected(runtime):
    first = RunningEngine(runtime).ready()
    first.process.kill()
    first.stop()
    assert runtime.exists()
    second = RunningEngine(runtime)
    try:
        second.ready()
        with pytest.raises(AssertionError):
            second.client(token=first.token)
        with second.client():
            pass
    finally:
        second.stop()
    assert not runtime.exists()


def test_non_socket_and_symlink_not_deleted(runtime):
    runtime.write_text("retain")
    for use_symlink in [False, True]:
        if use_symlink:
            target = runtime.with_name("retained.txt")
            runtime.rename(target)
            runtime.symlink_to(target)
        lease = SocketLease(runtime)
        with pytest.raises((BootstrapError, OSError)):
            lease.bind()
        assert runtime.read_text() == "retain"


def test_runtime_directory_must_be_private(runtime):
    runtime.parent.chmod(0o755)
    try:
        with pytest.raises(BootstrapError):
            SocketLease(runtime).bind()
        assert not runtime.exists()
    finally:
        runtime.parent.chmod(0o700)


def test_cleanup_does_not_remove_replacement(runtime):
    lease = SocketLease(runtime)
    owned = lease.bind()
    runtime.unlink()
    runtime.write_text("replacement")
    owned.close()
    lease.close()
    assert runtime.read_text() == "replacement"


async def test_handshake_timeout_and_connection_bound(runtime):
    server = LocalIPCServer(runtime, "a" * 64, handshake_timeout=0.05, max_connections=1)
    await server.start()
    r1, w1 = await asyncio.open_unix_connection(runtime)
    await asyncio.sleep(0)
    r2, w2 = await asyncio.open_unix_connection(runtime)
    try:
        assert await asyncio.wait_for(r2.read(1), 1) == b""
        assert await asyncio.wait_for(r1.read(1), 1) == b""
    finally:
        w1.close()
        w2.close()
        await w1.wait_closed()
        await w2.wait_closed()
        await server.close()


def test_existing_external_listener_not_unlinked(runtime):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
        listener.bind(str(runtime))
        listener.listen()
        inode = runtime.stat().st_ino
        with pytest.raises(BootstrapError):
            SocketLease(runtime).bind()
        assert runtime.stat().st_ino == inode


def test_symlinked_lock_is_not_followed(runtime):
    target = runtime.with_name("retained-file")
    target.write_text("do not touch")
    runtime.with_name(runtime.name + ".lock").symlink_to(target)
    with pytest.raises(OSError):
        SocketLease(runtime).bind()
    assert target.read_text() == "do not touch"
    assert not runtime.exists()


def test_empty_system_payload_required(engine):
    with engine.client() as client:
        for method in ("system.health", "system.shutdown"):
            client.sendall(encode_frame(request(method, {"unexpected": True})))
            assert receive(client)["error"]["code"] == "schema_invalid"
    assert engine.process.poll() is None


def test_authenticated_incompatible_protocol_offer(engine):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(2)
        client.connect(str(engine.path))
        client.sendall(encode_frame(request("system.handshake", {
            "app_version": "1", "app_build": "1", "supported_protocols": ["2.0"],
            "session_token": engine.token})))
        assert receive(client)["error"]["code"] == "protocol_version_mismatch"
        assert client.recv(1) == b""


async def test_duplicate_start_does_not_lose_original_lease(runtime):
    server = LocalIPCServer(runtime, "a" * 64)
    await server.start()
    inode = runtime.stat().st_ino
    try:
        with pytest.raises(BootstrapError):
            await server.start()
        assert runtime.stat().st_ino == inode
    finally:
        await server.close()
    assert not runtime.exists()


@pytest.mark.parametrize("parent_pid", [0, 1, -1])
@pytest.mark.asyncio
async def test_invalid_launch_parent_refuses_socket(tmp_path, parent_pid):
    from infrastructure.ipc_server import _run
    path = tmp_path / "parent.sock"
    with pytest.raises(BootstrapError):
        await _run(path, "a" * 64, parent_pid)
    assert not path.exists()
