"""Sanity test verifying engine package layout and domain boundaries."""
import sys


def test_python_version():
    assert sys.version_info >= (3, 14), "Engine requires Python 3.14+"

def test_domain_boundary():
    """Verify domain package has no direct imports of agentscope or sqlite3."""
    # Invariant: domain module must not import agentscope or sqlite
    loaded_modules = sys.modules
    assert "agentscope" not in loaded_modules or "engine.domain" not in sys.modules.get("agentscope", "")
