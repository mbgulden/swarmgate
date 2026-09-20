"""Tests for configurable swarmgate bridge paths.

The bridge's two fixed locations — the swarmlock daemon socket
(``/tmp/swarmlock.sock``) and the pending-decisions file
(``~/.swarmgate/pending_decisions.json``) — are unix-leaning defaults.
Both must be overridable via explicit argument, ``configure()``, or env var,
with the module constants left as working override points for tests.
"""

import json
import os
from pathlib import Path

import pytest

import swarmgate.bridge as bridge
from swarmgate.bridge import (
    ENV_PENDING_FILE,
    ENV_SWARMLOCK_SOCK,
    PENDING_FILE,
    SWARMLOCK_SOCK,
    PendingDecisionStore,
    resolve_swarmock_socket_path,
)


@pytest.fixture(autouse=True)
def _clean_store_config(monkeypatch):
    """Isolate global store config between tests."""
    monkeypatch.delenv(ENV_PENDING_FILE, raising=False)
    monkeypatch.delenv(ENV_SWARMLOCK_SOCK, raising=False)
    PendingDecisionStore.configure(None)
    yield
    PendingDecisionStore.configure(None)


def test_socket_path_defaults_to_module_constant():
    assert resolve_swarmock_socket_path() == SWARMLOCK_SOCK == "/tmp/swarmlock.sock"


def test_socket_path_explicit_argument_wins(monkeypatch):
    monkeypatch.setenv(ENV_SWARMLOCK_SOCK, "/env/sock")
    assert resolve_swarmock_socket_path("/explicit/sock") == "/explicit/sock"


def test_socket_path_env_override(monkeypatch):
    monkeypatch.setenv(ENV_SWARMLOCK_SOCK, "/env/sock")
    assert resolve_swarmock_socket_path() == "/env/sock"


def test_send_ipc_uses_resolved_path(monkeypatch, tmp_path):
    """send_swarmlock_ipc with an explicit path pointing nowhere returns None
    without touching the default socket location."""
    missing = tmp_path / "no-daemon-here.sock"
    assert bridge.send_swarmlock_ipc({"action": "PING"}, socket_path=str(missing)) is None


def test_pending_store_configure_explicit_path(tmp_path):
    target = tmp_path / "custom" / "pending.json"
    PendingDecisionStore.configure(target)
    assert PendingDecisionStore._path() == target
    PendingDecisionStore.save_all({"d1": {"x": 1}})
    assert target.exists()
    assert PendingDecisionStore.load_all() == {"d1": {"x": 1}}


def test_pending_store_env_override(monkeypatch, tmp_path):
    target = tmp_path / "env-pending.json"
    monkeypatch.setenv(ENV_PENDING_FILE, str(target))
    assert PendingDecisionStore._path() == target
    PendingDecisionStore.save_all({"d2": {"y": 2}})
    assert json.loads(target.read_text()) == {"d2": {"y": 2}}


def test_pending_store_explicit_beats_env(monkeypatch, tmp_path):
    monkeypatch.setenv(ENV_PENDING_FILE, str(tmp_path / "env.json"))
    explicit = tmp_path / "explicit.json"
    PendingDecisionStore.configure(explicit)
    assert PendingDecisionStore._path() == explicit


def test_pending_store_module_constant_still_overridable(monkeypatch, tmp_path):
    """Backwards compatibility: monkeypatching PENDING_FILE (as the engine's
    test-suite does) keeps working when nothing else is configured."""
    target = tmp_path / "monkey.json"
    monkeypatch.setattr(bridge, "PENDING_FILE", target)
    assert PendingDecisionStore._path() == target
    PendingDecisionStore.save_all({"d3": {"z": 3}})
    assert target.exists()


def test_pending_store_default_unchanged():
    assert PendingDecisionStore._path() == PENDING_FILE
    assert str(PENDING_FILE).endswith(".swarmgate/pending_decisions.json")


def test_configure_none_clears():
    PendingDecisionStore.configure("/tmp/x.json")
    PendingDecisionStore.configure(None)
    assert PendingDecisionStore._configured_path is None
