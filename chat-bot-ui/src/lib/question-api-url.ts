const DEFAULT_RAG_BASE = "http://127.0.0.1:8000";

export function questionApiBaseUrl(): string {
  return (process.env.RAG_QUESTION_API_URL?.trim() || DEFAULT_RAG_BASE).replace(/\/+$/, "");
}
