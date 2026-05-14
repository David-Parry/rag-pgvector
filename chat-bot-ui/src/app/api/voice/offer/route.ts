import { NextRequest, NextResponse } from "next/server";

import { questionApiBaseUrl } from "@/lib/question-api-url";

async function readJson(req: NextRequest): Promise<unknown> {
  try {
    return await req.json();
  } catch {
    return {};
  }
}

async function proxyVoiceOffer(req: NextRequest, method: "POST" | "PATCH") {
  const payload = await readJson(req);
  const target = `${questionApiBaseUrl()}/voice/api/offer`;
  let res: Response;
  try {
    res = await fetch(target, {
      method,
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(payload),
      cache: "no-store",
    });
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return NextResponse.json(
      { error: "Failed to reach question-api voice offer endpoint", detail, target },
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

export async function POST(req: NextRequest) {
  return proxyVoiceOffer(req, "POST");
}

export async function PATCH(req: NextRequest) {
  return proxyVoiceOffer(req, "PATCH");
}
