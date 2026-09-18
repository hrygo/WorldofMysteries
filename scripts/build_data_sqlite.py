#!/usr/bin/env python3
"""Build the private data SQLite extension used by the bundled Local Engine.

The base CPython runtime intentionally remains the pinned python-build-standalone
3.14.7 artifact. Its built-in ``_sqlite3`` is SQLite 3.53.1, so the authoritative
data layer uses a separately named CPython 3.14.7 extension, statically linked to
pinned upstream SQLite 3.53.4. Nothing is downloaded or compiled on an end-user
machine; this module is build-time only.
"""
from __future__ import annotations

import hashlib
import http.client
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / 'macos-app/Packaging/data-sqlite.lock.json'
MAX_SOURCE_BYTES = 64 * 1024 * 1024
MAX_EXPANDED_BYTES = 256 * 1024 * 1024
DOWNLOAD_ATTEMPTS = 3
RETRYABLE_HTTP_STATUS = frozenset({408, 429, 500, 502, 503, 504})
SQLITE_SOURCES = (
    'blob.c', 'connection.c', 'cursor.c', 'microprotocols.c', 'module.c',
    'prepare_protocol.c', 'row.c', 'statement.c', 'util.c',
)
COMPILE_DEFINITIONS = (
    'SQLITE_THREADSAFE=1',
    'SQLITE_ENABLE_DBSTAT_VTAB=1',
    'SQLITE_ENABLE_FTS3=1',
    'SQLITE_ENABLE_FTS3_PARENTHESIS=1',
    'SQLITE_ENABLE_FTS4=1',
    'SQLITE_ENABLE_FTS5=1',
    'SQLITE_ENABLE_GEOPOLY=1',
    'SQLITE_ENABLE_MATH_FUNCTIONS=1',
    'SQLITE_ENABLE_PERCENTILE=1',
    'SQLITE_ENABLE_RTREE=1',
)


class DataSQLiteBuildError(RuntimeError):
    """A bounded build/source-integrity failure without raw payloads or credentials."""


def _hex(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value) is not None


def sha256(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def sha3_256(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha3_256').hexdigest()


def read_lock(path: Path = LOCK) -> dict:
    try:
        record = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise DataSQLiteBuildError('Data SQLite lock is unreadable') from exc
    if not isinstance(record, dict):
        raise DataSQLiteBuildError('Data SQLite lock must be an object')
    required = {'format_version': 1, 'module_name': '_wom_sqlite3',
                'python_version': '3.14.7', 'sqlite_version': '3.53.4'}
    if any(type(record.get(k)) is not type(v) or record[k] != v for k, v in required.items()):
        raise DataSQLiteBuildError('Unsupported Data SQLite lock')
    py = record.get('python_source')
    sq = record.get('sqlite_source')
    if not isinstance(py, dict) or not isinstance(sq, dict):
        raise DataSQLiteBuildError('Data SQLite source pins are missing')
    py_url = urllib.parse.urlsplit(str(py.get('url', '')))
    if (py.get('filename') != 'Python-3.14.7.tar.xz' or py_url.scheme != 'https'
            or py_url.netloc != 'www.python.org'
            or py_url.path != '/ftp/python/3.14.7/Python-3.14.7.tar.xz'
            or py_url.query or py_url.fragment or not _hex(py.get('sha256'))
            or type(py.get('size')) is not int or py['size'] != 24053924):
        raise DataSQLiteBuildError('Python source pin is invalid')
    sq_url = urllib.parse.urlsplit(str(sq.get('url', '')))
    if (sq.get('filename') != 'sqlite-amalgamation-3530400.zip' or sq_url.scheme != 'https'
            or sq_url.netloc not in {'www.sqlite.org', 'sqlite.org'}
            or sq_url.path != '/2026/sqlite-amalgamation-3530400.zip'
            or sq_url.query or sq_url.fragment or not _hex(sq.get('sha256'))
            or not _hex(sq.get('sha3_256')) or not _hex(sq.get('sqlite3_c_sha3_256'))):
        raise DataSQLiteBuildError('SQLite source pin is invalid')
    options = record.get('required_compile_options')
    expected = {('THREADSAFE=1' if item == 'SQLITE_THREADSAFE=1' else item.removeprefix('SQLITE_').removesuffix('=1')) for item in COMPILE_DEFINITIONS}
    if not isinstance(options, list) or not all(isinstance(item, str) for item in options):
        raise DataSQLiteBuildError('SQLite compile option contract is invalid')
    if not expected.issubset(set(options)):
        raise DataSQLiteBuildError('SQLite compile option contract is incomplete')
    return record


def _verify_download(path: Path, source: dict, *, sqlite: bool = False) -> None:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_SOURCE_BYTES:
        raise DataSQLiteBuildError('Pinned source archive has invalid type or size')
    if type(source.get('size')) is int and path.stat().st_size != source['size']:
        raise DataSQLiteBuildError('Pinned source archive size mismatch')
    if sha256(path) != source['sha256']:
        raise DataSQLiteBuildError('Pinned source archive SHA-256 mismatch')
    if sqlite and sha3_256(path) != source['sha3_256']:
        raise DataSQLiteBuildError('Pinned SQLite archive SHA3-256 mismatch')


def download_source(source: dict, target: Path, *, sqlite: bool = False) -> None:
    """Download one immutable source pin with bounded retries and no-clobber publish."""
    if target.exists() or target.is_symlink():
        raise DataSQLiteBuildError('Refusing to replace an existing source archive')
    request = urllib.request.Request(source['url'], headers={'User-Agent': 'WorldofMysteries-builder'})
    for attempt in range(DOWNLOAD_ATTEMPTS):
        fd, name = tempfile.mkstemp(prefix='.source-download-', dir=target.parent)
        partial = Path(name)
        failure = ''
        try:
            with os.fdopen(fd, 'wb') as output:
                try:
                    with urllib.request.urlopen(request, timeout=60) as response:
                        final = urllib.parse.urlsplit(response.geturl())
                        if final.scheme != 'https':
                            raise DataSQLiteBuildError('Insecure source download redirect')
                        total = 0
                        while block := response.read(1024 * 1024):
                            total += len(block)
                            if total > MAX_SOURCE_BYTES:
                                raise DataSQLiteBuildError('Source download exceeds bound')
                            output.write(block)
                except urllib.error.HTTPError as exc:
                    code = exc.code
                    exc.close()
                    if code not in RETRYABLE_HTTP_STATUS:
                        raise DataSQLiteBuildError(f'Source download rejected (HTTP {code})') from None
                    failure = f'HTTP {code}'
                except urllib.error.URLError as exc:
                    if not isinstance(exc.reason, (TimeoutError, ConnectionError)):
                        raise DataSQLiteBuildError('Source download connection or TLS validation failed') from None
                    failure = 'connection interrupted'
                except (TimeoutError, ConnectionError, http.client.IncompleteRead):
                    failure = 'connection interrupted'
            if not failure:
                _verify_download(partial, source, sqlite=sqlite)
                os.link(partial, target)
                return
        finally:
            partial.unlink(missing_ok=True)
        if attempt + 1 == DOWNLOAD_ATTEMPTS:
            raise DataSQLiteBuildError(f'Source download exhausted {DOWNLOAD_ATTEMPTS} attempts ({failure})')
        time.sleep(2 ** attempt)


def _safe_tar_extract(archive: Path, output: Path) -> Path:
    output.mkdir(parents=True, exist_ok=False)
    with tarfile.open(archive, 'r:xz') as tar:
        members = tar.getmembers()
        if sum(member.size for member in members) > MAX_EXPANDED_BYTES or len(members) > 100_000:
            raise DataSQLiteBuildError('Python source expansion limit exceeded')
        seen: set[str] = set()
        for member in members:
            path = PurePosixPath(member.name)
            if (path.is_absolute() or '..' in path.parts or not path.parts
                    or path.parts[0] != 'Python-3.14.7' or str(path) in seen
                    or not (member.isfile() or member.isdir() or member.issym() or member.islnk())):
                raise DataSQLiteBuildError('Unsafe Python source archive member')
            if member.issym() and PurePosixPath(member.linkname).is_absolute():
                raise DataSQLiteBuildError('Unsafe Python source symlink')
            seen.add(str(path))
        tar.extractall(output, members=members, filter='data')
    root = output/'Python-3.14.7'
    if not root.is_dir():
        raise DataSQLiteBuildError('Python source root is missing')
    return root


def _safe_zip_extract(archive: Path, output: Path) -> Path:
    output.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(archive) as zipped:
        infos = zipped.infolist()
        if sum(info.file_size for info in infos) > MAX_EXPANDED_BYTES or len(infos) > 10_000:
            raise DataSQLiteBuildError('SQLite source expansion limit exceeded')
        seen: set[str] = set()
        for info in infos:
            path = PurePosixPath(info.filename)
            mode = (info.external_attr >> 16) & 0xFFFF
            if (path.is_absolute() or '..' in path.parts or not path.parts
                    or path.parts[0] != 'sqlite-amalgamation-3530400'
                    or str(path) in seen or stat.S_ISLNK(mode)):
                raise DataSQLiteBuildError('Unsafe SQLite source archive member')
            seen.add(str(path))
        zipped.extractall(output)
    root = output/'sqlite-amalgamation-3530400'
    if not root.is_dir():
        raise DataSQLiteBuildError('SQLite source root is missing')
    return root


def patch_module_source(source: str) -> str:
    """Give the CPython extension a private import name without altering its DB-API."""
    name = '.m_name = "_sqlite3"'
    init = 'PyInit__sqlite3(void)'
    if source.count(name) != 1 or source.count(init) != 1:
        raise DataSQLiteBuildError('CPython sqlite module shape changed')
    return source.replace(name, '.m_name = "_wom_sqlite3"').replace(
        init, 'PyInit__wom_sqlite3(void)')


def _run(command: list[str], *, cwd: Path, log: Path, env: dict | None = None,
         timeout: float = 300) -> str:
    log.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(command, cwd=cwd, env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        log.write_bytes(exc.stdout or b'')
        raise DataSQLiteBuildError(f'Data SQLite build timed out: {log.name}') from exc
    log.write_bytes(result.stdout)
    if result.returncode:
        raise DataSQLiteBuildError(f'Data SQLite build failed: {log.name} (exit {result.returncode})')
    return result.stdout.decode('utf-8', errors='replace')


def _probe(python: Path, extension: Path, work: Path, log: Path, env: dict) -> dict:
    code = f'''import importlib.util,json,pathlib,sys,tempfile
p={str(extension)!r}
spec=importlib.util.spec_from_file_location("_wom_sqlite3",p)
m=importlib.util.module_from_spec(spec); sys.modules["_wom_sqlite3"]=m; spec.loader.exec_module(m)
root=pathlib.Path(tempfile.mkdtemp(prefix="wom-sqlite-probe-"))
source=m.connect(root/"source.db", isolation_level=None)
try:
    mode=source.execute("pragma journal_mode=WAL").fetchone()[0]
    source.execute("pragma synchronous=FULL")
    source.execute("create table strict_probe(value integer not null) strict")
    source.execute("insert into strict_probe values (1)")
    source.execute("create virtual table text_probe using fts5(value, tokenize='trigram')")
    source.execute("insert into text_probe values ('mysteries')")
    target=m.connect(root/"backup.db", isolation_level=None)
    try: source.backup(target)
    finally: target.close()
    options={{row[0] for row in source.execute("pragma compile_options")}}
    report={{"sqlite_version":m.sqlite_version,"wal":mode.lower()=="wal",
      "strict":source.execute("select value from strict_probe").fetchone()[0]==1,
      "fts5_trigram":source.execute("select count(*) from text_probe where text_probe match 'ste'").fetchone()[0]==1,
      "backup":True,"threadsafe":m.threadsafety,"compile_options":sorted(options)}}
    print(json.dumps(report,sort_keys=True))
finally: source.close()
'''
    raw = _run([str(python), '-I', '-B', '-c', code], cwd=work, log=log, env=env)
    try:
        return json.loads(raw.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError) as exc:
        raise DataSQLiteBuildError('Data SQLite probe did not return JSON') from exc


def stage_data_sqlite(runtime: Path, logs: Path, *, lock_path: Path = LOCK,
                      python_archive: Path | None = None,
                      sqlite_archive: Path | None = None,
                      env: dict | None = None) -> dict:
    """Compile/install the pinned data driver into one already-extracted runtime."""
    if sys.platform != 'darwin' or os.uname().machine != 'arm64':
        raise DataSQLiteBuildError('Data SQLite staging requires macOS arm64')
    lock = read_lock(lock_path)
    python = runtime/'bin/python3'
    if not python.is_file() or not os.access(python, os.X_OK):
        raise DataSQLiteBuildError('Bundled Python interpreter is missing')
    clean_env = dict(env or os.environ)
    for key in list(clean_env):
        if key.startswith(('PYTHON', 'DYLD_', 'LD_')) or key in {'VIRTUAL_ENV', 'UV_PROJECT_ENVIRONMENT'}:
            clean_env.pop(key, None)
    with tempfile.TemporaryDirectory(prefix='.wom-data-sqlite-', dir=runtime.parent) as name:
        work = Path(name)
        py_archive = python_archive or work/lock['python_source']['filename']
        sq_archive = sqlite_archive or work/lock['sqlite_source']['filename']
        if python_archive is None:
            download_source(lock['python_source'], py_archive)
        else:
            _verify_download(py_archive, lock['python_source'])
        if sqlite_archive is None:
            download_source(lock['sqlite_source'], sq_archive, sqlite=True)
        else:
            _verify_download(sq_archive, lock['sqlite_source'], sqlite=True)
        py_source = _safe_tar_extract(py_archive, work/'python-source')
        sq_source = _safe_zip_extract(sq_archive, work/'sqlite-source')
        sqlite_c = sq_source/'sqlite3.c'
        if sha3_256(sqlite_c) != lock['sqlite_source']['sqlite3_c_sha3_256']:
            raise DataSQLiteBuildError('sqlite3.c SHA3-256 mismatch')
        original_module = py_source/'Modules/_sqlite/module.c'
        patched = work/'module.c'
        patched.write_text(patch_module_source(original_module.read_text(encoding='utf-8')), encoding='utf-8')
        suffix = _run([str(python), '-I', '-B', '-c',
                       'import sysconfig; print(sysconfig.get_config_var("EXT_SUFFIX"))'],
                      cwd=work, log=logs/'data-sqlite-suffix.log', env=clean_env).strip()
        platlib = Path(_run([str(python), '-I', '-B', '-c',
                            'import sysconfig; print(sysconfig.get_path("platlib"))'],
                           cwd=work, log=logs/'data-sqlite-platlib.log', env=clean_env).strip())
        resolved_runtime = runtime.resolve(strict=True)
        try:
            platlib.resolve(strict=False).relative_to(resolved_runtime)
        except ValueError as exc:
            raise DataSQLiteBuildError('Data SQLite install path escapes runtime') from exc
        platlib.mkdir(parents=True, exist_ok=True)
        target = platlib/f"{lock['module_name']}{suffix}"
        if target.exists() or target.is_symlink():
            raise DataSQLiteBuildError('Refusing to replace an existing Data SQLite extension')
        compiler = shutil.which('clang')
        if compiler is None:
            raise DataSQLiteBuildError('Target compiler clang is unavailable')
        sqlite_dir = py_source/'Modules/_sqlite'
        sources = [patched if item == 'module.c' else sqlite_dir/item for item in SQLITE_SOURCES]
        command = [compiler, '-bundle', '-undefined', 'dynamic_lookup', '-arch', 'arm64', '-O2', '-fPIC',
                   '-DPy_BUILD_CORE_MODULE=1', *[f'-D{item}' for item in COMPILE_DEFINITIONS],
                   f'-I{runtime / "include/python3.14"}', f'-I{py_source / "Include"}',
                   f'-I{py_source / "Include/internal"}', f'-I{py_source}', f'-I{sqlite_dir}',
                   f'-I{sq_source}', *map(str, sources), str(sqlite_c), '-o', str(target)]
        _run(command, cwd=work, log=logs/'data-sqlite-compile.log', env=clean_env, timeout=600)
        dependencies = _run(['otool', '-arch', 'arm64', '-L', str(target)], cwd=work,
                            log=logs/'data-sqlite-loads.log', env=clean_env)
        for line in dependencies.splitlines()[1:]:
            dependency = line.strip().split(' (', 1)[0]
            if dependency and not dependency.startswith(('/usr/lib/', '/System/Library/')):
                raise DataSQLiteBuildError('Data SQLite extension has a non-system dynamic dependency')
        probe = _probe(python, target, work, logs/'data-sqlite-probe.log', clean_env)
        options = set(probe.get('compile_options', []))
        if (probe.get('sqlite_version') != lock['sqlite_version'] or not probe.get('wal')
                or not probe.get('strict') or not probe.get('fts5_trigram') or not probe.get('backup')
                or not set(lock['required_compile_options']).issubset(options)):
            raise DataSQLiteBuildError('Data SQLite capability probe failed')
        relative = target.resolve(strict=True).relative_to(resolved_runtime).as_posix()
        return {
            'module': lock['module_name'], 'extension': relative,
            'sqlite_version': probe['sqlite_version'],
            'compile_options': sorted(options),
            'python_source_sha256': lock['python_source']['sha256'],
            'sqlite_archive_sha256': lock['sqlite_source']['sha256'],
            'sqlite_archive_sha3_256': lock['sqlite_source']['sha3_256'],
            'sqlite3_c_sha3_256': lock['sqlite_source']['sqlite3_c_sha3_256'],
            'source_lock': lock,
        }


if __name__ == '__main__':
    print('This module is invoked by scripts/bundle_engine.py; it is not a runtime installer.', file=sys.stderr)
    raise SystemExit(2)
