"""Host-independent contract checks for the private production SQLite driver."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
import build_data_sqlite as builder

from engine.infrastructure.database_manager import DatabaseManager, DatabasePaths, StorageError
from engine.infrastructure.sqlite_runtime import BUNDLED_DATA_SQLITE, production_driver_ready, sqlite3


def test_data_sqlite_source_lock_is_exact_and_public():
    lock = builder.read_lock()
    assert lock['python_version'] == '3.14.7'
    assert lock['sqlite_version'] == '3.53.4'
    assert lock['module_name'] == '_wom_sqlite3'
    assert lock['python_source'] == {
        'url': 'https://www.python.org/ftp/python/3.14.7/Python-3.14.7.tar.xz',
        'filename': 'Python-3.14.7.tar.xz',
        'size': 24053924,
        'sha256': '3b48dac8fb59f62eaa67ac83c1eb12bda1b7a08406dd286e252c11a66be27f81',
    }
    assert lock['sqlite_source']['url'] == 'https://www.sqlite.org/2026/sqlite-amalgamation-3530400.zip'
    assert lock['sqlite_source']['sha3_256'] == '628a44cfe82c66aed1ccbbe85a562d2e33ebe64b3288981ed76285612227934e'
    assert lock['sqlite_source']['sqlite3_c_sha3_256'] == '67f423e9ebbbdc473cbc4772c872ee6b89f31fde4ed0279a5c25d5f65c043a16'
    assert {'ENABLE_FTS5','ENABLE_GEOPOLY','ENABLE_PERCENTILE','ENABLE_RTREE','THREADSAFE=1'} <= set(lock['required_compile_options'])


@pytest.mark.parametrize(('path','value'), [
    (('sqlite_version',), '3.53.3'),
    (('python_version',), '3.14.8'),
    (('module_name',), '_sqlite3'),
    (('python_source','url'), 'https://example.invalid/Python.tar.xz'),
    (('python_source','sha256'), '0'*63),
    (('python_source','size'), True),
    (('sqlite_source','url'), 'http://www.sqlite.org/2026/sqlite-amalgamation-3530400.zip'),
    (('sqlite_source','sha3_256'), '0'*63),
    (('sqlite_source','sqlite3_c_sha3_256'), '0'*63),
])
def test_data_sqlite_lock_tampering_is_rejected(tmp_path, path, value):
    lock = copy.deepcopy(builder.read_lock())
    target = lock
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    file = tmp_path/'lock.json'
    file.write_text(json.dumps(lock))
    with pytest.raises(builder.DataSQLiteBuildError):
        builder.read_lock(file)


def test_cpython_module_patch_is_narrow_and_fail_closed():
    original = 'before\n    .m_name = "_sqlite3",\nafter\nPyInit__sqlite3(void)\nend\n'
    patched = builder.patch_module_source(original)
    assert '.m_name = "_wom_sqlite3"' in patched
    assert 'PyInit__wom_sqlite3(void)' in patched
    assert '.m_name = "_sqlite3"' not in patched
    assert 'PyInit__sqlite3(void)' not in patched
    with pytest.raises(builder.DataSQLiteBuildError):
        builder.patch_module_source('shape changed')
    with pytest.raises(builder.DataSQLiteBuildError):
        builder.patch_module_source(original + 'PyInit__sqlite3(void)\n')


def test_development_driver_fallback_is_never_production_ready():
    # Normal CI does not install the package-only native extension. Its stdlib
    # driver remains useful for compatibility tests, but cannot satisfy release.
    if not BUNDLED_DATA_SQLITE:
        assert sqlite3.module_name == 'sqlite3'
        assert not production_driver_ready('3.53.4')
    assert sqlite3.sqlite_version_info == tuple(map(int, sqlite3.sqlite_version.split('.')))


@pytest.mark.asyncio
async def test_production_open_requires_private_driver_before_touching_disk(tmp_path):
    if BUNDLED_DATA_SQLITE:
        pytest.skip('This host already provides the packaged private driver')
    paths = DatabasePaths.for_world(tmp_path, 'world')
    with pytest.raises(StorageError, match='baseline'):
        await DatabaseManager.open(paths)
    assert not paths.world.exists()
