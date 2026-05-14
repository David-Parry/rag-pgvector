This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

## Backend configuration

Set `RAG_QUESTION_API_URL` to the server-side `question-api` base URL used by
Next API proxy routes. Set `NEXT_PUBLIC_RAG_QUESTION_API_URL` to the browser-side
base URL used by WebRTC voice calls; local development defaults to
`http://localhost:8000`.

Text chat is proxied to `POST /ask`. Voice chat calls the Pipecat Small WebRTC
endpoints directly from the browser:

- `POST /voice/start`
- `POST /voice/api/offer`
- `PATCH /voice/api/offer`

Voice chat uses the active chat session UUID so the backend can keep the same
LangGraph/Redis thread semantics as text chat. The browser sends microphone
audio over WebRTC and plays Nova Sonic's streamed audio response from the remote
track.

Before starting a voice session, use the voice permissions prompt in the chat
composer to allow microphone capture and confirm browser audio output readiness.
If a voice proxy route or backend endpoint returns HTML instead of JSON, the UI
surfaces the HTTP status and response excerpt instead of a generic JSON parse
error.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.
