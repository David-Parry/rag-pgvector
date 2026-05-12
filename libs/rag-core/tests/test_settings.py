"""Unit tests for ``rag_core.settings``.

These cover the Bedrock model-id parser used to populate the hoisted
``embedding_model`` / ``embedding_model_version`` columns in the pgvector
``rag_chunks`` table. The rule is precise enough to be easy to break by
accident, so it gets table-driven coverage.
"""

from __future__ import annotations

import pytest

from rag_core.settings import (
    AwsBedrockSettings,
    DeepEvalSettings,
    _parse_embedding_model_id,
)


@pytest.mark.parametrize(
    ("model_id", "expected_name", "expected_version"),
    [
        # Canonical Titan v2: combined family-version + Bedrock revision.
        ("amazon.titan-embed-text-v2:0", "amazon.titan-embed-text", "2.0"),
        # Cohere follows the same Bedrock convention.
        ("cohere.embed-english-v3:0", "cohere.embed-english", "3.0"),
        # No `:<rev>` segment -> just the family-version major.
        ("amazon.titan-embed-text-v2", "amazon.titan-embed-text", "2"),
        # No `-v<n>` family suffix -> just the Bedrock revision.
        ("meta.llama3-70b:0", "meta.llama3-70b", "0"),
        # Neither segment present -> empty version, untouched name.
        ("plain-model-id", "plain-model-id", ""),
        # Mid-id digits do NOT get mistaken for the version (e.g. `text2` in
        # the middle is part of the name; only end-anchored `-v<n>` counts).
        ("amazon.titan-text2-embed-v1:0", "amazon.titan-text2-embed", "1.0"),
        # Multi-digit revisions and majors round-trip.
        ("vendor.family-v12:34", "vendor.family", "12.34"),
    ],
)
def test_parse_embedding_model_id(
    model_id: str, expected_name: str, expected_version: str
) -> None:
    name, version = _parse_embedding_model_id(model_id)
    assert name == expected_name
    assert version == expected_version


def test_aws_bedrock_settings_exposes_parsed_name_and_version() -> None:
    """The properties on ``AwsBedrockSettings`` flow through the parser."""
    settings = AwsBedrockSettings(
        BEDROCK_EMBEDDING_MODEL_ID="amazon.titan-embed-text-v2:0",
        _env_file=None,
    )
    assert settings.embedding_model_name == "amazon.titan-embed-text"
    assert settings.embedding_model_version == "2.0"


def test_aws_bedrock_settings_handles_missing_revision() -> None:
    settings = AwsBedrockSettings(
        BEDROCK_EMBEDDING_MODEL_ID="amazon.titan-embed-text-v2",
        _env_file=None,
    )
    assert settings.embedding_model_name == "amazon.titan-embed-text"
    assert settings.embedding_model_version == "2"


def test_aws_bedrock_settings_supports_embedding_model_alias() -> None:
    settings = AwsBedrockSettings(
        EMBEDDING_MODEL="approved-embedding-profile",
        _env_file=None,
    )

    assert settings.embedding_model_id == "approved-embedding-profile"


def test_deepeval_settings_parse_comma_separated_grids() -> None:
    settings = DeepEvalSettings(
        DEEPEVAL_TOP_K_GRID="3,6,8",
        DEEPEVAL_THRESHOLD_GRID="0.4,0.6,0.8",
        _env_file=None,
    )

    assert settings.top_k_grid == [3, 6, 8]
    assert settings.threshold_grid == [0.4, 0.6, 0.8]


def test_deepeval_settings_parse_json_grids() -> None:
    settings = DeepEvalSettings(
        DEEPEVAL_TOP_K_GRID="[3, 6, 8]",
        DEEPEVAL_THRESHOLD_GRID="[0.4, 0.6, 0.8]",
        _env_file=None,
    )

    assert settings.top_k_grid == [3, 6, 8]
    assert settings.threshold_grid == [0.4, 0.6, 0.8]
