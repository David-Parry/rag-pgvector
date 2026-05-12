from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from rag_core.bedrock import BedrockRuntimeProvider
from rag_core.settings import AwsBedrockSettings


def _sts_client() -> MagicMock:
    client = MagicMock()
    client.assume_role.return_value = {
        "Credentials": {
            "AccessKeyId": "ASIA_TEST",
            "SecretAccessKey": "secret",
            "SessionToken": "token",
            "Expiration": datetime.now(timezone.utc) + timedelta(hours=1),
        }
    }
    return client


def test_provider_loads_connection_from_secret() -> None:
    secrets_client = MagicMock()
    secrets_client.get_secret_value.return_value = {
        "SecretString": (
            '{"Region":"us-east-1","ModelId":"approved-chat",'
            '"EmbeddingModelId":"approved-embed","ApplicationName":"RagPgvector"}'
        )
    }
    settings = AwsBedrockSettings(
        BEDROCK_CONNECTION_SECRET_NAME="rag-bedrock-config-dev",
        BEDROCK_ROLE_ARN="arn:aws:iam::123456789012:role/BedrockInvokeRole",
        _env_file=None,
    )

    provider = BedrockRuntimeProvider(
        settings,
        sts_client=_sts_client(),
        secrets_client=secrets_client,
    )

    connection = provider.get_connection()

    secrets_client.get_secret_value.assert_called_once_with(
        SecretId="rag-bedrock-config-dev"
    )
    assert connection.model_id == "approved-chat"
    assert connection.embedding_model_id == "approved-embed"


def test_provider_builds_runtime_client_with_assumed_role() -> None:
    runtime_client = MagicMock()
    boto3_client_factory = MagicMock(return_value=runtime_client)
    settings = AwsBedrockSettings(
        BEDROCK_ROLE_ARN="arn:aws:iam::123456789012:role/BedrockInvokeRole",
        ANTHROPIC_MODEL="approved-chat",
        EMBEDDING_MODEL="approved-embed",
        _env_file=None,
    )
    sts_client = _sts_client()

    provider = BedrockRuntimeProvider(
        settings,
        sts_client=sts_client,
        boto3_client_factory=boto3_client_factory,
    )

    assert provider.get_runtime_client() is runtime_client
    assert provider.get_runtime_client() is runtime_client

    sts_client.assume_role.assert_called_once()
    boto3_client_factory.assert_called_once()
    call_kwargs = boto3_client_factory.call_args.kwargs
    assert boto3_client_factory.call_args.args == ("bedrock-runtime",)
    assert call_kwargs["region_name"] == "us-east-1"
    assert call_kwargs["aws_access_key_id"] == "ASIA_TEST"


def test_provider_requires_role_when_secret_is_configured() -> None:
    settings = AwsBedrockSettings(
        BEDROCK_CONNECTION_SECRET_NAME="rag-bedrock-config-dev",
        _env_file=None,
    )
    secrets_client = MagicMock()
    secrets_client.get_secret_value.return_value = {
        "SecretString": '{"Region":"us-east-1","ModelId":"approved-chat"}'
    }
    provider = BedrockRuntimeProvider(settings, secrets_client=secrets_client)

    with pytest.raises(ValueError, match="BEDROCK_ROLE_ARN is required"):
        provider.get_runtime_client()
