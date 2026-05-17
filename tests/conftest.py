"""Shared pytest fixtures for optimAI tests."""

import pytest


@pytest.fixture
def sample_workdir(tmp_path):
    """Provide a temporary workdir for shell sandbox tests."""
    return tmp_path
