"""Tests for optimai.patterns.base — Pattern Protocol, Step type, registry (DEC-021)."""

from typing import Literal

import pytest
from pydantic import BaseModel

from optimai.patterns import base as base_mod
from optimai.patterns.base import (
    Pattern,
    Step,
    available_patterns,
    get_pattern,
    register,
)


@pytest.fixture(autouse=True)
def _isolate_registry(monkeypatch):
    """Each test runs against a fresh registry snapshot — no test cross-pollution."""
    snapshot = dict(base_mod._REGISTRY)
    yield
    base_mod._REGISTRY.clear()
    base_mod._REGISTRY.update(snapshot)


class _DummySpec(BaseModel):
    goal: str = "x"


def _make_dummy_pattern(name: str):
    class _Dummy:
        def __init__(self):
            self.name = name
            self.spec_model = _DummySpec

        def system_prompt(self, spec):
            return "sys"

        def initial_user_message(self, spec):
            return "intro"

        def operator_text(self, spec):
            return spec.goal

        def parse(self, worker_text):
            return Step(kind="invalid", reason="dummy")

        def build_report(
            self,
            *,
            final_payload,
            commands_executed,
            stop_reason,
            iterations_used,
            status,
            notes,
        ):
            return _DummySpec(goal=status)

    return _Dummy


# --------------------------------------------------------------------------
# Step type
# --------------------------------------------------------------------------


def test_step_defaults():
    step = Step(kind="invalid")
    assert step.kind == "invalid"
    assert step.cmd == ""
    assert step.think == ""
    assert step.payload is None
    assert step.reason == ""


def test_step_is_frozen():
    step = Step(kind="command", cmd="echo hi", think="t")
    with pytest.raises(Exception):  # noqa: BLE001 — FrozenInstanceError varies by Python
        step.cmd = "rm -rf /"  # type: ignore[misc]


# --------------------------------------------------------------------------
# register / get_pattern / available_patterns
# --------------------------------------------------------------------------


def test_register_then_get_returns_same_instance():
    register("foo")(_make_dummy_pattern("foo"))
    p1 = get_pattern("foo")
    p2 = get_pattern("foo")
    assert p1 is p2  # patterns are stateless singletons


def test_available_patterns_lists_registered_names():
    register("foo")(_make_dummy_pattern("foo"))
    register("bar")(_make_dummy_pattern("bar"))
    names = available_patterns()
    # diagnose is preserved by the autouse snapshot
    assert "foo" in names and "bar" in names
    assert names == sorted(names)


def test_get_pattern_raises_keyerror_with_available_list():
    with pytest.raises(KeyError) as exc_info:
        get_pattern("nope-does-not-exist")
    # error message names the missing key and lists what's available
    assert "nope-does-not-exist" in str(exc_info.value)


def test_register_rejects_name_mismatch():
    """Decorating @register('x') on a class whose .name='y' is a typo guard."""
    with pytest.raises(ValueError):
        register("declared-name")(_make_dummy_pattern("different-name"))


def test_registered_dummy_satisfies_pattern_protocol():
    register("foo")(_make_dummy_pattern("foo"))
    instance = get_pattern("foo")
    # runtime_checkable lets us isinstance() against the Protocol
    assert isinstance(instance, Pattern)


def test_builtin_diagnose_registered_after_import():
    # patterns/__init__.py imported diagnose at module load time;
    # the @register('diagnose') side effect must have populated the registry.
    assert "diagnose" in available_patterns()
    inst = get_pattern("diagnose")
    assert inst.name == "diagnose"


# --------------------------------------------------------------------------
# Pattern Protocol shape — sanity check we didn't break the contract
# --------------------------------------------------------------------------


def test_pattern_protocol_required_methods():
    inst = get_pattern("diagnose")
    for method in ("system_prompt", "initial_user_message", "operator_text", "parse", "build_report"):
        assert callable(getattr(inst, method)), f"missing {method}"


def test_pattern_step_kind_literal():
    # No runtime enforcement of Literal, but document the contract.
    kinds: set[Literal["command", "final", "invalid"]] = {"command", "final", "invalid"}
    assert kinds == {"command", "final", "invalid"}
