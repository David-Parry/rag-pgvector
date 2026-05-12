"""Shared AWS Bedrock connection support."""

from __future__ import annotations

import os
import threading
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
from typing import Any

import boto3
from botocore.config import Config

from rag_core.settings import AwsBedrockSettings, BedrockConnectionSettings

_SECRETS_MANAGER_CONFIG = Config(connect_timeout=3, read_timeout=5, retries={"max_attempts": 1})
_CREDENTIAL_EXPIRY_BUFFER = timedelta(minutes=5)


class BedrockRuntimeProvider:
    """Loads approved Bedrock settings and creates Bedrock Runtime clients."""

    def __init__(
        self,
        settings: AwsBedrockSettings,
        *,
        sts_client: Any | None = None,  # Any: boto3 clients are dynamically generated.
        secrets_client: Any | None = None,
        boto3_client_factory: Callable[..., Any] | None = None,
    ) -> None:
        self._settings = settings
        self._connection: BedrockConnectionSettings | None = None
        self._connection_lock = threading.Lock()
        self._credentials: Mapping[str, Any] | None = None
        self._credentials_expiry = datetime.min.replace(tzinfo=timezone.utc)
        self._credentials_lock = threading.Lock()
        self._sts_client = sts_client
        self._secrets_client = secrets_client
        self._boto3_client_factory = boto3_client_factory or boto3.client
        self._runtime_client = threading.local()

    def get_connection(self) -> BedrockConnectionSettings:
        """Return secret-backed settings, or local env settings when no secret is configured."""
        if not self._settings.connection_secret_name:
            return self._settings.local_connection()
        if self._connection is not None:
            return self._connection
        with self._connection_lock:
            if self._connection is not None:
                return self._connection
            client = self._secrets_client or self._boto3_client_factory(
                "secretsmanager",
                config=_SECRETS_MANAGER_CONFIG,
            )
            response = client.get_secret_value(SecretId=self._settings.connection_secret_name)
            self._connection = BedrockConnectionSettings.from_secret(response["SecretString"])
            return self._connection

    def get_runtime_client(self) -> Any:
        """Return a thread-local Bedrock Runtime client."""
        client = getattr(self._runtime_client, "client", None)
        if client is not None:
            return client

        connection = self.get_connection()
        client_kwargs: dict[str, Any] = {
            "region_name": connection.region,
            "config": Config(
                connect_timeout=3,
                read_timeout=connection.timeout_seconds,
                retries={"max_attempts": 1},
            ),
        }
        credentials = self._assume_role_if_configured()
        if credentials is not None:
            client_kwargs.update(
                {
                    "aws_access_key_id": credentials["AccessKeyId"],
                    "aws_secret_access_key": credentials["SecretAccessKey"],
                    "aws_session_token": credentials["SessionToken"],
                }
            )

        client = self._boto3_client_factory("bedrock-runtime", **client_kwargs)
        self._runtime_client.client = client
        return client

    def configure_environment(self) -> BedrockConnectionSettings:
        """Mirror credentials and region for libraries that read AWS env vars."""
        connection = self.get_connection()
        credentials = self._assume_role_if_configured()
        if credentials is not None:
            os.environ["AWS_ACCESS_KEY_ID"] = str(credentials["AccessKeyId"])
            os.environ["AWS_SECRET_ACCESS_KEY"] = str(credentials["SecretAccessKey"])
            os.environ["AWS_SESSION_TOKEN"] = str(credentials["SessionToken"])
        elif self._settings.bearer_token is not None:
            os.environ.setdefault(
                "AWS_BEARER_TOKEN_BEDROCK",
                self._settings.bearer_token.get_secret_value(),
            )
        elif self._settings.access_key_id is not None:
            os.environ.setdefault(
                "AWS_ACCESS_KEY_ID",
                self._settings.access_key_id.get_secret_value(),
            )
            if self._settings.secret_access_key is not None:
                os.environ.setdefault(
                    "AWS_SECRET_ACCESS_KEY",
                    self._settings.secret_access_key.get_secret_value(),
                )
        os.environ["AWS_REGION"] = connection.region
        os.environ["AWS_DEFAULT_REGION"] = connection.region
        return connection

    def _assume_role_if_configured(self) -> Mapping[str, Any] | None:
        if not self._settings.role_arn:
            if self._settings.connection_secret_name:
                raise ValueError("BEDROCK_ROLE_ARN is required when BEDROCK_CONNECTION_SECRET_NAME is set")
            return None

        now = datetime.now(timezone.utc)
        if self._credentials and now < self._credentials_expiry - _CREDENTIAL_EXPIRY_BUFFER:
            return self._credentials

        with self._credentials_lock:
            now = datetime.now(timezone.utc)
            if self._credentials and now < self._credentials_expiry - _CREDENTIAL_EXPIRY_BUFFER:
                return self._credentials

            connection = self.get_connection()
            sts_client = self._sts_client or self._boto3_client_factory("sts")
            response = sts_client.assume_role(
                RoleArn=self._settings.role_arn,
                RoleSessionName=f"{connection.application_name}-{now.strftime('%Y%m%d%H%M%S')}",
                DurationSeconds=3600,
            )
            self._credentials = response["Credentials"]
            expiry = self._credentials["Expiration"]
            self._credentials_expiry = (
                expiry if expiry.tzinfo else expiry.replace(tzinfo=timezone.utc)
            )
            self._runtime_client.client = None
            return self._credentials
