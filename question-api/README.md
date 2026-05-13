# question-api

Project 2 of the rag-pgvector monorepo. A FastAPI pod that answers strictly-grounded questions over the data loaded by `vectorizer`.

## Endpoints

- `POST /ask` — body: `{ "question": "...", "sessionId": "<uuid>", "metadata": {...}, "topK": 5, "scoreThreshold": 0.25 }`. Returns `{ "answer": "...", "citations": [...], "usedContextCount": n, "provider": "...", "fromRedisSessionCache": false }`. The `sessionId` is the per-chat client GUID and is used as LangGraph `thread_id` for Redis checkpointing. **`fromRedisSessionCache`** is **`true`** only when this turn reused the prior assistant answer and citations from session checkpoint without a new pgvector search or LLM call (consecutive duplicate user question).
- `GET /healthz` — liveness probe; after startup includes `sessionMemory` (`backend`, `checkpointer`, `redisEndpoint` without credentials) so you can confirm the pod uses Redis for LangGraph session checkpoints.

## Session checkpointing (LangGraph + Redis)

- Configure **`LANGGRAPH_REDIS_URL`** or **`REDIS_URL`** (default `redis://127.0.0.1:6379`). Redis must provide **RedisJSON** and **RediSearch** (Redis 8+ or Redis Stack).
- **`SESSION_CHECKPOINT_TTL_DAYS`** (default `5`) maps to the checkpointer `default_ttl` (minutes) for key expiry.
- **`SESSION_CHECKPOINT_TTL_REFRESH_ON_READ`** (default `true`) refreshes TTL on read when supported by the saver.

## LLM provider

The service uses direct Anthropic Claude API calls. Configure `ANTHROPIC_API_KEY`
or `ANTHROPIC_API_KEY_FILE`, and optionally `ANTHROPIC_DIRECT_MODEL`.
