from __future__ import annotations

from rag_core.ports import RetrievedChunk
from rag_core.prompts import SYSTEM_PROMPT_QA, build_user_prompt


def _chunk(idx: int, text: str = "facts") -> RetrievedChunk:
    return RetrievedChunk(
        id=f"c{idx}",
        text=text,
        metadata={
            "packageId": f"PKG{idx}",
            "sourceUrl": f"https://example.gov/{idx}",
            "pageNumber": idx,
        },
        score=0.1 * idx,
    )


def test_system_prompt_explicitly_forbids_tools_and_external_action() -> None:
    assert "MUST NOT call tools" in SYSTEM_PROMPT_QA
    assert "external system" in SYSTEM_PROMPT_QA


def test_system_prompt_requires_grounded_only_answers() -> None:
    assert "I don't know based on the provided context." in SYSTEM_PROMPT_QA
    assert "Answer using ONLY the CONTEXT" in SYSTEM_PROMPT_QA


def test_user_prompt_renders_numbered_chunks_with_metadata() -> None:
    chunks = [_chunk(1, "alpha"), _chunk(2, "beta")]
    prompt = build_user_prompt("What is alpha?", chunks)
    assert "[1]" in prompt
    assert "[2]" in prompt
    assert "packageId=PKG1" in prompt
    assert "sourceUrl=https://example.gov/2" in prompt
    assert "alpha" in prompt
    assert "beta" in prompt
    assert prompt.rstrip().endswith("What is alpha?")


def test_user_prompt_handles_empty_context() -> None:
    prompt = build_user_prompt("anything?", [])
    assert "(no context retrieved above the similarity threshold)" in prompt
    assert "QUESTION" in prompt


def test_user_prompt_includes_prior_conversation_when_provided() -> None:
    chunks = [_chunk(1, "only facts here")]
    prompt = build_user_prompt(
        "What about that?",
        chunks,
        prior_conversation="User: What is alpha?\nAssistant: Alpha is X.",
    )
    assert "PRIOR_CONVERSATION" in prompt
    assert "User: What is alpha?" in prompt
    assert "CONTEXT:" in prompt
    assert "QUESTION:" in prompt
    assert prompt.endswith("What about that?\n")


def test_chunking_factory_uses_configured_size() -> None:
    from rag_core.chunking import build_text_splitter

    splitter = build_text_splitter(chunk_size=50)
    parts = splitter.split_text("a" * 200)
    assert all(len(p) <= 50 for p in parts)
    assert len(parts) >= 4
