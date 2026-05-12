# Bedrock STS Secret Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Connect `EMBEDDING_MODEL` and `ANTHROPIC_MODEL` to AWS Bedrock using the same Secrets Manager + STS-assumed-role pattern as `spectrum-notes-agent`.

**Architecture:** Add shared Bedrock connection settings to `rag-core`, including secret loading and cached STS credentials. Replace the direct Anthropic adapter with a Bedrock Claude adapter, and update both embedding adapters to use the approved model IDs and runtime credentials from the Bedrock secret. Update Helm and docs so deployments provide `BEDROCK_CONNECTION_SECRET_NAME` and `BEDROCK_ROLE_ARN` instead of direct Anthropic keys.

**Tech Stack:** Python 3.12, Pydantic Settings, boto3/botocore, FastAPI service composition, Helm.

---

**Revision:** Embeddings intentionally remain on the previous direct Bedrock credential path because Amazon Titan is not enabled in the ACA account. The ACA Secrets Manager + STS path applies to Anthropic Claude generation only.

### Task 1: Shared Bedrock Settings And Client Support

**Files:**
- Modify: `libs/rag-core/src/rag_core/settings.py`
- Test: `libs/rag-core/tests/test_settings.py`

**Steps:**
1. Add `BEDROCK_CONNECTION_SECRET_NAME`, `BEDROCK_ROLE_ARN`, optional local override aliases, generation defaults, and a `BedrockConnectionSettings` value object.
2. Add parsing for Secrets Manager JSON keys used by the reference project: `Region`, `ModelId`, `EmbeddingModelId`, `MaxTokens`, `Temperature`, `ApplicationName`, and `TimeoutSeconds`.
3. Add tests for secret parsing and env aliases.

### Task 2: Bedrock Runtime Adapter

**Files:**
- Create: `libs/rag-core/src/rag_core/bedrock.py`
- Test: `libs/rag-core/tests/test_bedrock.py`

**Steps:**
1. Add a small runtime provider that loads the secret once, assumes `BEDROCK_ROLE_ARN`, caches temporary credentials, and builds `bedrock-runtime` clients.
2. Expose `get_connection()`, `get_runtime_client()`, and credential env helpers for LangChain Bedrock embeddings.
3. Unit test secret loading, STS role assumption, runtime client construction, and env mirroring without real AWS calls.

### Task 3: Question API Bedrock Claude

**Files:**
- Create: `question-api/src/question_api/adapters/bedrock_llm.py`
- Modify: `question-api/src/question_api/core/composition.py`
- Modify: `question-api/src/question_api/core/settings.py`
- Test: `question-api/tests/test_bedrock_llm.py`

**Steps:**
1. Implement an async `LLMPort` adapter using Bedrock `converse`.
2. Set provider name to `bedrock` for the AWS path while preserving `ollama` as a local alternative.
3. Test request shape and content extraction.

### Task 4: Embeddings Use Approved Bedrock Secret

**Files:**
- Modify: `question-api/src/question_api/adapters/titan_embeddings.py`
- Modify: `vectorizer/src/vectorizer/adapters/titan_embeddings.py`

**Steps:**
1. Resolve embedding model ID and region from the Bedrock connection secret when configured.
2. Mirror assumed temporary credentials into the process environment before constructing `BedrockEmbeddings`.
3. Preserve existing bearer/IAM env behavior only when no connection secret is configured for local development.

### Task 5: Helm, Docs, And Changelog

**Files:**
- Modify: `infra/helm/rag-pgvector/values.yaml`
- Modify: `infra/helm/rag-pgvector/values-example.yaml`
- Modify: `infra/helm/rag-pgvector/templates/secrets.yaml`
- Modify: `tests/test_helm_chart.py`
- Modify: `.env.example`
- Modify: `README.md`
- Create or modify: `CHANGELOG.md`

**Steps:**
1. Add Helm values for `bedrock.connectionSecretName` and `bedrock.roleArn`.
2. Render `BEDROCK_CONNECTION_SECRET_NAME`, `BEDROCK_ROLE_ARN`, `EMBEDDING_MODEL`, and `ANTHROPIC_MODEL`.
3. Remove required direct Anthropic API key configuration from chart tests and documentation.
4. Add a Keep a Changelog `[Unreleased]` entry.

### Task 6: Validation

**Steps:**
1. Run focused unit tests for settings, Bedrock adapter, question API LLM adapter, and Helm rendering.
2. Run lint for changed Python files when practical.
3. Read lints for edited files and fix introduced diagnostics.
