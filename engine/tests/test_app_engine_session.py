"""Compile production Swift, then exercise the real independent Python Engine.

The required target is macOS with Swift installed. No fake success/skip when that
prerequisite is missing. Linux can also run this as supplementary compatibility.
"""
from __future__ import annotations

from contextlib import closing
import json
import os
from pathlib import Path
import selectors
import shutil
import socket
import sqlite3
import struct
import subprocess
import sys
import tempfile
import threading
import time

import pytest

ROOT = Path(__file__).resolve().parents[2]
SWIFT = ROOT / 'macos-app/WorldOfMysteries'
ENGINE_DIR = ROOT / 'engine'
ENGINE_PACKAGES = ('domain', 'application', 'infrastructure', 'ai', 'contracts')
WORLD_DIRECTORY = 'engineering-golden001'
UNSUPPORTED_TEXT = '先问问医生今天还有没有别的预约。'

sys.path.insert(0, str(ROOT / 'scripts'))
import build_story_content as content_builder  # noqa: E402


@pytest.fixture(scope='module')
def app_driver(tmp_path_factory):
    compiler = shutil.which('swiftc')
    assert compiler, 'Production App–Engine integration requires the target Swift toolchain'
    binary = tmp_path_factory.mktemp('swift-engine') / 'driver'
    sources = ['IPCEnvelope', 'IPCFrameCodec', 'MediaProtocol', 'EngineRuntimeModels',
               'EngineSocketTransport', 'EngineIPCClient', 'EngineProcessManager', 'EngineConnectionState',
               'StorySessionControl', 'StoryRequestJournal', 'StorySessionModel', 'AppState']
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


# ---------------------------------------------------------------------------
# Real Swift App → independent Engine → disk first turn
# ---------------------------------------------------------------------------

HOST_SQLITE_SHIM = '''"""Test dependency: host SQLite stand-in for the packaged extension."""
from __future__ import annotations

import sqlite3 as _host

sqlite_version = _host.sqlite_version
sqlite_version_info = _host.sqlite_version_info


def __getattr__(name):
    return getattr(_host, name)
'''

LAUNCHER_WRAPPER = '''"""Test launcher wrapper injected by engine/tests; production code is unchanged.

The production entrypoint stays byte-for-byte in
``infrastructure/_ipc_server_production.py``. This wrapper only declares the
host SQLite driver — the same compatibility injection repository tests pass as
``expected_sqlite_version`` — and installs a one-shot fault hook on the real
``StoryRuntime`` when ``WOM_TEST_RUNTIME_FAULT`` names a fault plan. Core
services, repositories and the IPC server keep their production behaviour, and
no production code path gains a fault switch.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3

from . import database_manager
from . import story_runtime
from . import _ipc_server_production as production

database_manager.SQLITE_VERSION = sqlite3.sqlite_version
_FAULT_ENV = "WOM_TEST_RUNTIME_FAULT"


def _fault_hook(stage: str) -> None:
    configured = os.environ.get(_FAULT_ENV)
    if not configured:
        return
    plan_path = Path(configured)
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    stages = plan.get("stages") or []
    if stage not in stages:
        return
    skip = plan.get("skip") or 0
    if isinstance(skip, int) and skip > 0:
        plan["skip"] = skip - 1
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        return
    plan["stages"] = [item for item in stages if item != stage]
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    if plan.get("action") == "exit":
        os._exit(70)
    raise RuntimeError("injected runtime fault: " + stage)


_original_open = story_runtime.StoryRuntime.open.__func__


async def _open_with_fault(cls, config, **kwargs):
    kwargs.setdefault("fault_hook", _fault_hook)
    return await _original_open(cls, config, **kwargs)


story_runtime.StoryRuntime.open = classmethod(_open_with_fault)

raise SystemExit(production.main())
'''


@pytest.fixture(scope='module')
def story_engine(tmp_path_factory):
    """Staged module tree: production packages plus a test-only launcher wrapper."""

    staged = tmp_path_factory.mktemp('story-engine')
    for name in ENGINE_PACKAGES:
        shutil.copytree(ENGINE_DIR / name, staged / name,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    entry = staged / 'infrastructure/ipc_server.py'
    production_bytes = entry.read_bytes()
    (staged / 'infrastructure/_ipc_server_production.py').write_bytes(production_bytes)
    entry.write_text(LAUNCHER_WRAPPER, encoding='utf-8')
    (staged / '_wom_sqlite3.py').write_text(HOST_SQLITE_SHIM, encoding='utf-8')
    # The artifact is produced by the same build script the packaging step uses.
    content_builder.write_artifact(
        staged / 'infrastructure/story_content/canon.db', content_builder.build_payload())
    # Only the entrypoint file was replaced; the production copy is byte-identical.
    assert (staged / 'infrastructure/_ipc_server_production.py').read_bytes() == production_bytes
    assert production_bytes == (ENGINE_DIR / 'infrastructure/ipc_server.py').read_bytes()
    return staged


def _run_story(app_driver, story_engine, mode, home, data_root, runtime, *, fault=None, timeout=120):
    environment = dict(os.environ)
    # CoreFoundation resolves Application Support from CFFIXED_USER_HOME, not HOME,
    # so both are redirected: the App journal must never touch real user data.
    environment['HOME'] = str(home)
    environment['CFFIXED_USER_HOME'] = str(home)
    # Never let a pre-commit hook redirect the child repositories at this repo.
    for key in ('GIT_DIR', 'GIT_INDEX_FILE', 'GIT_WORK_TREE', 'GIT_COMMON_DIR',
                'GIT_OBJECT_DIRECTORY', 'WOM_TEST_RUNTIME_FAULT'):
        environment.pop(key, None)
    if fault is not None:
        plan = home / 'fault-plan.json'
        plan.write_text(json.dumps(fault), encoding='utf-8')
        environment['WOM_TEST_RUNTIME_FAULT'] = str(plan)
    return subprocess.run(
        [str(app_driver), mode, sys.executable, str(story_engine), str(runtime), str(data_root)],
        capture_output=True, text=True, timeout=timeout, env=environment)


def _facts(result, mode):
    assert result.returncode == 0, f'{mode} failed\n{result.stdout}\n{result.stderr}'
    assert f'PASS {mode}' in result.stdout, result.stdout + result.stderr
    for line in result.stdout.splitlines():
        if line.startswith('STORY '):
            return json.loads(line[len('STORY '):])
    raise AssertionError(f'No story facts emitted\n{result.stdout}\n{result.stderr}')


def _world_counts(data_root):
    world = Path(data_root) / 'Worlds' / WORLD_DIRECTORY / 'world.db'
    assert world.is_file(), f'Missing world database: {world}'
    with closing(sqlite3.connect(f'file:{world}?mode=ro', uri=True)) as connection:
        def count(table):
            return connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]

        return {
            'commits': count('domain_commits'),
            'intakes': count('turn_intake_commands'),
            'sessions': count('story_sessions'),
            'bootstraps': count('story_session_bootstraps'),
        }


@pytest.fixture
def story_session(tmp_path):
    """Isolated HOME, data root and a short runtime socket namespace."""

    home = tmp_path / 'home'
    data_root = tmp_path / 'data'
    home.mkdir()
    data_root.mkdir()
    # AF_UNIX sun_path is capped at 104 bytes; pytest's tmp path is already long.
    runtime = Path(tempfile.mkdtemp(prefix='wom-story-runtime-'))
    try:
        yield home, data_root, runtime
    finally:
        shutil.rmtree(runtime, ignore_errors=True)


def test_real_story_first_turn_reopens_across_processes(app_driver, story_engine, story_session):
    home, data_root, runtime = story_session

    opened = _facts(_run_story(app_driver, story_engine, 'story-open', home, data_root, runtime),
                    'story-open')
    assert opened['state'] == 'ready' and opened['turn'] == 0
    assert opened['supported_advice'] == ['先别问医生病人的事，我想看看他的反应。']

    submitted = _facts(_run_story(app_driver, story_engine, 'story-submit', home, data_root, runtime),
                       'story-submit')
    assert submitted['state'] == 'completed' and submitted['turn'] == 1
    assert submitted['session_id'] == opened['session_id']
    assert '医生的停顿' in submitted['clues']
    journal = (home / 'Library/Application Support/WorldofMysteries/Engineering/Golden001/Journal'
               / 'first-turn-request.json')
    assert journal.is_file(), 'Client retry journal must stay inside the isolated user home'

    reopened = _facts(_run_story(app_driver, story_engine, 'story-reopen', home, data_root, runtime),
                      'story-reopen')
    assert reopened['state'] == 'completed' and reopened['turn'] == 1
    assert reopened['session_id'] == submitted['session_id']
    assert reopened['story_revision'] == 1
    assert reopened['clues'] == submitted['clues']
    assert _world_counts(data_root) == {
        'commits': 2, 'intakes': 1, 'sessions': 1, 'bootstraps': 1}


def test_real_story_lost_ack_recovers_without_recommitting(app_driver, story_engine, story_session):
    home, data_root, runtime = story_session
    _facts(_run_story(app_driver, story_engine, 'story-open', home, data_root, runtime), 'story-open')

    # The Engine commits the first turn and then dies before answering the client.
    lost = _facts(_run_story(app_driver, story_engine, 'story-submit-lost-ack', home, data_root,
                             runtime, fault={'action': 'exit', 'stages': ['after_commit']}),
                  'story-submit-lost-ack')
    assert lost['state'] == 'completed' and lost['turn'] == 1
    committed = _world_counts(data_root)
    assert committed == {'commits': 2, 'intakes': 1, 'sessions': 1, 'bootstraps': 1}

    # A brand-new App process only reads; the durable result is never re-committed.
    recovered = _facts(_run_story(app_driver, story_engine, 'story-reopen', home, data_root, runtime),
                       'story-reopen')
    assert recovered['session_id'] == lost['session_id']
    assert recovered['turn'] == 1
    assert _world_counts(data_root) == committed


def test_real_story_pending_request_waits_for_explicit_continuation(
        app_driver, story_engine, story_session):
    home, data_root, runtime = story_session
    _facts(_run_story(app_driver, story_engine, 'story-open', home, data_root, runtime), 'story-open')

    # Received advice is durable, the domain commit is not: the App must not retry by itself.
    interrupted = _facts(_run_story(app_driver, story_engine, 'story-submit-interrupted',
                                    home, data_root, runtime,
                                    fault={'action': 'exit', 'stages': ['before_commit']}),
                         'story-submit-interrupted')
    assert interrupted['state'] in {'pending', 'recovering', 'failed'}
    assert interrupted['turn'] == 0
    pending = _world_counts(data_root)
    assert pending == {'commits': 1, 'intakes': 1, 'sessions': 1, 'bootstraps': 1}

    # The restarted process reads the pending intent and only continues when asked.
    resumed = _facts(_run_story(app_driver, story_engine, 'story-continue-pending', home, data_root,
                                runtime),
                     'story-continue-pending')
    assert resumed['state'] == 'completed' and resumed['turn'] == 1
    assert _world_counts(data_root) == {
        'commits': 2, 'intakes': 1, 'sessions': 1, 'bootstraps': 1}


def test_real_story_open_lost_ack_recovers_unique_session(app_driver, story_engine, story_session):
    home, data_root, runtime = story_session

    lost = _facts(_run_story(app_driver, story_engine, 'story-open-lost-ack', home, data_root,
                             runtime, fault={'action': 'exit', 'stages': ['after_commit']}),
                  'story-open-lost-ack')
    assert lost['state'] == 'ready' and lost['turn'] == 0
    counts = _world_counts(data_root)
    assert counts == {'commits': 1, 'intakes': 0, 'sessions': 1, 'bootstraps': 1}

    found = _facts(_run_story(app_driver, story_engine, 'story-recover-open', home, data_root, runtime),
                   'story-recover-open')
    assert found['state'] == 'ready' and found['turn'] == 0
    assert found['session_id'] == lost['session_id'], 'Entry must find the single committed session'
    assert _world_counts(data_root) == counts


def test_real_story_unsupported_input_keeps_draft_and_writes_nothing(
        app_driver, story_engine, story_session):
    home, data_root, runtime = story_session
    _facts(_run_story(app_driver, story_engine, 'story-open', home, data_root, runtime), 'story-open')

    rejected = _facts(_run_story(app_driver, story_engine, 'story-submit-unsupported', home,
                                 data_root, runtime), 'story-submit-unsupported')
    assert rejected['state'] == 'failed'
    assert rejected['last_service_code'] == 'deterministic_input_unsupported'
    assert rejected['draft'] == UNSUPPORTED_TEXT
    assert rejected['turn'] == 0
    assert _world_counts(data_root) == {
        'commits': 1, 'intakes': 0, 'sessions': 1, 'bootstraps': 1}
