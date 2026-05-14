"use client";

import { useEffect } from "react";

type GlobalErrorPageProps = {
  error: Error & { digest?: string };
  reset: () => void;
};

export default function GlobalErrorPage({ error, reset }: GlobalErrorPageProps) {
  useEffect(() => {
    console.error("chat-bot-ui global error", error);
  }, [error]);

  return (
    <html lang="en">
      <body>
        <main
          style={{
            alignItems: "center",
            background: "#09090b",
            color: "#fafafa",
            display: "flex",
            fontFamily: "system-ui, sans-serif",
            justifyContent: "center",
            minHeight: "100vh",
            padding: "24px",
          }}
        >
          <section
            style={{
              border: "1px solid rgba(248, 113, 113, 0.45)",
              borderRadius: "16px",
              maxWidth: "640px",
              padding: "24px",
            }}
          >
            <h1 style={{ fontSize: "20px", margin: "0 0 12px" }}>Chat UI failed to load</h1>
            <p style={{ color: "#d4d4d8", lineHeight: 1.5, margin: "0 0 16px" }}>
              The application hit a root rendering error. Restart the development server if this
              continues after retrying.
            </p>
            <pre
              style={{
                background: "rgba(255, 255, 255, 0.06)",
                borderRadius: "10px",
                overflowX: "auto",
                padding: "12px",
                whiteSpace: "pre-wrap",
              }}
            >
              {error.message}
            </pre>
            <button
              type="button"
              onClick={reset}
              style={{
                background: "#fafafa",
                border: 0,
                borderRadius: "8px",
                color: "#09090b",
                cursor: "pointer",
                fontWeight: 600,
                marginTop: "16px",
                padding: "8px 12px",
              }}
            >
              Try again
            </button>
          </section>
        </main>
      </body>
    </html>
  );
}
