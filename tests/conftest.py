"""Shared pytest fixtures for optimAI tests."""

from pathlib import Path

import pytest

from optimai.shell import load_blacklist

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def sample_workdir(tmp_path):
    """Provide a temporary workdir for shell sandbox tests."""
    return tmp_path


@pytest.fixture
def sample_blacklist_file():
    """Path to the real, versioned blacklist file (config/blacklist.txt)."""
    return REPO_ROOT / "config" / "blacklist.txt"


@pytest.fixture
def blacklist_patterns(sample_blacklist_file):
    """Compiled patterns from the real blacklist (DEC-008)."""
    return load_blacklist(sample_blacklist_file)
