import { NextRequest, NextResponse } from "next/server";

import { questionApiBaseUrl } from "@/lib/question-api-url";

export async function POST(req: NextRequest) {
  let payload: unknown = {};
  try {
    payload = await req.json();
  } catch {
    payload = {};
  }

  const target = `${questionApiBaseUrl()}/voice/start`;
  let res: Response;
  try {
    res = await fetch(target, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(payload),
      cache: "no-store",
    });
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return NextResponse.json(
      { error: "Failed to reach question-api voice start endpoint", detail, target },
      { status: 503 }
    );
  }

  const text = await res.text();
  let body: unknown = {};
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = { raw: text.slice(0, 2000) };
    }
  }
  return NextResponse.json(body, { status: res.status });
}
