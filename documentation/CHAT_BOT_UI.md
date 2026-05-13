# Chat Bot UI Integration

`chat-bot-ui` is a Next.js chat interface for the `question-api` service. The browser posts to the local Next.js route `POST /api/chat`; that route forwards requests to `POST /ask` on `question-api`.

## Local Development

Start Kubernetes port forwarding from the repository root:

```powershell
.\scripts\ps\Port-Forward.ps1
```

By default, the script forwards `question-api` to `http://localhost:8002`. The UI route defaults to `http://127.0.0.1:8002`, so no additional environment variable is required for the default local setup.

If the backend is running elsewhere, set `RAG_QUESTION_API_URL` before starting the UI:

```powershell
$env:RAG_QUESTION_API_URL = "http://127.0.0.1:8002"
cd .\chat-bot-ui
npm run dev
```

Open `http://localhost:3000`.

## Request Parameters

The composer includes a collapsible Advanced options panel. The default values match `scripts/ps/Ask.ps1`, so the UI sends the same retrieval settings unless a user edits them. Blank fields are omitted from the request.

| UI field | Backend field | Notes |
| --- | --- | --- |
| Metadata JSON | `metadata` | Defaults to `{}`. Must be a JSON object, for example `{"packageId":"BILLS-115hr1625enr"}`. |
| Top K | `topK` | Defaults to `6`. Optional integer from 1 through 50. |
| Score threshold | `scoreThreshold` | Defaults to `0.8`. Optional numeric cosine-distance threshold. Lower values are stricter. |

The resulting request is sent to `POST /api/chat` and proxied to `POST /ask`.
