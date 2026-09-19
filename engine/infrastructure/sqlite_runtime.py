"""Single persistence-driver seam for the authoritative local data kernel.

Release builds stage ``_wom_sqlite3`` from the exact CPython 3.14.7 sqlite
binding sources and SQLite 3.53.4 amalgamation. Development/test environments
may not have that private native extension, so they fall back to stdlib sqlite3;
DatabaseManager's production-default open path still rejects that fallback.
"""
from __future__ import annotations

try:
    import _wom_sqlite3 as _driver
    BUNDLED_DATA_SQLITE = True
except ImportError:  # development/test compatibility only; production fails closed later
    import sqlite3 as _driver
    BUNDLED_DATA_SQLITE = False


class _SQLiteDriver:
    sqlite_version = _driver.sqlite_version
    sqlite_version_info = tuple(int(part) for part in _driver.sqlite_version.split('.'))
    module_name = _driver.__name__
    bundled = BUNDLED_DATA_SQLITE

    def __getattr__(self, name):
        return getattr(_driver, name)


sqlite3 = _SQLiteDriver()


def production_driver_ready(expected_version: str) -> bool:
    return BUNDLED_DATA_SQLITE and sqlite3.sqlite_version == expected_version
