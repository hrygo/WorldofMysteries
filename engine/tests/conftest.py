"""Pytest fixtures and configuration for World of Mysteries Engine."""
import pytest


@pytest.fixture
def sample_trace_id() -> str:
    return "trace_test_001"
