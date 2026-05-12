"""Smoke tests for the rag-pgvector Helm chart.

Runs ``helm lint`` and ``helm template`` against the chart on disk to catch
regressions in template rendering. Skipped automatically if ``helm`` isn't on PATH.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

CHART_PATH = Path(__file__).resolve().parent.parent / "infra" / "helm" / "rag-pgvector"

REQUIRED_VALUES = [
    "--set",
    "aws.auth.bearerToken=fake-bearer",
    "--set",
    "anthropic.apiKey=fake-anthropic",
    "--set",
    "govinfo.apiKey=fake-govinfo",
]


pytestmark = pytest.mark.skipif(
    shutil.which("helm") is None,
    reason="helm not installed",
)


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["helm", *args],
        check=False,
        capture_output=True,
        text=True,
    )


def test_helm_lint_passes() -> None:
    result = _run("lint", str(CHART_PATH), *REQUIRED_VALUES)
    assert result.returncode == 0, f"helm lint failed:\n{result.stdout}\n{result.stderr}"


@pytest.mark.parametrize("provider", ["anthropic", "bedrock", "ollama"])
def test_helm_template_renders_for_each_llm_provider(provider: str) -> None:
    result = _run(
        "template",
        "rag",
        str(CHART_PATH),
        *REQUIRED_VALUES,
        "--set",
        f"qa.llmProvider={provider}",
    )
    assert result.returncode == 0, f"helm template failed:\n{result.stderr}"
    rendered = result.stdout
    assert "kind: StatefulSet" in rendered
    assert "kind: Deployment" in rendered
    assert "name: vectorizer" in rendered
    assert "name: question-api" in rendered
    assert "AWS_BEARER_TOKEN_BEDROCK" in rendered
    assert "EMBEDDING_MODEL" in rendered
    assert "ANTHROPIC_MODEL" in rendered
    assert "ANTHROPIC_API_KEY" in rendered
    assert "ANTHROPIC_DIRECT_MODEL" in rendered
    assert f'value: "{provider}"' in rendered


def test_helm_template_supports_irsa_mode_without_aws_keys() -> None:
    result = _run(
        "template",
        "rag",
        str(CHART_PATH),
        "--set",
        "aws.auth.mode=irsa",
        "--set",
        "aws.auth.irsaRoleArn=arn:aws:iam::111122223333:role/rag-bedrock",
        "--set",
        "govinfo.apiKey=fake",
    )
    assert result.returncode == 0, result.stderr
    rendered = result.stdout
    assert "eks.amazonaws.com/role-arn" in rendered
    assert "AWS_BEARER_TOKEN_BEDROCK" not in rendered
    assert "AWS_ACCESS_KEY_ID" not in rendered


def test_helm_template_renders_bedrock_secret_and_role() -> None:
    result = _run(
        "template",
        "rag",
        str(CHART_PATH),
        "--set",
        "aws.auth.mode=irsa",
        "--set",
        "aws.auth.irsaRoleArn=arn:aws:iam::111122223333:role/rag-app",
        "--set",
        "bedrock.connectionSecretName=rag-bedrock-config-dev",
        "--set",
        "bedrock.roleArn=arn:aws:iam::111122223333:role/BedrockInvokeRole",
        "--set",
        "bedrock.embeddingBearerToken=fake-embedding-bearer",
        "--set",
        "qa.llmProvider=bedrock",
        "--set",
        "govinfo.apiKey=fake",
    )
    assert result.returncode == 0, result.stderr
    rendered = result.stdout
    assert "BEDROCK_CONNECTION_SECRET_NAME" in rendered
    assert "rag-bedrock-config-dev" in rendered
    assert "BEDROCK_ROLE_ARN" in rendered
    assert "AWS_BEARER_TOKEN_BEDROCK" in rendered


def test_helm_template_supports_temporary_session_credentials() -> None:
    result = _run(
        "template",
        "rag",
        str(CHART_PATH),
        "--set",
        "aws.auth.mode=accessKey",
        "--set",
        "aws.auth.accessKeyId=ASIA_TEST",
        "--set",
        "aws.auth.secretAccessKey=fake-secret",
        "--set",
        "aws.auth.sessionToken=fake-session-token",
        "--set",
        "bedrock.connectionSecretName=rag-bedrock-config-dev",
        "--set",
        "bedrock.roleArn=arn:aws:iam::111122223333:role/BedrockInvokeRole",
        "--set",
        "bedrock.embeddingBearerToken=fake-embedding-bearer",
        "--set",
        "qa.llmProvider=bedrock",
        "--set",
        "govinfo.apiKey=fake",
    )
    assert result.returncode == 0, result.stderr
    rendered = result.stdout
    assert "AWS_ACCESS_KEY_ID" in rendered
    assert "AWS_SECRET_ACCESS_KEY" in rendered
    assert "AWS_SESSION_TOKEN" in rendered
