# question-api Voice Deployment

`question-api` can host an optional Pipecat Small WebRTC voice runtime that uses AWS Bedrock Nova Sonic for realtime voice input, finalized user transcripts, and spoken responses.

## Runtime Behavior

- Browser audio connects through `POST /voice/start`, `POST /voice/api/offer`, and `PATCH /voice/api/offer`.
- Nova Sonic provides finalized user transcript text.
- Finalized user and assistant transcript turns are available to browser clients through `GET /voice/transcripts/{sessionId}` as server-sent events.
- The transcript is sent to `AskService.ask()` as the `AskRequest.question`.
- The existing LangGraph flow handles Redis checkpointing, Titan query embeddings, pgvector retrieval, Anthropic grounded answer generation, and citations.
- Nova Sonic speaks the grounded `AskResponse.answer`. It is not the source of project knowledge.

## Required Configuration

Set these values through the same environment path used by the `question-api` pod:

| Variable | Required | Description |
|----------|----------|-------------|
| `VOICE_ENABLED` | Yes | Set to `true` to allow `/voice/start` and voice bot startup. Helm local deployment values default this to `true`; set it to `false` only when intentionally disabling voice. |
| `BEDROCK_NOVA_SONIC_MODEL_ID` | No | Defaults to `amazon.nova-2-sonic-v1:0`. `NOVA_SONIC_MODEL` remains accepted as a fallback. |
| `NOVA_SONIC_VOICE` | No | Defaults to `matthew`. |
| `NOVA_SONIC_ENDPOINTING_SENSITIVITY` | No | Defaults to `MEDIUM`. |
| `NOVA_SONIC_SYSTEM_INSTRUCTION` | No | Optional override for the grounded voice instruction. |
| `AWS_REGION` | Yes | Bedrock region for Titan embeddings and Nova Sonic. |
| `SONIC_AWS_ROLE_ARN` | No | Role ARN associated with the Nova Sonic STS credentials; retained for traceability. |
| `SONIC_AWS_ACCESS_KEY_ID` | When using Nova Sonic-specific access-key auth | AWS access key passed to Pipecat's `AWSNovaSonicLLMService`. |
| `SONIC_AWS_SECRET_ACCESS_KEY` | When using Nova Sonic-specific access-key auth | AWS secret key passed to Pipecat's `AWSNovaSonicLLMService`. |
| `SONIC_AWS_SESSION_TOKEN` | For temporary Nova Sonic credentials | AWS session token passed to Pipecat's `AWSNovaSonicLLMService`. |
| `SONIC_AWS_CREDENTIAL_EXPIRATION` | No | Expiration timestamp for operational checks; it is not sent to Bedrock. |
| `CORS_ALLOW_ORIGINS` | No | Comma-separated frontend origins allowed to call voice endpoints directly. Defaults include local Next dev ports `3000` and `3001`. |

Nova Sonic calls prefer the `SONIC_AWS_*` credentials. If those are not provided, the code falls back to the generic `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and `AWS_SESSION_TOKEN` credentials used elsewhere in the service.

## Helm Notes

For Docker Desktop or local Helm installs, set voice values under `qa.env`:

```yaml
qa:
  env:
    VOICE_ENABLED: "true"
    NOVA_SONIC_VOICE: matthew
    NOVA_SONIC_ENDPOINTING_SENSITIVITY: MEDIUM

novaSonic:
  modelId: amazon.nova-sonic-v1:0
  roleArn: "REPLACE_WITH_SONIC_AWS_ROLE_ARN"
  accessKeyId: "REPLACE_WITH_SONIC_AWS_ACCESS_KEY_ID"
  secretAccessKey: "REPLACE_WITH_SONIC_AWS_SECRET_ACCESS_KEY"
  sessionToken: "REPLACE_WITH_SONIC_AWS_SESSION_TOKEN"
  credentialExpiration: "REPLACE_WITH_SONIC_AWS_CREDENTIAL_EXPIRATION"
```

Credential values should remain in the chart secret path through `aws.auth` or another approved secret mechanism. Do not commit credential values.

## Manual Verification

1. Start `question-api` with `VOICE_ENABLED=true`, valid Bedrock credentials, Redis, pgvector, and Anthropic credentials.
2. Call `POST /voice/start` and keep the returned `sessionId`.
3. Connect a Small WebRTC browser client to `POST /voice/api/offer` and include `request_data.sessionId`.
4. Speak a question covered by the indexed corpus.
5. Confirm logs include `voice.user_transcript_finalized` with the final transcript.
6. Subscribe to `GET /voice/transcripts/{sessionId}` and confirm a `transcript` event is emitted for the finalized user turn.
7. Confirm the existing RAG logs show vector retrieval for that transcript.
8. Confirm the spoken response matches the grounded answer returned by `AskService.ask()`.
9. Confirm assistant transcript logs and stream events include `voice.assistant_transcript_finalized`.
