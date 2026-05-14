# LangGraph session checkpoints (question-api)

## Purpose

The `question-api` service uses **LangGraph** with a **Redis** checkpointer to persist per-session graph state for each chat tab. The client sends a UUID **`sessionId`** on every `POST /ask`; the server uses it as LangGraph **`thread_id`**.

## State channels

- **`messages`**: LangChain chat messages (`HumanMessage` / `AIMessage`) with stable ids. Each successful `/ask` appends one user message and one assistant message.
- **`aca_truth_turns`**: Append-only list of ACA snapshots for that turn, including `turn_id`, `user_message_id`, `assistant_message_id`, and serialized citations (post-threshold retrieval used for grounding).

## Redis

- Connection: **`LANGGRAPH_REDIS_URL`** or **`REDIS_URL`**.
- The Helm chart installs **Redis Stack** by default and points `question-api` at **`redis://rag-redis-stack:6379`** unless you override `qa.env.LANGGRAPH_REDIS_URL`.
- Redis must expose **RedisJSON** and **RediSearch** (Redis 8+ includes both; older deployments use **Redis Stack**).
- TTL: **`SESSION_CHECKPOINT_TTL_DAYS`** (default `5`) with optional **`SESSION_CHECKPOINT_TTL_REFRESH_ON_READ`** (default `true`). Values map to `langgraph-checkpoint-redis` `ttl` options (`default_ttl` is in **minutes** internally).

## Client contract

- Next.js BFF and `chat-bot-ui` send `sessionId` with each chat request.
- Shell helper `scripts/ask.sh` sets `SESSION_ID` automatically when `uuidgen` or `python3` is available.

## Observability

- **`question_api.langgraph_session_memory`** (startup): `session_memory_backend=redis`, `session_memory_endpoint` (host:port, no password), `checkpointer_cls=AsyncRedisSaver`.
- **`GET /healthz`**: when the app has finished startup, includes **`sessionMemory`**: `{ "backend": "redis", "checkpointer": "AsyncRedisSaver", "redisEndpoint": "host:port" }` (no credentials). Confirms the process is wired to Redis for session checkpoints before you send chat traffic.
- **`ask.langgraph_checkpoint_read`** / **`ask.langgraph_checkpoint_write`**: include bound `session_memory_backend`, `session_memory_endpoint`, and **`session_memory_serves_context`** (`true` when backend is `redis`). `prior_message_count` increasing across turns with the same `sessionId` indicates prior turns were read from the checkpointer before merging the new message.
- **`ask_graph.session_messages_for_context`**: emitted at the start of the graph node after LangGraph merges checkpoint state with the new `HumanMessage`; includes `merged_message_count` and `merged_aca_truth_turn_count`. Bound fields `session_memory_backend` / `session_memory_endpoint` identify Redis vs in-memory test graphs.
- **`ask_graph.duplicate_consecutive_question`**: emitted when the current user message duplicates the immediately prior user message in the merged state; flags `skip_pgvector_similarity_search` and `skip_llm_generate` as `true`. LangGraph still persists this turn to the checkpointer.

## Duplicate consecutive question

If the user sends the **same natural-language question twice in a row** in one `sessionId`, the graph **does not call** the vector store similarity search or the LLM again; it returns the previous assistant text and reuses the prior turn's citation list. This is only for **consecutive** repeats (not the same question alternating with other turns). Whitespace and letter case are normalized for the comparison. Duplicate detection compares the merged `messages` tail using **message roles** (`human` / `ai`) so it still works when Redis checkpoint serde restores prior rows as plain dicts rather than LangChain class instances. **JsonPlus** checkpoints often use the **`lc` + `constructor`** envelope (`type` at the root is `"constructor"`, with class name in `id` and text in `kwargs`); the graph normalizes that shape as well. The **`POST /ask`** response sets **`fromRedisSessionCache`: `true`** (camelCase in JSON) for that turn so clients can show a session-cache indicator.

## Inspecting Redis (messages and state)

Chat turns are **not** stored as a plain Redis `LIST` of strings. `langgraph-checkpoint-redis` stores **checkpoint JSON documents** (and related `checkpoint_blob:*` / `checkpoint_write:*` keys) keyed roughly as:

`checkpoint:<thread_id>:<checkpoint_ns>:<checkpoint_id>`

Your client **`sessionId` (UUID string)** is LangGraph **`thread_id`**, so it appears as the second segment of `checkpoint:*` keys (after any storage-safe encoding, a normal UUID usually matches literally).

### redis-cli

Use the same URL as **`LANGGRAPH_REDIS_URL`** or **`REDIS_URL`** (for example `redis://127.0.0.1:6379`).

1. List keys for one session (prefer `SCAN` over `KEYS` outside dev):

   ```text
   redis-cli -u redis://127.0.0.1:6379
   SCAN 0 MATCH checkpoint:*YOUR-SESSION-UUID* COUNT 200
   ```

2. Inspect a checkpoint document (keys are **RedisJSON** in typical setups). Use a key returned from `SCAN`:

   ```text
   JSON.GET "<paste-key-here>"
   ```

   Search inside the returned JSON for channel data related to **`messages`** (exact nesting depends on library version; large message bodies may be split across **`checkpoint_blob:*`** keys referenced from the checkpoint).

3. Optional **RediSearch** index (created by the saver) is often named **`checkpoints`**. You can query by `thread_id` if your server supports `FT.SEARCH`:

   ```text
   FT.SEARCH checkpoints "@thread_id:{YOUR-SESSION-UUID}"
   ```

### RedisInsight

Connect to the same host/port (or URL), open **Browser**, filter by prefix `checkpoint:`, then open a key and use the JSON viewer. Search for `messages` or `content` inside the payload.

### From application code

The most reliable view of **`messages`** is the same object LangGraph uses: call **`aget_state`** on the compiled graph with `{"configurable": {"thread_id": "<sessionId>"}}` and read `snapshot.values["messages"]` (see `question-api` tests under `test_ask_graph_sessions.py`). That avoids depending on internal Redis document layout.

## Verifying Redis backs merged context

1. Call **`GET /healthz`** after startup and confirm **`sessionMemory.backend`** is **`redis`** and **`redisEndpoint`** matches your deployment.
2. Send two **`POST /ask`** requests with the same **`sessionId`** and different questions. In logs, the second request should show **`prior_message_count`** (or **`merged_message_count`** on `ask_graph.session_messages_for_context`) **greater than** the first, proving prior messages were loaded from the checkpointer when building the merged message list for the graph node.
3. Cross-check in Redis using the **Inspecting Redis** section above (`checkpoint:*` keys for that `sessionId`).
