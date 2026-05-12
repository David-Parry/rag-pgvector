"""Tests for the chonkie-backed text splitter in ``rag_core.chunking``.

Covers the duck-typed ``TextSplitter`` contract that ``VectorizeService``
depends on, plus the legislative-marker boundary behavior that motivates the
chonkie swap in the first place.
"""

from __future__ import annotations

import pytest

from rag_core.chunking import (
    LEGISLATIVE_DELIMITERS,
    TextSplitter,
    build_text_splitter,
)


@pytest.fixture
def splitter() -> TextSplitter:
    return build_text_splitter(chunk_size=200)


def test_returns_object_satisfying_textsplitter_protocol() -> None:
    sp = build_text_splitter()
    assert isinstance(sp, TextSplitter)


def test_empty_input_returns_empty_list(splitter: TextSplitter) -> None:
    assert splitter.split_text("") == []


def test_short_input_returns_single_chunk_preserving_content(
    splitter: TextSplitter,
) -> None:
    text = "A short legislative excerpt that fits in one chunk."
    parts = splitter.split_text(text)
    assert len(parts) == 1
    assert parts[0] == text


def test_join_of_chunks_is_a_superset_of_the_original_tokens(
    splitter: TextSplitter,
) -> None:
    text = (
        "Preamble line one of a govinfo style document.\n"
        "There is some narrative prose here that spans a couple of sentences. "
        "It should chunk cleanly without losing token content."
    )
    parts = splitter.split_text(text)
    joined = "".join(parts)
    for token in ("Preamble", "govinfo", "narrative", "chunk"):
        assert token in joined, token


def test_legislative_section_markers_start_new_chunks() -> None:
    """SEC. headers must begin a chunk so the heading is embedded with its body.

    We pick a chunk_size small enough that two SEC.-delimited sections cannot
    fit in a single merged chunk, forcing the level-0 boundary to actually fire.
    """
    sp = build_text_splitter(chunk_size=120)
    text = (
        "Preamble line.\n"
        "SEC. 101. Short title.\n"
        "This Act may be cited as the Example Act of 2026, hereinafter the Act.\n"
        "SEC. 102. Definitions.\n"
        "In this Act the following definitions apply: widget means a small thing.\n"
        "SEC. 201. Enforcement.\n"
        "Rules shall be enforced as written by the Secretary."
    )
    parts = sp.split_text(text)

    assert len(parts) >= 2, parts
    starts = [p.lstrip("\n").lstrip() for p in parts]
    sec_starts = [s for s in starts if s.startswith("SEC. ")]
    assert len(sec_starts) >= 2, (
        f"Expected at least two chunks to begin with 'SEC. ', got starts={starts!r}"
    )


def test_titles_and_section_symbols_are_recognized_as_boundaries() -> None:
    """TITLE / § markers must also create chunk boundaries when size forces it."""
    sp = build_text_splitter(chunk_size=120)
    text = (
        "Front matter for the package.\n"
        "TITLE I - GENERAL PROVISIONS\n"
        "General provisions establish the scope of this Act and its administration.\n"
        "§ 1234. Records to be kept.\n"
        "Each covered entity shall maintain records of all relevant transactions.\n"
        "§ 1235. Inspection authority.\n"
        "The Secretary may inspect records during normal business hours."
    )
    parts = sp.split_text(text)
    starts = [p.lstrip("\n").lstrip() for p in parts]

    has_title = any(s.startswith("TITLE ") for s in starts)
    has_section_symbol = any(s.startswith("§") for s in starts)
    assert has_title or has_section_symbol, (
        f"Expected at least one chunk to begin with 'TITLE ' or '§', got starts={starts!r}"
    )


def test_mid_sentence_section_references_do_not_create_false_boundaries() -> None:
    """Inline citations like '...as defined in Sec. 101 of the Act' must NOT split.

    Each LEGISLATIVE_DELIMITERS entry begins with ``\\n``, so a marker that
    appears in the middle of a sentence has no leading newline and is left
    inside its surrounding sentence/paragraph chunk.
    """
    sp = build_text_splitter(chunk_size=200)
    text = (
        "This paragraph references SEC. 101 of the Act in passing and also "
        "mentions TITLE I as a cross-reference, but it does not start a new "
        "section here. The text continues describing related background."
    )
    parts = sp.split_text(text)

    assert len(parts) == 1, (
        f"Mid-sentence references should not start a new chunk; got {parts!r}"
    )


def test_legislative_delimiters_all_start_with_newline() -> None:
    """Defensive invariant: every level-0 delimiter must be newline-anchored.

    A delimiter that doesn't start with ``\\n`` would false-match inside
    sentences (e.g. plain ``"SEC. "`` matching ``"see SEC. 101 of..."``).
    """
    for delim in LEGISLATIVE_DELIMITERS:
        assert delim.startswith("\n"), delim
