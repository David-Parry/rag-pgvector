# question-api

Project 2 of the rag-pgvector monorepo. A FastAPI pod that answers strictly-grounded questions over the data loaded by `vectorizer`.

## Endpoints

- `POST /ask` — body: `{ "question": "...", "sessionId": "<uuid>", "metadata": {...}, "topK": 5, "scoreThreshold": 0.25 }`. Returns `{ "answer": "...", "citations": [...], "usedContextCount": n, "provider": "...", "fromRedisSessionCache": false }`. The `sessionId` is the per-chat client GUID and is used as LangGraph `thread_id` for Redis checkpointing. **`fromRedisSessionCache`** is **`true`** only when this turn reused the prior assistant answer and citations from session checkpoint without a new pgvector search or LLM call (consecutive duplicate user question).
- `GET /healthz` — liveness probe; after startup includes `sessionMemory` (`backend`, `checkpointer`, `redisEndpoint` without credentials) so you can confirm the pod uses Redis for LangGraph session checkpoints.
- `POST /voice/start` — creates or accepts a voice `sessionId` and optional `{ "metadata": {...}, "topK": 5, "scoreThreshold": 0.25 }` defaults for the voice session.
- `POST /voice/api/offer` — Small WebRTC offer endpoint for the Pipecat voice runtime. The browser request should include `request_data.sessionId` from `/voice/start`.
- `PATCH /voice/api/offer` — Small WebRTC ICE candidate patch endpoint.

## Voice path (Pipecat + Nova Sonic)

Set `VOICE_ENABLED=true` to enable the realtime voice path. The voice bot uses Pipecat Small WebRTC for browser audio and AWS Bedrock Nova Sonic for realtime speech input, finalized transcripts, and spoken output. Final user transcripts are passed into the existing `AskService.ask()` flow, so vectorization, pgvector retrieval, Redis checkpointing, grounded Anthropic generation, and citations remain the same as `POST /ask`.

Voice configuration:

| Variable | Default | Purpose |
|----------|---------|---------|
| `VOICE_ENABLED` | `false` in the app, `true` in Helm local deployment values | Enables `/voice/start` and `/voice/api/offer` bot startup. |
| `BEDROCK_NOVA_SONIC_MODEL_ID` | `amazon.nova-2-sonic-v1:0` | Bedrock Nova Sonic model id. `NOVA_SONIC_MODEL` is still accepted as a fallback. |
| `NOVA_SONIC_VOICE` | `matthew` | Nova Sonic output voice. |
| `NOVA_SONIC_ENDPOINTING_SENSITIVITY` | `MEDIUM` | Nova Sonic turn endpointing sensitivity. |
| `NOVA_SONIC_SYSTEM_INSTRUCTION` | grounded RAG voice instruction | Optional system instruction override. |
| `AWS_REGION` | `us-east-1` | Bedrock region used for embeddings and Nova Sonic. |
| `SONIC_AWS_ROLE_ARN` | unset | Role ARN associated with the Nova Sonic STS credentials; retained for traceability. |
| `SONIC_AWS_ACCESS_KEY_ID`, `SONIC_AWS_SECRET_ACCESS_KEY`, `SONIC_AWS_SESSION_TOKEN` | unset | Preferred credential set for Nova Sonic calls. If unset, the generic `AWS_*` credentials are used as a fallback. |
| `SONIC_AWS_CREDENTIAL_EXPIRATION` | unset | Expiration timestamp for the Nova Sonic STS credentials; useful for operational checks. |
| `CORS_ALLOW_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001` | Comma-separated browser origins allowed to call the voice WebRTC endpoints directly. |

## Session checkpointing (LangGraph + Redis)

- Configure **`LANGGRAPH_REDIS_URL`** or **`REDIS_URL`** (default `redis://127.0.0.1:6379`). Redis must provide **RedisJSON** and **RediSearch** (Redis 8+ or Redis Stack).
- **`SESSION_CHECKPOINT_TTL_DAYS`** (default `5`) maps to the checkpointer `default_ttl` (minutes) for key expiry.
- **`SESSION_CHECKPOINT_TTL_REFRESH_ON_READ`** (default `true`) refreshes TTL on read when supported by the saver.

## LLM provider

The service uses direct Anthropic Claude API calls. Configure `ANTHROPIC_API_KEY`
or `ANTHROPIC_API_KEY_FILE`, and optionally `ANTHROPIC_DIRECT_MODEL`.
