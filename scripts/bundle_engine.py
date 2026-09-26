#!/usr/bin/env python3
"""Build-time only: stage a pinned, relocatable Python runtime without host venvs.

The application never calls uv/pip, downloads Python or resolves dependencies.
An existing output is never replaced. SHA-256 is integrity evidence, not a code
signature; distribution signing is owned by build_macos_package.py.
"""
from __future__ import annotations

import hashlib
import http.client
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

from build_data_sqlite import stage_data_sqlite

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / 'macos-app/Packaging/python-runtime.lock.json'
ENGINE_DIRS = ('domain', 'application', 'infrastructure', 'ai', 'contracts')
MAX_EXPANDED_BYTES = 2 * 1024**3


class BundleError(RuntimeError):
    """A bounded build/validation failure, without credentials or raw payloads."""


def sha256(path: Path) -> str:
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def read_lock(path: Path = LOCK) -> dict:
    record = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(record, dict):
        raise BundleError('Runtime lock must be an object')
    required = {'format_version': 1, 'python_version': '3.14.7', 'implementation': 'cpython',
                'gil_enabled': True, 'architecture': 'arm64', 'platform': 'darwin',
                'provider': 'astral-sh/python-build-standalone', 'agentscope_version': '2.0.8'}
    if any(type(record.get(k)) is not type(v) or record[k] != v for k, v in required.items()):
        raise BundleError('Unsupported runtime lock')
    if not re.fullmatch(r'[0-9a-f]{64}', str(record.get('sha256', ''))):
        raise BundleError('Runtime lock needs a SHA-256')
    if type(record.get('size')) is not int or not 0 < record['size'] < MAX_EXPANDED_BYTES:
        raise BundleError('Invalid runtime archive size')
    release = record.get('release', '')
    if not isinstance(release, str) or not re.fullmatch(r'\d{8}', release):
        raise BundleError('Invalid runtime release')
    filename = f"cpython-3.14.7+{release}-aarch64-apple-darwin-install_only_stripped.tar.gz"
    url = urllib.parse.urlsplit(record.get('url', ''))
    expected = f'/astral-sh/python-build-standalone/releases/download/{release}/{filename}'
    if (record.get('filename') != filename or url.scheme != 'https' or url.netloc != 'github.com'
            or urllib.parse.unquote(url.path) != expected or url.query or url.fragment):
        raise BundleError('Runtime URL must identify the pinned upstream asset')
    return record


def validate_archive(path: Path, lock: dict) -> None:
    if path.is_symlink() or not path.is_file() or path.stat().st_size != lock['size']:
        raise BundleError('Runtime archive size/type mismatch')
    if sha256(path) != lock['sha256']:
        raise BundleError('Runtime archive digest mismatch')


DOWNLOAD_ATTEMPTS = 3
RETRYABLE_HTTP_STATUS = frozenset({408, 429, 500, 502, 503, 504})


def download_runtime(lock: dict, target: Path) -> None:
    """Retry only transient transport failures; never publish unverified bytes.

    Each attempt owns a new temporary file. Atomic no-clobber publication protects
    existing outputs (including symlinks) and concurrent builders. Integrity,
    TLS and permission failures never trigger a weaker source or validation path.
    """
    if target.exists() or target.is_symlink():
        raise BundleError('Refusing to replace an existing runtime archive')
    req = urllib.request.Request(lock['url'], headers={'User-Agent': 'WorldofMysteries-bundler'})
    for attempt in range(DOWNLOAD_ATTEMPTS):
        fd, name = tempfile.mkstemp(prefix='.runtime-download-', dir=target.parent)
        partial = Path(name)
        failure = ''
        try:
            with os.fdopen(fd, 'wb') as output:
                try:
                    with urllib.request.urlopen(req, timeout=60) as response:
                        if urllib.parse.urlsplit(response.geturl()).scheme != 'https':
                            raise BundleError('Insecure runtime download redirect')
                        total = 0
                        while block := response.read(1024 * 1024):
                            total += len(block)
                            if total > lock['size']:
                                raise BundleError('Runtime download exceeds pinned size')
                            output.write(block)
                        if total != lock['size']:
                            raise http.client.IncompleteRead(b'', lock['size'] - total)
                except urllib.error.HTTPError as exc:
                    code = exc.code
                    exc.close()
                    if code not in RETRYABLE_HTTP_STATUS:
                        raise BundleError(f'Runtime download rejected (HTTP {code})') from None
                    failure = f'HTTP {code}'
                except urllib.error.URLError as exc:
                    if not isinstance(exc.reason, (TimeoutError, ConnectionError)):
                        raise BundleError('Runtime download connection or TLS validation failed') from None
                    failure = 'connection interrupted'
                except (TimeoutError, ConnectionError, http.client.IncompleteRead):
                    failure = 'connection interrupted'
            if not failure:
                validate_archive(partial, lock)
                # Hard-link creation is atomic and fails if any target already exists.
                os.link(partial, target)
                return
        finally:
            partial.unlink(missing_ok=True)
        if attempt + 1 == DOWNLOAD_ATTEMPTS:
            raise BundleError(f'Runtime download exhausted {DOWNLOAD_ATTEMPTS} attempts ({failure})')
        print(f'Runtime download attempt {attempt + 1}/{DOWNLOAD_ATTEMPTS} failed ({failure}); retrying pinned asset',
              file=sys.stderr)
        time.sleep(2 ** attempt)


def validate_links(root: Path) -> None:
    """Reject escaped, absolute, cyclic or dangling links, including interpreter links."""
    resolved = root.resolve(strict=True)
    for path in root.rglob('*'):
        if path.is_symlink():
            try:
                target = path.resolve(strict=True)
            except (OSError, RuntimeError) as exc:
                raise BundleError('Broken runtime link') from exc
            if Path(os.readlink(path)).is_absolute() or not target.is_relative_to(resolved):
                raise BundleError('Runtime link escapes the bundle')
        elif not (path.is_file() or path.is_dir()):
            raise BundleError('Unsupported runtime filesystem entry')


def extract_runtime(archive: Path, output: Path, lock: dict) -> Path:
    validate_archive(archive, lock)
    output.mkdir(parents=True, exist_ok=False)
    with tarfile.open(archive, 'r:gz') as tar:
        members = tar.getmembers()
        if sum(m.size for m in members) > MAX_EXPANDED_BYTES or len(members) > 100_000:
            raise BundleError('Runtime archive expansion limit exceeded')
        names = set()
        for member in members:
            name = PurePosixPath(member.name)
            if (name.is_absolute() or '..' in name.parts or not name.parts or name.parts[0] != 'python'
                    or str(name) in names or not (member.isfile() or member.isdir() or member.issym() or member.islnk())):
                raise BundleError('Unsafe runtime archive member')
            if member.issym() and PurePosixPath(member.linkname).is_absolute():
                raise BundleError('Absolute runtime archive symlink')
            names.add(str(name))
        # The data filter also prevents links escaping through earlier members.
        tar.extractall(output, members=members, filter='data')
    runtime = output / 'python'
    validate_links(runtime)
    return runtime


def run(command: list[str], *, cwd: Path, log: Path, env: dict | None = None,
        timeout: float = 300) -> str:
    log.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(command, cwd=cwd, env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        log.write_bytes(exc.stdout or b'')
        raise BundleError(f'Build step timed out: {log.name}') from exc
    log.write_bytes(result.stdout)
    if result.returncode:
        raise BundleError(f'Build step failed: {log.name} (exit {result.returncode})')
    return result.stdout.decode('utf-8', errors='replace')


def source_inventory(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): sha256(p)
            for p in sorted(root.rglob('*')) if p.is_file() and not p.is_symlink()}


def stage_engine(output: Path, logs: Path, *, archive: Path | None = None) -> dict:
    if sys.platform != 'darwin' or platform.machine() != 'arm64':
        raise BundleError('Production runtime staging requires macOS arm64')
    lock = read_lock()
    if output.exists() or output.is_symlink():
        raise BundleError('Refusing to replace an existing runtime')
    output.parent.mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in os.environ.items() if not k.startswith(('PYTHON', 'DYLD_', 'LD_'))
           and k not in {'VIRTUAL_ENV', 'UV_PROJECT_ENVIRONMENT'}}
    env.update(UV_PYTHON_DOWNLOADS='never', UV_NO_CONFIG='true', UV_LINK_MODE='copy')
    with tempfile.TemporaryDirectory(prefix='.wom-runtime-', dir=output.parent) as work:
        work = Path(work)
        source_archive = archive or work / lock['filename']
        if archive is None:
            download_runtime(lock, source_archive)
        runtime = extract_runtime(source_archive, work / 'extract', lock)
        python = runtime / 'bin/python3'
        if not python.is_file() or not os.access(python, os.X_OK):
            raise BundleError('Runtime interpreter is missing')
        probe = "import sys,sysconfig,platform,json; print(json.dumps({'version':platform.python_version(),'arch':platform.machine(),'gil_disabled':bool(sysconfig.get_config_var('Py_GIL_DISABLED')),'prefix':sys.prefix}))"
        actual = json.loads(run([str(python), '-I', '-B', '-c', probe], cwd=work,
                                log=logs/'runtime-version.log', env=env))
        if (actual['version'] != lock['python_version'] or actual['arch'] != 'arm64'
                or actual['gil_disabled'] or Path(actual['prefix']).resolve() != runtime.resolve()):
            raise BundleError('Downloaded interpreter differs from the locked runtime')
        uv = shutil.which('uv')
        if not uv:
            raise BundleError('Build machine needs uv; the final application does not')
        requirements = work / 'requirements.txt'
        run([uv, 'export', '--locked', '--no-dev', '--no-emit-project', '--no-editable',
             '--format', 'requirements-txt', '--output-file', str(requirements)],
            cwd=ROOT/'engine', log=logs/'dependency-export.log', env=env)
        # A complete hashed lock export: no implicit resolution, build scripts or editable host paths.
        run([uv, 'pip', 'install', '--python', str(python), '--system', '--require-hashes',
             '--no-deps', '--no-build', '-r', str(requirements)],
            cwd=work, log=logs/'dependency-install.log', env=env, timeout=600)
        data_sqlite = stage_data_sqlite(runtime, logs, env=env)
        modules = runtime / 'engine'
        modules.mkdir()
        tracked = subprocess.check_output(['git', 'ls-files', '-z', '--',
                    *['engine/'+d for d in ENGINE_DIRS]], cwd=ROOT).decode().split('\0')
        for name in filter(None, tracked):
            source = ROOT/name
            if source.is_symlink() or not source.is_file() or source.suffix in {'.db', '.sqlite', '.pyc'}:
                raise BundleError('Unexpected engine source type')
            target = modules / Path(name).relative_to('engine')
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        # The trusted Golden content is generated, never tracked: the artifact is
        # produced by the same build script the repository tests exercise.
        story_content = run([str(python), '-I', '-B', str(ROOT/'scripts/build_story_content.py'),
                             '--out', str(modules/'infrastructure/story_content/canon.db')],
                            cwd=work, log=logs/'story-content-build.log', env=env)
        story_content_summary = json.loads(story_content.strip().splitlines()[-1])
        if story_content_summary['scenario_id'] != 'golden_001':
            raise BundleError('Unexpected story content scenario')
        # Exercise the installed AgentScope 2.x message API without creating services or calling a model.
        code = """import agentscope,aiosqlite,pydantic,pydantic_core,openai,jsonschema,sqlite3,ssl,ctypes,sys,json,_wom_sqlite3
from importlib.metadata import distributions,version
from agentscope.message import UserMsg
assert UserMsg(name='packaging-probe',content='offline').get_text_content() == 'offline'
assert version('agentscope') == '2.0.8'
assert _wom_sqlite3.sqlite_version == '3.53.4'
class Result(pydantic.BaseModel):
    ok: bool
assert Result.model_validate_json('{"ok":true}').ok
print(json.dumps({'agentscope':version('agentscope'),'python':sys.version.split()[0],
'packages':sorted([{'name':d.metadata['Name'],'version':d.version} for d in distributions()],key=lambda d:d['name'].lower())}))
"""
        raw = run([str(python), '-I', '-B', '-c', code], cwd=work,
                  log=logs/'dependency-probe.log', env=env)
        dependencies = json.loads(raw.strip().splitlines()[-1])
        # The packaged engine must resolve its content artifact from the module
        # directory, never from a repository cwd or environment variable.
        relocated = work / 'story-content-probe'
        relocated.mkdir()
        probe_code = ("import json,sys;sys.path.insert(0,sys.argv[1]);"
                      "from infrastructure.story_runtime import default_content_path;"
                      "p=default_content_path();"
                      "print(json.dumps({'content_artifact_exists':p.is_file()}))")
        relocation = json.loads(run([str(python), '-I', '-B', '-c', probe_code, str(modules)],
                                    cwd=relocated, log=logs/'story-content-relocation.log', env=env).strip().splitlines()[-1])
        if not relocation['content_artifact_exists']:
            raise BundleError('Packaged story content is not module-relative')
        # Installation-created bytecode is not required. Runtime always launches with -B.
        for cache in list(runtime.rglob('__pycache__')):
            if cache.is_dir() and not cache.is_symlink():
                shutil.rmtree(cache)
        validate_links(runtime)
        shutil.copyfile(ROOT/'engine/uv.lock', runtime/'dependencies.uv.lock')
        shutil.copyfile(requirements, runtime/'dependencies.requirements.txt')
        manifest = {'format_version': 1, 'python_version': lock['python_version'],
            'architecture': 'arm64', 'gil_enabled': True, 'protocol_version': '1.0',
            'agentscope_version': lock['agentscope_version'],
            'source_commit': subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            'runtime_archive_sha256': lock['sha256'], 'dependency_lock_sha256': sha256(ROOT/'engine/uv.lock'),
            'runtime_source': lock, 'data_sqlite': data_sqlite, 'dependencies': dependencies['packages'],
            'story_content': story_content_summary,
            'inventory_phase': 'before-code-signing', 'files': source_inventory(runtime)}
        (runtime/'runtime-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
        # All upstream runtime and wheel license data are preserved without pruning.
        os.replace(runtime, output)
    return manifest
