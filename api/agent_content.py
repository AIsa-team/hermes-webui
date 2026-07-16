"""Activate externally managed AgentSpec content at new-session boundaries."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import threading


logger = logging.getLogger(__name__)
_activation_lock = threading.Lock()
_last_activated_generation: str | None = None


def _active_generation() -> str | None:
    marker = (
        Path(os.environ.get("HERMES_HOME", "~/.hermes")).expanduser()
        / ".agentspec-content"
        / "active.json"
    )
    try:
        value = json.loads(marker.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError, TypeError):
        logger.warning("Ignoring invalid AgentSpec content marker at %s", marker)
        return None
    generation = value.get("generation") if isinstance(value, dict) else None
    return generation.strip() if isinstance(generation, str) and generation.strip() else None


def activate_current_content_for_new_session() -> bool:
    """Refresh skill discovery/caches once for each managed generation.

    Existing session Agent instances are intentionally untouched. A failure is
    fail-open for session creation and will be retried at the next new session.
    """
    global _last_activated_generation
    generation = _active_generation()
    if not generation or generation == _last_activated_generation:
        return False
    with _activation_lock:
        generation = _active_generation()
        if not generation or generation == _last_activated_generation:
            return False
        try:
            from agent.skill_commands import reload_skills
            from agent.prompt_builder import clear_skills_system_prompt_cache

            reload_skills()
            clear_skills_system_prompt_cache(clear_snapshot=True)
        except Exception:
            logger.warning(
                "Could not activate AgentSpec content generation %s; will retry",
                generation,
                exc_info=True,
            )
            return False
        _last_activated_generation = generation
        logger.info("Activated AgentSpec content generation %s for new sessions", generation)
        return True
