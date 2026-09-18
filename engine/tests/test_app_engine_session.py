"""Compile production Swift, then exercise the real independent Python Engine.

The required target is macOS with Swift installed. No fake success/skip when that
prerequisite is missing. Linux can also run this as supplementary compatibility.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import selectors
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time

import pytest

ROOT = Path(__file__).resolve().parents[2]
SWIFT = ROOT / 'macos-app/WorldOfMysteries'


@pytest.fixture(scope='module')
def app_driver(tmp_path_factory):
    compiler = shutil.which('swiftc')
    assert compiler, 'Production App–Engine integration requires the target Swift toolchain'
    binary = tmp_path_factory.mktemp('swift-engine') / 'driver'
    sources = ['IPCEnvelope', 'IPCFrameCodec', 'EngineRuntimeModels',
               'EngineSocketTransport', 'EngineIPCClient', 'EngineProcessManager', 'EngineConnectionState', 'AppState']
    # The production ArtifactContext declaration is Foundation-only but shares a
    # file with SwiftUI-dependent artwork. Extract that declaration byte-for-byte;
    # AppState and every connection/process implementation are compiled in full.
    text = (SWIFT / 'Artifacts/ArtifactModels.swift').read_text()
    context = text[text.index('public struct ArtifactContext:'):text.index('public enum ArtifactRiskBand:')]
    context_file = binary.parent / 'ArtifactContext.swift'
    context_file.write_text('import Foundation\n' + context)
    # Supplementary Linux verification uses matching static Swift libraries: the
    # supplied dynamic Observation library has an unresolved threading symbol.
    # Target macOS CI uses the normal dynamic toolchain without this option.
    platform_flags = ['-static-stdlib'] if sys.platform == 'linux' else []
    result = subprocess.run([compiler, '-swift-version', '6', '-strict-concurrency=complete', *platform_flags,
        *[str(SWIFT / f'{name}.swift') for name in sources],
        str(context_file), str(Path(__file__).parent / 'fixtures/app_engine_driver.swift'), '-o', str(binary)],
        capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
    return binary


@pytest.mark.parametrize('mode', ['normal', 'wrong-token', 'crash', 'cancel-start', 'app-state', 'app-reconnect', 'app-bounded-reconnect', 'app-stop-during-start'])
def test_real_swift_app_engine_lifecycle(app_driver, mode):
    with tempfile.TemporaryDirectory(prefix='wom-app-') as runtime:
        command = [str(app_driver), mode, sys.executable, str(ROOT / 'engine'), runtime]
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stdout + result.stderr
        assert f'PASS {mode}' in result.stdout
        assert list(Path(runtime).iterdir()) == [], 'Per-launch runtime directory was not cleaned'


def test_engine_stops_when_swift_parent_is_force_quit(app_driver):
    with tempfile.TemporaryDirectory(prefix='wom-app-') as runtime:
        app = subprocess.Popen([str(app_driver), 'hold', sys.executable, str(ROOT / 'engine'), runtime],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        child = None
        try:
            with selectors.DefaultSelector() as ready:
                ready.register(app.stdout, selectors.EVENT_READ)
                assert ready.select(15), 'App did not launch Engine'
            line = app.stdout.readline()
            assert line, app.stderr.read()
            record = json.loads(line)
            child = record['pid']
            socket_path = Path(record['socket'])
            assert socket_path.exists()
            app.kill()
            app.wait(timeout=3)
            deadline = time.monotonic() + 4
            while socket_path.exists() and time.monotonic() < deadline:
                time.sleep(0.05)
            assert not socket_path.exists(), 'Engine survived parent death'
        finally:
            if app.poll() is None:
                app.kill()
                app.wait(timeout=3)
            # Only our recorded child, and only if it is still present, is cleaned up.
            if child is not None and 'socket_path' in locals() and socket_path.exists():
                try:
                    os.kill(child, 9)
                except ProcessLookupError:
                    pass
            app.communicate(timeout=3)


def _receive(peer):
    def exact(size):
        value = b''
        while len(value) < size:
            part = peer.recv(size - len(value))
            if not part:
                raise EOFError
            value += part
        return value
    return json.loads(exact(struct.unpack('!I', exact(4))[0]))


def _frame(value):
    body = json.dumps(value, separators=(',', ':')).encode()
    return struct.pack('!I', len(body)) + body


@pytest.mark.parametrize('variant', ['fragmented', 'wrong-trace', 'wrong-request',
                                   'oversize', 'duplicate-key', 'timeout', 'invalid-health'])
def test_production_client_rejects_bad_peers(app_driver, variant):
    errors = []
    with tempfile.TemporaryDirectory(prefix='wom-peer-') as directory:
        path = str(Path(directory) / 'p.sock')
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
            server.bind(path)
            os.chmod(path, 0o600)
            server.listen(1)
            server.settimeout(10)

            def serve():
                try:
                    with server.accept()[0] as peer:
                        peer.settimeout(3)
                        hello = _receive(peer)
                        welcome = {'kind': 'response', 'protocol_version': '1.0',
                            'trace_id': hello['trace_id'], 'request_id': hello['request_id'],
                            'status': 'ok', 'payload': {'engine_version': '0.1', 'engine_build': 'test',
                            'python_version': '3.14.7', 'protocol_version': '1.0', 'capabilities': ['system.health']}}
                        peer.sendall(_frame(welcome))
                        request = _receive(peer)
                        value = {'kind': 'response', 'protocol_version': '1.0',
                            'trace_id': request['trace_id'], 'request_id': request['request_id'],
                            'status': 'ok', 'payload': {'transport_ready': True, 'world_ready': False,
                                                      'model_ready': False, 'voice_ready': False}}
                        if variant == 'wrong-trace': value['trace_id'] = 'wrong'
                        if variant == 'wrong-request': value['request_id'] = 'wrong'
                        if variant == 'invalid-health': value['payload']['world_ready'] = 'true'
                        wire = _frame(value)
                        if variant == 'oversize': wire = struct.pack('!I', 1048577)
                        if variant == 'duplicate-key':
                            body = wire[4:-1] + b',"status":"ok"}'
                            wire = struct.pack('!I', len(body)) + body
                        if variant == 'timeout': time.sleep(0.6)
                        elif variant == 'fragmented':
                            for i in range(0, len(wire), 3):
                                peer.sendall(wire[i:i + 3])
                                time.sleep(0.001)
                        else: peer.sendall(wire)
                        time.sleep(0.1)
                except (BrokenPipeError, ConnectionResetError):
                    pass
                except Exception as error:
                    errors.append(error)
            thread = threading.Thread(target=serve, daemon=True)
            thread.start()
            expected = 'ok' if variant == 'fragmented' else 'error'
            result = subprocess.run([str(app_driver), 'peer', path, expected, variant],
                                    capture_output=True, text=True, timeout=8)
            thread.join(timeout=4)
            assert not thread.is_alive(), 'Peer fixture did not stop'
            assert not errors, errors
            assert result.returncode == 0, result.stdout + result.stderr
            assert f'PASS peer {expected}' in result.stdout
