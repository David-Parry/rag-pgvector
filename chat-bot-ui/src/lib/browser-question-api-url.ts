const DEFAULT_BROWSER_RAG_BASE = "http://localhost:8000";

export function browserQuestionApiBaseUrl(): string {
  return (
    process.env.NEXT_PUBLIC_RAG_QUESTION_API_URL?.trim() || DEFAULT_BROWSER_RAG_BASE
  ).replace(/\/+$/, "");
}

export function browserQuestionApiUrl(path: string): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${browserQuestionApiBaseUrl()}${normalizedPath}`;
}
