"""
Regression guard for card #321: "ANTSAbot ignores specific strategy, describes
parent therapy only."

Reported example: a practitioner (WEB_ASSISTANT persona) asks ANTSAbot to
describe 'chair work' within 'schema therapy'; ANTSAbot describes schema
therapy generally and never mentions chair work.

There is no retrieval/RAG pipeline behind this kind of question — the only
pgvector-backed semantic search available to WEB_ASSISTANT
(semantic_search_sessions, tools.py) is scoped to a client's own session
transcripts, not a clinical knowledge base of therapy modalities/techniques.
So a "describe this technique" question is answered directly by the model
from its own general knowledge, with no tool call and no chunking/retrieval
step involved. The fix is therefore a system-prompt instruction telling the
model to answer about the exact named technique rather than substituting a
general description of the parent modality.

No pytest-asyncio dependency — follow the repo's asyncio.run-free pattern
used by the other persona tests (they only touch prompt text/config).
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from personas import PersonaType, persona_manager  # noqa: E402


def test_web_assistant_prompt_instructs_specific_strategy_focus():
    """
    The WEB_ASSISTANT system prompt must explicitly instruct the model to
    answer about the specific named strategy/technique when one is asked for
    within a broader modality, rather than describing the parent modality.
    """
    prompt = persona_manager.get_persona(PersonaType.WEB_ASSISTANT).system_prompt
    lower = prompt.lower()

    # Must name the failure mode it's guarding against (specific technique
    # nested inside a broader modality) and instruct against substituting
    # the parent/general description.
    assert "specific strategy" in lower or "specific technique" in lower
    assert "modality" in lower or "parent therapy" in lower
    assert "do not" in lower and (
        "general description" in lower or "parent modality" in lower or "parent therapy" in lower
    )
