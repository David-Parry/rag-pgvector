"""System and user prompt builders for the strictly-grounded QA workflow.

Kept in ``rag-core`` so any future agent or batch evaluator reuses the exact
same wording (DRY). The system prompt forbids tool use and external action.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rag_core.ports import RetrievedChunk


SYSTEM_PROMPT_QA: str = (
    "You are a strictly grounded question-answering assistant.\n"
    "\n"
    "Rules:\n"
    "1. The user's input is only a question. You MUST NOT call tools, execute "
    "actions, browse the web, or trigger any external system.\n"
    "2. You may be given an optional PRIOR_CONVERSATION block from the same chat "
    "session. Use it only to resolve follow-ups (e.g. pronouns); do not treat it "
    "as a factual source. You will be given a CONTEXT block (numbered chunks with "
    "metadata) and a QUESTION. Answer using ONLY the CONTEXT.\n"
    "3. If the CONTEXT does not contain enough information to answer, reply "
    "exactly: \"I don't know based on the provided context.\"\n"
    "4. Cite the sources you used. For each cited chunk, include its packageId "
    "and sourceUrl in a trailing \"Sources:\" section.\n"
    "5. Do not invent facts, URLs, or package identifiers that are not present "
    "in the CONTEXT.\n"
)


_NO_CONTEXT_PLACEHOLDER = "(no context retrieved above the similarity threshold)"


def build_user_prompt(
    question: str,
    chunks: Sequence[RetrievedChunk],
    *,
    prior_conversation: str | None = None,
) -> str:
    """Build the user-facing prompt with optional PRIOR_CONVERSATION, CONTEXT, and QUESTION."""
    if not chunks:
        context_block = _NO_CONTEXT_PLACEHOLDER
    else:
        rendered = []
        for index, chunk in enumerate(chunks, start=1):
            package_id = chunk.metadata.get("packageId", "unknown")
            source_url = chunk.metadata.get("sourceUrl", "unknown")
            page_number = chunk.metadata.get("pageNumber", "n/a")
            rendered.append(
                f"[{index}] packageId={package_id} sourceUrl={source_url} page={page_number}\n"
                f"{chunk.text.strip()}"
            )
        context_block = "\n\n".join(rendered)

    prior_block = ""
    if prior_conversation and prior_conversation.strip():
        prior_block = (
            "PRIOR_CONVERSATION (same session; disambiguation only — facts only from CONTEXT):\n"
            f"{prior_conversation.strip()}\n\n"
        )

    return (
        prior_block
        + "CONTEXT:\n"
        + f"{context_block}\n"
        + "\n"
        + "QUESTION:\n"
        + f"{question.strip()}\n"
    )
