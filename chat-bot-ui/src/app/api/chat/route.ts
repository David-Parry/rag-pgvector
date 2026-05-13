import { NextRequest, NextResponse } from "next/server";

const DEFAULT_RAG_BASE = "http://127.0.0.1:8002";

function normalizeBase(url: string): string {
  return url.replace(/\/+$/, "");
}

type ClientBody = {
  question?: unknown;
  metadata?: unknown;
  topK?: unknown;
  scoreThreshold?: unknown;
};

export async function POST(req: NextRequest) {
  let raw: unknown;
  try {
    raw = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    return NextResponse.json({ error: "Expected a JSON object" }, { status: 400 });
  }

  const body = raw as ClientBody;
  const question = body.question;
  if (typeof question !== "string" || question.trim().length === 0) {
    return NextResponse.json(
      { error: "question is required and must be a non-empty string" },
      { status: 400 }
    );
  }

  const base = normalizeBase(
    process.env.RAG_QUESTION_API_URL?.trim() || DEFAULT_RAG_BASE
  );

  const upstreamPayload: Record<string, unknown> = { question: question.trim() };
  if (body.metadata !== undefined && body.metadata !== null) {
    if (typeof body.metadata !== "object" || Array.isArray(body.metadata)) {
      return NextResponse.json(
        { error: "metadata must be a JSON object when provided" },
        { status: 400 }
      );
    }
    upstreamPayload.metadata = body.metadata;
  }
  if (body.topK !== undefined && body.topK !== null) {
    if (typeof body.topK !== "number" || !Number.isInteger(body.topK)) {
      return NextResponse.json({ error: "topK must be an integer" }, { status: 400 });
    }
    upstreamPayload.topK = body.topK;
  }
  if (body.scoreThreshold !== undefined && body.scoreThreshold !== null) {
    if (typeof body.scoreThreshold !== "number" || Number.isNaN(body.scoreThreshold)) {
      return NextResponse.json(
        { error: "scoreThreshold must be a number" },
        { status: 400 }
      );
    }
    upstreamPayload.scoreThreshold = body.scoreThreshold;
  }

  let res: Response;
  try {
    res = await fetch(`${base}/ask`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(upstreamPayload),
      cache: "no-store",
    });
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return NextResponse.json(
      {
        error: "Failed to reach question-api",
        detail,
        target: `${base}/ask`,
      },
      { status: 503 }
    );
  }

  const text = await res.text();
  let parsed: unknown = null;
  if (text.length > 0) {
    try {
      parsed = JSON.parse(text) as unknown;
    } catch {
      parsed = { raw: text.slice(0, 2000) };
    }
  }

  if (!res.ok) {
    return NextResponse.json(
      {
        error: "question-api returned an error",
        status: res.status,
        body: parsed,
      },
      { status: res.status >= 400 && res.status < 600 ? res.status : 502 }
    );
  }

  return NextResponse.json(parsed ?? {});
}
