import json
import sys
import types
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def test_server():
    """This unit-only module does not need the suite's HTTP server."""
    yield


def _install_fake_agent(monkeypatch, calls):
    package = types.ModuleType("agent")
    skills = types.ModuleType("agent.skill_commands")
    prompt = types.ModuleType("agent.prompt_builder")
    skills.reload_skills = lambda: calls.append("reload") or {}
    prompt.clear_skills_system_prompt_cache = (
        lambda *, clear_snapshot=False: calls.append(("clear", clear_snapshot))
    )
    monkeypatch.setitem(sys.modules, "agent", package)
    monkeypatch.setitem(sys.modules, "agent.skill_commands", skills)
    monkeypatch.setitem(sys.modules, "agent.prompt_builder", prompt)


def _write_generation(home: Path, generation: str):
    marker = home / ".agentspec-content" / "active.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"generation": generation}), encoding="utf-8")


def test_new_generation_refreshes_skills_once(monkeypatch, tmp_path):
    calls = []
    _install_fake_agent(monkeypatch, calls)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    from api import agent_content
    monkeypatch.setattr(agent_content, "_last_activated_generation", None)
    _write_generation(tmp_path, "sha-1")

    assert agent_content.activate_current_content_for_new_session() is True
    assert agent_content.activate_current_content_for_new_session() is False
    assert calls == ["reload", ("clear", True)]


def test_changed_generation_refreshes_on_next_session(monkeypatch, tmp_path):
    calls = []
    _install_fake_agent(monkeypatch, calls)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    from api import agent_content
    monkeypatch.setattr(agent_content, "_last_activated_generation", None)
    _write_generation(tmp_path, "sha-1")
    agent_content.activate_current_content_for_new_session()
    _write_generation(tmp_path, "sha-2")

    assert agent_content.activate_current_content_for_new_session() is True
    assert calls == ["reload", ("clear", True), "reload", ("clear", True)]


def test_missing_or_invalid_marker_is_fail_open(monkeypatch, tmp_path):
    calls = []
    _install_fake_agent(monkeypatch, calls)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    from api import agent_content
    monkeypatch.setattr(agent_content, "_last_activated_generation", None)

    assert agent_content.activate_current_content_for_new_session() is False
    marker = tmp_path / ".agentspec-content" / "active.json"
    marker.parent.mkdir(parents=True)
    marker.write_text("not json", encoding="utf-8")
    assert agent_content.activate_current_content_for_new_session() is False
    assert calls == []


def test_session_new_route_activates_before_creating_session():
    source = Path("api/routes.py").read_text(encoding="utf-8")
    block = source[source.index('if parsed.path == "/api/session/new":'):]
    block = block[:block.index('if parsed.path == "/api/session/compression-recovery/start":')]
    assert "activate_current_content_for_new_session" in block
    assert block.index("activate_current_content_for_new_session") < block.index("s = new_session(")
