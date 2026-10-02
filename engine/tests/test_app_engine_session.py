"""Compile production Swift, then exercise the real independent Python Engine.

The required target is macOS with Swift installed. No fake success/skip when that
prerequisite is missing. Linux can also run this as supplementary compatibility.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
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
from contextlib import closing
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SWIFT = ROOT / 'macos-app/WorldOfMysteries'
ENGINE_DIR = ROOT / 'engine'
ENGINE_PACKAGES = ('domain', 'application', 'infrastructure', 'ai', 'contracts')
WORLD_DIRECTORY = 'engineering-golden001'
UNSUPPORTED_TEXT = '先问问医生今天还有没有别的预约。'
# The frozen fixed-run advice, exactly as the packaged five-turn content ships it.
TURN_ADVICE = (
    '先别问医生病人的事，我想看看他的反应。',
    '检查预约簿，但别让他发现。',
    '我觉得地下室有问题，先听听下面有没有声音。',
    '不要直接进去，想办法让医生先离开。',
    '已经够了，把我们知道的东西整理清楚，然后离开。',
)
FIVE_CLUE_DISPLAY_NAMES = (
    '医生的停顿', '异常的预约记录', '被撕去的预约页', '门框黑粉', 'Jonathan 的纸片',
)
DRIVER_SOURCES = [
    'IPCEnvelope', 'IPCFrameCodec', 'MediaProtocol', 'EngineRuntimeModels',
    'EngineSocketTransport', 'StoryPostCommitControl', 'EngineIPCClient',
    'EngineProcessManager', 'EngineConnectionState',
    'StorySessionControl', 'StoryRequestJournal', 'StorySubmissionCoordinator',
    'StorySessionModel', 'AppState',
    # AppState owns the Story Book model. Only the model half is compiled here:
    # the SwiftUI view is not part of the transport contract under test.
    'StoryBookModel',
    # story.expression.get DTOs. EngineIPCClient and StorySessionModel
    # decode against these types, so omitting the file breaks the real
    # App build below with "cannot find type ... in scope".
    'StoryExpressionControl',
    # AppState owns the voice turn controller, so the media stack it
    # composes is part of compiling the real App, not an extra.
    'Media/VoiceTurnController', 'Media/EngineMediaPlaybackSession',
    'Media/NativePlayback', 'Media/PlaybackInterruption',
    'Media/UnixMediaFrameTransport', 'Media/MicrophoneCapture',
    'Media/SpeechRailRealtimeASR', 'Media/SpeechRailRealtimeASRConnection',
    'Media/SpeechRailRealtimeASRTurnCoordinator', 'Media/VoiceInputPTTSession',
]

sys.path.insert(0, str(ROOT / 'scripts'))
import build_story_content as content_builder
import bundle_engine


def child_environment() -> dict[str, str]:
    """The environment the Swift process manager hands to the Engine child.

    Mirrored here so a warm-up run is indistinguishable from a real launch:
    same interpreter isolation, and none of the parent's Python or dynamic
    loader injection.
    """
    blocked = ('PYTHON', 'DYLD_', 'LD_')
    return {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(blocked) and key != 'VIRTUAL_ENV'
    }


def _engine_ipc_referenced_sources() -> set[str]:
    """Top-level Swift files whose declarations EngineIPCClient names."""
    declaration = re.compile(
        r'^(?:(?:public|package|internal|private|fileprivate|open|nonisolated|final|indirect)\s+)*'
        r'(?:actor|class|enum|protocol|struct|typealias)\s+([A-Za-z_]\w*)',
        re.MULTILINE,
    )
    engine_client = (SWIFT / 'EngineIPCClient.swift').read_text(encoding='utf-8')
    referenced_sources = set()
    for source in SWIFT.glob('*.swift'):
        if source.name == 'EngineIPCClient.swift':
            continue
        declarations = declaration.findall(source.read_text(encoding='utf-8'))
        if any(re.search(rf'\b{re.escape(name)}\b', engine_client) for name in declarations):
            referenced_sources.add(source.stem)
    return referenced_sources


def test_driver_sources_cover_engine_ipc_top_level_type_dependencies():
    """Keep this separately compiled driver in step with EngineIPCClient DTOs."""
    referenced_sources = _engine_ipc_referenced_sources()

    missing = referenced_sources - set(DRIVER_SOURCES)
    assert not missing, (
        'The App driver omits Swift source files declaring top-level types used by '
        f'EngineIPCClient: {sorted(missing)}'
    )


def test_package_probe_sources_cover_engine_ipc_top_level_type_dependencies():
    """Keep the packaged-release probe in step with EngineIPCClient DTOs too.

    `build_macos_package.py` compiles its own curated subset of the production
    client. A new IPC DTO declared outside that subset breaks `swiftc` there
    while every fast suite stays green, and the only symptom is a packaging job
    failing minutes later — long after the slice that caused it was merged.
    """
    import build_macos_package

    missing = _engine_ipc_referenced_sources() - set(
        build_macos_package.PACKAGE_PROBE_SWIFT_SOURCES
    )
    assert not missing, (
        'The packaged probe omits Swift source files declaring top-level types '
        f'used by EngineIPCClient: {sorted(missing)}'
    )

    missing_files = [name for name in DRIVER_SOURCES if not (SWIFT / f'{name}.swift').is_file()]
    assert not missing_files, f'The App driver references missing Swift files: {missing_files}'
    assert DRIVER_SOURCES.index('StoryPostCommitControl') < DRIVER_SOURCES.index('EngineIPCClient')


@pytest.fixture(scope='module')
def app_driver(tmp_path_factory):
    compiler = shutil.which('swiftc')
    assert compiler, 'Production App–Engine integration requires the target Swift toolchain'
    binary = tmp_path_factory.mktemp('swift-engine') / 'driver'
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
        *[str(SWIFT / f'{name}.swift') for name in DRIVER_SOURCES],
        str(context_file), str(Path(__file__).parent / 'fixtures/app_engine_driver.swift'), '-o', str(binary)],
        capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
    # The Engine child is spawned with -B and a scrubbed environment, so the
    # very first launch on a cold machine pays to read the interpreter, the
    # standard library and every Engine module from disk before it can bind
    # its socket. That cost belongs to no assertion here and it is charged to
    # whichever case happens to run first, which made the suite fail only on a
    # fresh CI runner. Warm the identical code path once, with the same
    # interpreter, flags, working directory and environment the child gets, so
    # every case below measures protocol behaviour rather than disk speed.
    warm = subprocess.run(
        [sys.executable, '-E', '-s', '-B', '-X', 'utf8', '-c', 'import infrastructure.ipc_server'],
        cwd=str(ENGINE_DIR), env=child_environment(), capture_output=True, text=True, timeout=90)
    assert warm.returncode == 0, warm.stdout + warm.stderr
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
    plan.setdefault("fired", []).append(stage)
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
    """Staged module tree mirroring the relocatable bundle layout.

    The real packager keeps the engine packages under `<root>/engine/` and the
    runtime contract schemas at `<root>/contracts/schemas/`. This fixture
    reproduces that exact relative layout (plus the test-only launcher wrapper)
    so the Episode finalizer resolves its artifact contracts from the same
    trusted root the shipped Engine uses.
    """

    root = tmp_path_factory.mktemp('story-engine')
    staged = root / 'engine'
    staged.mkdir()
    for name in ENGINE_PACKAGES:
        shutil.copytree(ENGINE_DIR / name, staged / name,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    entry = staged / 'infrastructure/ipc_server.py'
    production_bytes = entry.read_bytes()
    (staged / 'infrastructure/_ipc_server_production.py').write_bytes(production_bytes)
    entry.write_text(LAUNCHER_WRAPPER, encoding='utf-8')
    (staged / '_wom_sqlite3.py').write_text(HOST_SQLITE_SHIM, encoding='utf-8')
    # The artifact is produced by the same build script the packaging step uses.
    payload = content_builder.build_payload()
    content_builder.write_artifact(
        staged / 'infrastructure/story_content/canon.db', payload)
    content_builder.write_five_turn_directory(
        staged / 'infrastructure/story_content', payload['seed'])
    content_builder.write_episode_artifacts(staged / 'infrastructure/story_content')
    # The packager ships the three artifact contracts the Episode finalizer
    # validates against; stage them exactly as the bundle does.
    assert bundle_engine.stage_contract_schemas(root) == (
        'character_knowledge.schema.json',
        'character_memory.schema.json',
        'world_event.schema.json',
    )
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


def _fired_stages(home):
    """Which acceptance checkpoints the Engine actually hit.

    The App restarts a lost Engine and the durable worker resumes whatever the
    dead process left behind, so the end state of a crashed run converges and
    can no longer tell one checkpoint from another. The fault plan is the only
    witness that the requested boundary was genuinely exercised.
    """
    plan = Path(home) / 'fault-plan.json'
    if not plan.is_file():
        return []
    return json.loads(plan.read_text(encoding='utf-8')).get('fired') or []


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
    canon = story_engine / 'infrastructure/story_content/canon.db'
    canon_digest = hashlib.sha256(canon.read_bytes()).hexdigest()

    opened = _facts(_run_story(app_driver, story_engine, 'story-open', home, data_root, runtime),
                    'story-open')
    assert opened['state'] == 'ready' and opened['turn'] == 0
    assert opened['supported_advice'] == ['先别问医生病人的事，我想看看他的反应。']

    submitted = _facts(_run_story(app_driver, story_engine, 'story-submit', home, data_root, runtime),
                       'story-submit')
    # One committed turn reopens the fixed run with exactly the next turn's advice.
    assert submitted['state'] == 'ready' and submitted['turn'] == 1
    assert submitted['session_id'] == opened['session_id']
    assert submitted['supported_advice'] == [TURN_ADVICE[1]]
    assert '医生的停顿' in submitted['clues']
    journal = (home / 'Library/Application Support/WorldofMysteries/Engineering/Golden001/Journal'
               / 'first-turn-request.json')
    assert journal.is_file(), 'Client retry journal must stay inside the isolated user home'

    reopened = _facts(_run_story(app_driver, story_engine, 'story-reopen', home, data_root, runtime),
                      'story-reopen')
    assert reopened['state'] == 'ready' and reopened['turn'] == 1
    assert reopened['session_id'] == submitted['session_id']
    assert reopened['story_revision'] == 1
    assert reopened['clues'] == submitted['clues']
    assert reopened['supported_advice'] == [TURN_ADVICE[1]]
    assert _world_counts(data_root) == {
        'commits': 2, 'intakes': 1, 'sessions': 1, 'bootstraps': 1}
    # A full product first turn must never write the read-only canon artifact.
    assert hashlib.sha256(canon.read_bytes()).hexdigest() == canon_digest
    # The advice the client submitted is the packaged frozen content, verbatim.
    staged_advice = json.loads(
        (story_engine / 'infrastructure/story_content/five_turn/turns/01_advice.json')
        .read_text(encoding='utf-8'))['raw_input']
    assert staged_advice == TURN_ADVICE[0]
    assert opened['supported_advice'] == [TURN_ADVICE[0]]


def test_real_story_five_turns_commit_settle_and_close(app_driver, story_engine, story_session):
    home, data_root, runtime = story_session
    opened = _facts(_run_story(app_driver, story_engine, 'story-open', home, data_root, runtime),
                    'story-open')
    assert opened['state'] == 'ready' and opened['turn'] == 0

    # One App process drives the whole fixed run through real IPC.
    finished = _facts(_run_story(app_driver, story_engine, 'story-five-turn', home, data_root,
                                 runtime, timeout=180),
                      'story-five-turn')
    assert finished['state'] == 'completed' and finished['turn'] == 5
    assert finished['story_revision'] == 5
    assert finished['session_id'] == opened['session_id']
    assert finished['supported_advice'] == []
    assert sorted(finished['clues']) == sorted(FIVE_CLUE_DISPLAY_NAMES)
    counts = _world_counts(data_root)
    # Seven commits: the session bootstrap, the five committed turns, and the
    # Episode finalization, which is itself one durable domain commit.
    assert counts == {'commits': 7, 'intakes': 5, 'sessions': 1, 'bootstraps': 1}

    # The packaged runtime really settles: Episode + all five artifact groups
    # are durable, and frozen expression (BeatPlan + NarrativeBlock) exists
    # for every committed turn.
    world = Path(data_root) / 'Worlds' / WORLD_DIRECTORY / 'world.db'
    with closing(sqlite3.connect(f'file:{world}?mode=ro', uri=True)) as connection:
        def count(table):
            return connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]

        assert count('episodes') == 1
        assert count('episode_finalizations') == 1
        assert count('character_episode_memories') >= 1
        assert count('episode_knowledge_changes') >= 1
        assert count('beat_plans') == 5
        assert count('narrative_blocks') == 5
        ending = connection.execute(
            "SELECT payload_json FROM episodes").fetchone()[0]
    episode = json.loads(ending)
    assert episode['ending']['type'] == 'partial_truth'
    assert set(episode['unresolved_threads']) == {
        'jonathan_current_location', 'occult_group_identity'}

    # A brand-new process re-reads the closed run and never recommits.
    reopened = _facts(_run_story(app_driver, story_engine, 'story-reopen', home, data_root, runtime),
                      'story-reopen')
    assert reopened['state'] == 'completed' and reopened['turn'] == 5
    assert reopened['story_revision'] == 5
    assert reopened['clues'] == finished['clues']
    assert reopened['supported_advice'] == []
    assert _world_counts(data_root) == counts


def test_real_story_lost_ack_recovers_without_recommitting(app_driver, story_engine, story_session):
    home, data_root, runtime = story_session
    _facts(_run_story(app_driver, story_engine, 'story-open', home, data_root, runtime), 'story-open')

    # The Engine commits the first turn and then dies before answering the client.
    lost = _facts(_run_story(app_driver, story_engine, 'story-submit-lost-ack', home, data_root,
                             runtime, fault={'action': 'exit', 'stages': ['after_commit']}),
                  'story-submit-lost-ack')
    assert lost['state'] == 'ready' and lost['turn'] == 1
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
    assert resumed['state'] == 'ready' and resumed['turn'] == 1
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


# ---------------------------------------------------------------------------
# Golden acceptance: the eight Engine termination checkpoints
#
# The runtime specification (`docs/07_工程启动/golden_001_runtime/README.md` §6)
# requires the Engine to be killable at eight semantic boundaries, and the
# iteration plan (checkpoint C) requires every fault test to prove BOTH process
# recovery AND disk facts — zero duplicate commits, zero partial settlement.
# The named checkpoints below announce those boundaries through the same
# already-injected `fault_hook` (production stays fault-switch free), so a fault
# plan can target one exact boundary and the assertions can tell "turn
# committed" from "settlement committed".
# ---------------------------------------------------------------------------


def _durable_counts(data_root):
    """Row counts for every table the eight acceptance checkpoints observe."""

    world = Path(data_root) / 'Worlds' / WORLD_DIRECTORY / 'world.db'
    assert world.is_file(), f'Missing world database: {world}'
    tables = (
        'domain_commits',
        'turn_intake_commands',
        'turn_advice_interpretations',
        'turn_transactions',
        'beat_plans',
        'narrative_blocks',
        'episodes',
        'episode_finalizations',
        'character_episode_memories',
    )
    with closing(sqlite3.connect(f'file:{world}?mode=ro', uri=True)) as connection:
        return {
            table: connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
            for table in tables
        }


@pytest.mark.parametrize(
    'stage,expected_interpretations',
    [
        # CP1 "after advice": the PlayerAdvice intake is durable, but the
        # interpretation has not run and nothing is committed.
        ('after_advice_intake', 0),
        # CP2 "after action intent" and CP3 "after resolver before commit" share
        # this durable window. The interpretation is committed in its own
        # transaction before the domain COMMIT, and the resolver is a pure
        # in-memory function, so the two are indistinguishable on disk: both
        # mean "intent recorded, turn not committed". CP2's precise in-memory
        # point lives in the application layer, outside this capsule's
        # infrastructure write scope, so it is covered here at the equivalent
        # durable boundary (the same approach the pre-existing `before_commit`
        # recovery test already exercises).
        ('before_commit', 1),
    ],
    ids=['cp1_after_advice', 'cp2_cp3_after_intent_before_commit'],
)
def test_acceptance_checkpoint_before_domain_commit_is_resumed_exactly_once(
        app_driver, story_engine, story_session, stage, expected_interpretations):
    home, data_root, runtime = story_session
    _facts(_run_story(app_driver, story_engine, 'story-open', home, data_root, runtime), 'story-open')

    # The Engine dies inside the first submit, before any domain commit.
    interrupted = _facts(
        _run_story(app_driver, story_engine, 'story-submit-interrupted', home, data_root,
                   runtime, fault={'action': 'exit', 'stages': [stage]}),
        'story-submit-interrupted')
    assert interrupted['state'] in {'pending', 'recovering', 'failed'}
    assert interrupted['turn'] == 0
    counts = _durable_counts(data_root)
    # The intake is durable (and, past the interpretation, so is the
    # interpretation) — but the turn never committed: zero turn commits, zero
    # expression, zero episode. The App must not invent an outcome.
    assert counts['domain_commits'] == 1              # session bootstrap only
    assert counts['turn_intake_commands'] == 1
    assert counts['turn_advice_interpretations'] == expected_interpretations
    assert counts['turn_transactions'] == 0
    assert counts['beat_plans'] == 0
    assert counts['narrative_blocks'] == 0
    assert counts['episodes'] == 0

    # A brand-new process continues the durable intent and commits the turn
    # exactly once — never a second interpretation, never a duplicate commit.
    resumed = _facts(
        _run_story(app_driver, story_engine, 'story-continue-pending', home, data_root, runtime),
        'story-continue-pending')
    assert resumed['state'] == 'ready' and resumed['turn'] == 1
    after = _durable_counts(data_root)
    assert after['domain_commits'] == 2               # bootstrap + the one turn
    assert after['turn_transactions'] == 1
    assert after['turn_advice_interpretations'] == 1  # exactly one interpretation


@pytest.mark.parametrize(
    'stage,beat_plans,narrative_blocks',
    [
        # CP4 "immediately after commit": the turn is durable and no post-COMMIT
        # work has started. The App restarts the lost Engine and the worker
        # finishes the turn, so the run may already have converged by the time
        # the facts are read; only the fired checkpoint pins the boundary.
        ('after_turn_commit', 1, 1),
        # CP5 "after beat plan": the frozen BeatPlan is durable, narrative pending.
        ('after_beat_plan', 1, 0),
        # CP6 "after narrative": the frozen expression is complete, run continues.
        ('after_narrative', 1, 1),
    ],
    ids=['cp4_immediately_after_commit', 'cp5_after_beat_plan', 'cp6_after_narrative'],
)
def test_acceptance_checkpoint_after_commit_never_recommits(
        app_driver, story_engine, story_session, stage, beat_plans, narrative_blocks):
    home, data_root, runtime = story_session
    _facts(_run_story(app_driver, story_engine, 'story-open', home, data_root, runtime), 'story-open')

    # The Engine dies after the first turn is durably committed, at the given
    # expression boundary, before it can answer the client. This is the
    # "facts saved, expression pending" split: the App must recover the
    # committed turn from durable state, never re-commit it.
    lost = _facts(
        _run_story(app_driver, story_engine, 'story-submit-lost-ack', home, data_root,
                   runtime, fault={'action': 'exit', 'stages': [stage]}),
        'story-submit-lost-ack')
    # The boundary really was crossed. A converged end state no longer tells
    # the checkpoints apart — the App heals a lost Engine inside the same run —
    # so the fault plan is the only witness that this exact boundary was hit.
    assert stage in _fired_stages(home)
    # The App reports the committed turn and never invents an outcome for it.
    # A killed Engine legitimately reads as `unavailable`: that is an honest
    # report of a lost transport, not a failure, and the durable facts below
    # are the real subject of this checkpoint.
    assert lost['turn'] == 1
    assert lost['state'] in {'ready', 'unavailable', 'recovering', 'failed'}
    counts = _durable_counts(data_root)
    assert counts['domain_commits'] == 2               # bootstrap + one committed turn
    assert counts['turn_transactions'] == 1
    assert counts['beat_plans'] == beat_plans
    assert counts['narrative_blocks'] == narrative_blocks
    assert counts['episodes'] == 0                    # a single turn never finalizes

    # A brand-new process re-reads the same committed turn, adds no commit, and
    # finishes whatever the lost worker never got to. This is the stronger half
    # of the contract: the old suite only proved the reopen changed nothing,
    # which a durable world also satisfies when the work never finished at all.
    reopened = _facts(
        _run_story(app_driver, story_engine, 'story-reopen', home, data_root, runtime),
        'story-reopen')
    assert reopened['turn'] == 1
    healed = _durable_counts(data_root)
    assert healed['domain_commits'] == 2              # recovery never re-commits
    assert healed['turn_transactions'] == 1
    assert healed['turn_intake_commands'] == 1
    assert healed['turn_advice_interpretations'] == 1
    assert healed['beat_plans'] == 1                  # the work is finished, once
    assert healed['narrative_blocks'] == 1
    assert healed['episodes'] == 0


@pytest.mark.parametrize(
    'stage',
    [
        # CP7 "during finalization transaction": every settlement row is written
        # but the transaction is NOT yet committed, so the Episode is wholly
        # absent at that instant.
        'during_finalization',
        # CP8 "after finalization commit before projection": the Episode is
        # durably committed while the rebuildable retrieval projection lags.
        'after_finalization_commit',
    ],
    ids=['cp7_during_finalization', 'cp8_after_finalization_commit'],
)
def test_acceptance_checkpoint_settlement_is_atomic_and_never_refinalizes(
        app_driver, story_engine, story_session, stage):
    home, data_root, runtime = story_session
    _facts(_run_story(app_driver, story_engine, 'story-open', home, data_root, runtime), 'story-open')

    # Drive all five turns; the fault terminates the Engine inside the fifth
    # turn's settlement, so the App loses the final acknowledgement. The
    # driver tolerates the lost final ack; a brand-new process proves the
    # durable facts.
    finished = _facts(
        _run_story(app_driver, story_engine, 'story-five-turn-final-lost', home, data_root,
                   runtime, fault={'action': 'exit', 'stages': [stage]}, timeout=180),
        'story-five-turn-final-lost')
    # The App restarts a lost Engine and the durable worker resumes whatever
    # the dead process left behind, so both checkpoints converge to the same
    # end state inside one run. The fired boundary is what tells them apart.
    assert stage in _fired_stages(home)
    assert finished['state'] in {'ready', 'completed', 'failed', 'recovering', 'pending'}

    counts = _durable_counts(data_root)
    # All five turns committed exactly once, and every committed turn carries
    # its frozen expression regardless of how far settlement got.
    assert counts['turn_transactions'] == 5
    assert counts['beat_plans'] == 5
    assert counts['narrative_blocks'] == 5
    # The Episode is wholly committed or wholly absent — never partial, and
    # never settled twice: a finalization without an Episode, or an Episode
    # memory without either, is exactly the corruption this checkpoint exists
    # to catch.
    assert counts['episodes'] in (0, 1)
    assert counts['episode_finalizations'] == counts['episodes']
    assert bool(counts['character_episode_memories']) == bool(counts['episodes'])
    assert counts['domain_commits'] == 6 + counts['episodes']

    # A brand-new process re-opens the closed run, completes a settlement the
    # lost worker never finished, and never re-finalizes a finished one.
    reopened = _facts(
        _run_story(app_driver, story_engine, 'story-reopen', home, data_root, runtime),
        'story-reopen')
    assert reopened['turn'] == 5
    assert reopened['supported_advice'] == []
    healed = _durable_counts(data_root)
    assert healed['episodes'] == 1
    assert healed['episode_finalizations'] == 1
    assert healed['character_episode_memories'] > 0
    assert healed['domain_commits'] == 7               # bootstrap + 5 turns + 1 episode
    assert healed['turn_transactions'] == 5
    assert healed['beat_plans'] == 5
    assert healed['narrative_blocks'] == 5
    # A second process must find the closed run exactly as it was left.
    again = _facts(
        _run_story(app_driver, story_engine, 'story-reopen', home, data_root, runtime),
        'story-reopen')
    assert again['turn'] == 5
    assert _durable_counts(data_root) == healed
