"""Shared text splitter — chonkie ``RecursiveChunker`` tuned for US legislative text.

Both projects use the exact same splitter so chunks produced at ingest time
match the granularity expected at query time (DRY).

The recursive rules are tailored for govinfo content (BILLS, CFR, FR, USCOURTS).
Level 0 boundaries are the literal section/title/part markers that the US Office
of the Law Revision Counsel and the GPO use in legislative drafting; falling
through to paragraphs, sentences, whitespace, and finally a character-level
fallback when a single section is too large for one chunk.

Note: chonkie 1.6.5's ``RecursiveChunker._split_text`` only honors
``RecursiveLevel.delimiters`` and ``RecursiveLevel.whitespace`` — the ``pattern``
field exists on the dataclass but is silently ignored by the chunker — so we
encode the legislative markers as literal string delimiters. Each delimiter
starts with ``\\n`` to avoid false positives on mid-sentence references like
"...as defined in Sec. 101 of the Act".
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from chonkie import RecursiveChunker, RecursiveLevel, RecursiveRules

DEFAULT_CHUNK_SIZE = 1600
"""Target maximum characters per chunk.

Using chonkie's ``tokenizer='character'`` (1 char == 1 token) for deterministic,
offline behavior — no tokenizer asset downloads. 1600 chars ≈ 400 GPT-style
tokens, sitting comfortably inside Bedrock Titan v2's 8k-token input window
while keeping chunks information-dense enough for retrieval.
"""

DEFAULT_MIN_CHARACTERS = 24
"""Below this, chonkie merges a chunk with its neighbor. Filters tiny artifacts."""

LEGISLATIVE_DELIMITERS: list[str] = [
    "\nSEC. ",
    "\nSECTION ",
    "\nSection ",
    "\nTITLE ",
    "\nSUBTITLE ",
    "\nSubtitle ",
    "\nPART ",
    "\nCHAPTER ",
    "\nARTICLE ",
    "\n§ ",
    "\n§",
]
"""Top-level section markers used by US legislative drafting.

Each starts with ``\\n`` so we only match a marker that begins a line. This
keeps mid-sentence citations like "see Sec. 101 of this Act" from being treated
as section breaks.
"""


def _legislative_rules() -> RecursiveRules:
    """Five-level cascade: section markers → paragraphs → sentences → words → chars."""
    return RecursiveRules(
        levels=[
            RecursiveLevel(
                delimiters=LEGISLATIVE_DELIMITERS,
                include_delim="next",
            ),
            RecursiveLevel(delimiters=["\n\n", "\r\n", "\n", "\r"]),
            RecursiveLevel(delimiters=[". ", "! ", "? "]),
            RecursiveLevel(whitespace=True),
            RecursiveLevel(),
        ]
    )


@runtime_checkable
class TextSplitter(Protocol):
    """Structural contract ``VectorizeService`` depends on.

    Any object exposing ``split_text(text: str) -> list[str]`` satisfies this.
    Lets us swap chunker implementations (chonkie today, something else
    tomorrow) without touching the domain layer.
    """

    def split_text(self, text: str) -> list[str]:
        """Split ``text`` into a list of chunk strings, in document order."""
        ...


class _ChonkieSplitter:
    """Adapter that exposes chonkie's chunker behind the ``split_text`` contract."""

    def __init__(self, chunker: RecursiveChunker) -> None:
        self._chunker = chunker

    def split_text(self, text: str) -> list[str]:
        if not text:
            return []
        return [c.text for c in self._chunker(text)]


def build_text_splitter(
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    min_characters_per_chunk: int = DEFAULT_MIN_CHARACTERS,
) -> TextSplitter:
    """Return the canonical splitter — chonkie ``RecursiveChunker`` with legislative rules.

    Args:
        chunk_size: Target maximum characters per chunk (chonkie's character
            tokenizer treats 1 char == 1 token).
        min_characters_per_chunk: Below this length, chonkie merges the chunk
            with a neighbor instead of emitting it standalone.

    Returns:
        A ``TextSplitter`` (duck-typed object exposing ``split_text``).
    """
    chunker = RecursiveChunker(
        tokenizer="character",
        chunk_size=chunk_size,
        rules=_legislative_rules(),
        min_characters_per_chunk=min_characters_per_chunk,
    )
    return _ChonkieSplitter(chunker)
