/**
 * Types aligned with rag-pgvector question-api
 * {@link https://github.com/David-Parry/rag-pgvector question_api/domain/models.py}
 *
 * FastAPI serializes AskResponse with aliases (camelCase) when using
 * response_model_by_alias=True on the route.
 */

export type Citation = {
  packageId: string;
  sourceUrl: string;
  pageNumber: number | null;
  score: number;
  snippet: string;
};

/** Successful `POST /ask` JSON body */
export type AskSuccessResponse = {
  answer: string;
  citations: Citation[];
  usedContextCount: number;
  provider: string;
};

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function parseCitation(v: unknown): Citation | null {
  if (!isRecord(v)) return null;
  const packageId = v.packageId;
  const sourceUrl = v.sourceUrl;
  const snippet = v.snippet;
  const score = v.score;
  if (typeof packageId !== "string" || typeof sourceUrl !== "string") return null;
  if (typeof snippet !== "string" || typeof score !== "number" || Number.isNaN(score)) return null;
  let pageNumber: number | null = null;
  if (v.pageNumber !== undefined && v.pageNumber !== null) {
    if (typeof v.pageNumber !== "number" || Number.isNaN(v.pageNumber)) return null;
    pageNumber = v.pageNumber;
  }
  return { packageId, sourceUrl, pageNumber, score, snippet };
}

/**
 * Validates a JSON value matches AskSuccessResponse enough for safe UI rendering.
 */
export function parseAskSuccessResponse(data: unknown): AskSuccessResponse | null {
  if (!isRecord(data)) return null;
  if (typeof data.answer !== "string") return null;
  if (!Array.isArray(data.citations)) return null;
  const citations: Citation[] = [];
  for (const item of data.citations) {
    const c = parseCitation(item);
    if (!c) return null;
    citations.push(c);
  }
  if (typeof data.usedContextCount !== "number" || Number.isNaN(data.usedContextCount)) return null;
  if (typeof data.provider !== "string") return null;
  return {
    answer: data.answer,
    citations,
    usedContextCount: data.usedContextCount,
    provider: data.provider,
  };
}

/** FastAPI 422 `detail` entry */
type ValidationErr = { loc?: unknown[]; msg?: string; type?: string };

function formatValidationDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (!Array.isArray(detail)) return JSON.stringify(detail);
  return detail
    .map((item) => {
      if (!isRecord(item)) return JSON.stringify(item);
      const ve = item as ValidationErr;
      const loc = Array.isArray(ve.loc) ? ve.loc.join(".") : "";
      const msg = typeof ve.msg === "string" ? ve.msg : JSON.stringify(item);
      return loc ? `${loc}: ${msg}` : msg;
    })
    .join("; ");
}

/**
 * Human-readable message from our BFF error payload or raw FastAPI JSON.
 */
export function formatRagClientError(payload: unknown): string {
  if (payload === null || payload === undefined) return "Unknown error";
  if (typeof payload === "string") return payload;
  if (!isRecord(payload)) return String(payload);

  // Next.js BFF wraps upstream: { error, status, body }
  if (payload.body !== undefined && typeof payload.error === "string") {
    const status =
      typeof payload.status === "number" ? ` [HTTP ${payload.status}]` : "";
    const inner = formatRagClientError(payload.body);
    return `${payload.error}${status}: ${inner}`;
  }

  if (typeof payload.error === "string") {
    const base = payload.error;
    if (payload.detail !== undefined && typeof payload.detail === "string") {
      return `${base}: ${payload.detail}`;
    }
    return base;
  }

  if (payload.detail !== undefined) {
    return formatValidationDetail(payload.detail);
  }

  if (typeof payload.message === "string") return payload.message;
  return JSON.stringify(payload);
}
