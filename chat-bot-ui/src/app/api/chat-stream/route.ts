import { NextRequest } from "next/server";
import { createUIMessageStream, createUIMessageStreamResponse } from "ai";
import { randomUUID } from "node:crypto";

const DEFAULT_RAG_BASE = "http://127.0.0.1:8002";

function normalizeBase(url: string): string {
  return url.replace(/\/+$/, "");
}

type UIMessagePartLike = { type: string; text?: string };
type UIMessageLike = { role?: string; parts?: UIMessagePartLike[] };

function lastUserText(messages: UIMessageLike[]): string | null {
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    if (m?.role !== "user") continue;
    const text = (m.parts ?? [])
      .filter((p) => p.type === "text" && typeof p.text === "string")
      .map((p) => p.text as string)
      .join("");
    if (text.trim().length > 0) return text;
  }
  return null;
}

export async function POST(req: NextRequest) {
  let body: { messages?: UIMessageLike[]; id?: string };
  try {
    body = await req.json();
  } catch {
    return new Response(JSON.stringify({ error: "Invalid JSON body" }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    });
  }

  const question = lastUserText(body.messages ?? []);
  if (!question) {
    return new Response(JSON.stringify({ error: "No user message found" }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    });
  }

  const base = normalizeBase(
    process.env.RAG_QUESTION_API_URL?.trim() || DEFAULT_RAG_BASE
  );
  const sessionId = typeof body.id === "string" && body.id ? body.id : randomUUID();

  const stream = createUIMessageStream({
    execute: async ({ writer }) => {
      let ragJson: unknown;
      try {
        const res = await fetch(`${base}/ask`, {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify({ question, sessionId }),
          cache: "no-store",
        });
        ragJson = await res.json();
        if (!res.ok) {
          const msg =
            (ragJson as { error?: string } | null)?.error ??
            `question-api returned HTTP ${res.status}`;
          writer.write({ type: "error", errorText: msg });
          return;
        }
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        writer.write({ type: "error", errorText: `Failed to reach question-api: ${msg}` });
        return;
      }

      const data = ragJson as {
        answer?: string;
        citations?: unknown[];
        usedContextCount?: number;
        provider?: string;
        fromRedisSessionCache?: boolean;
      };
      const answer = typeof data.answer === "string" ? data.answer : "";
      const textId = randomUUID();

      writer.write({ type: "text-start", id: textId });
      // Pseudo-stream the precomputed answer in small chunks so the client sees
      // progressive rendering even though the backend returns it whole.
      const CHUNK = 24;
      for (let i = 0; i < answer.length; i += CHUNK) {
        writer.write({
          type: "text-delta",
          id: textId,
          delta: answer.slice(i, i + CHUNK),
        });
        // Yield to event loop so each delta flushes
        await new Promise((r) => setTimeout(r, 8));
      }
      writer.write({ type: "text-end", id: textId });

      // Emit citations + provider as a custom data part so the client can render
      // them alongside the streamed text.
      writer.write({
        type: "data-rag",
        id: randomUUID(),
        data: {
          citations: data.citations ?? [],
          usedContextCount: data.usedContextCount ?? 0,
          provider: data.provider ?? "unknown",
          fromRedisSessionCache:
            typeof data.fromRedisSessionCache === "boolean"
              ? data.fromRedisSessionCache
              : false,
        },
      });
    },
    onError: (err) => (err instanceof Error ? err.message : String(err)),
  });

  return createUIMessageStreamResponse({ stream });
}
