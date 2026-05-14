"use client";

import { useState } from "react";
import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport, type UIMessage } from "ai";
import { Bot, SendHorizontal, User } from "lucide-react";
import Link from "next/link";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

type RagDataPart = {
  citations: Array<{
    packageId?: string;
    pageNumber?: number | null;
    score?: number;
    sourceUrl?: string;
    snippet?: string;
  }>;
  usedContextCount: number;
  provider: string;
  fromRedisSessionCache?: boolean;
};

function isRagDataPart(part: UIMessage["parts"][number]): part is UIMessage["parts"][number] & {
  type: "data-rag";
  data: RagDataPart;
} {
  return part.type === "data-rag";
}

export default function ChatSdkDemoPage() {
  const [input, setInput] = useState("");
  const { messages, sendMessage, status, error } = useChat({
    transport: new DefaultChatTransport({ api: "/api/chat-stream" }),
  });

  const submit = () => {
    const text = input.trim();
    if (!text || status === "streaming" || status === "submitted") return;
    sendMessage({ text });
    setInput("");
  };

  return (
    <div className="flex h-[100dvh] flex-col bg-background text-foreground">
      <header className="relative z-20 flex shrink-0 items-center justify-between gap-3 border-border/60 border-b bg-card/40 px-4 py-3 backdrop-blur-sm">
        <div className="min-w-0">
          <h1 className="truncate text-lg font-semibold tracking-tight">
            Chat SDK demo
          </h1>
          <p className="text-muted-foreground text-xs">
            <span className="font-medium text-primary">useChat</span> + streaming{" "}
            <code className="rounded bg-muted px-1 py-0.5 text-[11px]">/api/chat-stream</code>{" "}
            wrapping rag-pgvector
          </p>
        </div>
        <Link
          href="/"
          className="text-primary text-xs underline-offset-2 hover:underline"
        >
          ← back to ChatPanel
        </Link>
      </header>

      <div className="flex min-h-0 flex-1 flex-col overflow-hidden px-4 py-4">
        <ScrollArea className="min-h-0 flex-1">
          <div className="mx-auto flex max-w-3xl flex-col gap-4 pb-24">
            {messages.length === 0 ? (
              <Card className="border-primary/20 bg-gradient-to-br from-primary/10 via-card to-muted/40">
                <CardContent className="space-y-2 pt-6 text-center text-muted-foreground text-sm">
                  <p>
                    Side-by-side demo using{" "}
                    <span className="font-semibold text-foreground">
                      @ai-sdk/react
                    </span>{" "}
                    <code className="rounded bg-muted px-1 py-0.5 text-[11px]">
                      useChat
                    </code>{" "}
                    + a streaming route that wraps the existing RAG{" "}
                    <code className="rounded bg-muted px-1 py-0.5 text-[11px]">
                      /ask
                    </code>{" "}
                    backend.
                  </p>
                  <p className="text-xs">
                    Citations stream as a typed{" "}
                    <code className="rounded bg-muted px-1 py-0.5 text-[11px]">
                      data-rag
                    </code>{" "}
                    part.
                  </p>
                </CardContent>
              </Card>
            ) : null}

            {messages.map((m) => {
              const isUser = m.role === "user";
              const text = m.parts
                .filter((p) => p.type === "text")
                .map((p) => (p as { text: string }).text)
                .join("");
              const ragPart = m.parts.find(isRagDataPart);

              return (
                <div
                  key={m.id}
                  className={cn("flex gap-3", isUser && "flex-row-reverse")}
                >
                  <Avatar className="size-9 shrink-0 ring-2 ring-background">
                    <AvatarFallback
                      className={cn(
                        isUser
                          ? "bg-gradient-to-br from-primary to-primary/80 text-primary-foreground"
                          : "bg-muted text-foreground"
                      )}
                    >
                      {isUser ? <User className="size-4" /> : <Bot className="size-4" />}
                    </AvatarFallback>
                  </Avatar>
                  <Card
                    className={cn(
                      "max-w-[85%] flex-1",
                      isUser
                        ? "border-primary/20 bg-gradient-to-br from-primary to-primary/90 text-primary-foreground"
                        : "border-border/70 border-l-4 border-l-primary/40 bg-card"
                    )}
                  >
                    <CardContent className="space-y-3 pt-4 text-sm leading-relaxed">
                      <p className="whitespace-pre-wrap break-words">{text}</p>

                      {ragPart ? (
                        <div className="space-y-2 border-t border-border/60 pt-3 text-xs text-muted-foreground">
                          <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
                            <p>
                              <span className="font-medium text-primary">Provider:</span>{" "}
                              <span className="font-medium text-foreground">
                                {ragPart.data.provider}
                              </span>
                              {" · "}
                              <span className="font-medium text-primary">Context:</span>{" "}
                              <span className="font-medium text-foreground">
                                {ragPart.data.usedContextCount}
                              </span>
                            </p>
                            {ragPart.data.fromRedisSessionCache ? (
                              <span
                                className="inline-flex items-center rounded-md border border-amber-500/40 bg-amber-500/10 px-2 py-0.5 font-medium text-amber-950 dark:text-amber-100"
                                title="Answer and citations were reused from this chat session in Redis; no new similarity search or LLM call for this turn."
                              >
                                Session cache (Redis)
                              </span>
                            ) : null}
                          </div>
                          {ragPart.data.citations.length > 0 ? (
                            <details>
                              <summary className="cursor-pointer font-medium text-primary hover:underline">
                                Citations ({ragPart.data.citations.length})
                              </summary>
                              <ul className="mt-2 space-y-2">
                                {ragPart.data.citations.map((c, i) => (
                                  <li
                                    key={i}
                                    className="rounded-md bg-muted/40 p-2"
                                  >
                                    {c.packageId ? (
                                      <div className="font-mono text-[11px] text-foreground">
                                        {c.packageId}
                                      </div>
                                    ) : null}
                                    {c.pageNumber != null ? (
                                      <div>Page {c.pageNumber}</div>
                                    ) : null}
                                    {typeof c.score === "number" ? (
                                      <div>score: {c.score.toFixed(4)}</div>
                                    ) : null}
                                    {c.sourceUrl ? (
                                      <a
                                        href={c.sourceUrl}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="text-primary hover:underline"
                                      >
                                        Source
                                      </a>
                                    ) : null}
                                    {c.snippet ? (
                                      <p className="mt-1 text-foreground/90">
                                        {c.snippet}
                                      </p>
                                    ) : null}
                                  </li>
                                ))}
                              </ul>
                            </details>
                          ) : null}
                        </div>
                      ) : null}
                    </CardContent>
                  </Card>
                </div>
              );
            })}

            {status === "submitted" ? (
              <p className="text-center text-muted-foreground text-xs">
                Calling RAG backend…
              </p>
            ) : null}

            {error ? (
              <Card className="border-destructive/40 bg-destructive/10">
                <CardContent className="pt-4 text-destructive text-sm">
                  {error.message}
                </CardContent>
              </Card>
            ) : null}
          </div>
        </ScrollArea>
      </div>

      <div className="shrink-0 border-border/60 border-t bg-card/50 p-4 backdrop-blur-md">
        <div className="mx-auto flex max-w-3xl flex-col gap-2">
          <Textarea
            value={input}
            placeholder="Message…"
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
            rows={3}
            disabled={status === "streaming" || status === "submitted"}
            className="min-h-[80px] resize-none"
            aria-label="Chat message"
          />
          <div className="flex justify-end">
            <Button
              type="button"
              onClick={submit}
              disabled={
                status === "streaming" ||
                status === "submitted" ||
                !input.trim()
              }
            >
              <SendHorizontal className="mr-2 size-4" aria-hidden />
              Send
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
