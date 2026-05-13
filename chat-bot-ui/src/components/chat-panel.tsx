"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Bot,
  ChevronsLeft,
  ChevronsRight,
  MessageSquarePlus,
  PanelLeft,
  SendHorizontal,
  Trash2,
  User,
  X,
} from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";
import {
  formatRagClientError,
  parseAskSuccessResponse,
  type AskSuccessResponse,
  type Citation,
} from "@/lib/rag-api-types";
import { cn } from "@/lib/utils";

type ChatMessage =
  | {
      id: string;
      role: "user";
      content: string;
    }
  | {
      id: string;
      role: "assistant";
      content: string;
      citations: Citation[];
      usedContextCount: number;
      provider: string;
    }
  | {
      id: string;
      role: "assistant";
      error: true;
      content: string;
    };

type ChatSession = {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  messages: ChatMessage[];
  draftInput: string;
};

type AdvancedAskOptions = {
  metadataText: string;
  topK: string;
  scoreThreshold: string;
};

type AskPayload = {
  question: string;
  metadata?: Record<string, unknown>;
  topK?: number;
  scoreThreshold?: number;
};

const DEFAULT_ADVANCED_ASK_OPTIONS: AdvancedAskOptions = {
  metadataText: "{}",
  topK: "6",
  scoreThreshold: "0.8",
};

function newId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;
}

function createSession(): ChatSession {
  const now = Date.now();
  return {
    id: newId(),
    title: "New chat",
    createdAt: now,
    updatedAt: now,
    messages: [],
    draftInput: "",
  };
}

function titleFromFirstQuestion(q: string): string {
  const t = q.trim().replace(/\s+/g, " ");
  if (!t) return "New chat";
  return t.length > 44 ? `${t.slice(0, 44)}…` : t;
}

const SIDEBAR_COLLAPSED_KEY = "rag-pgvector-chat:sidebar-collapsed";

function sessionInitialLetter(title: string): string {
  const t = title.trim();
  if (!t) return "?";
  return t[0]?.toUpperCase() ?? "?";
}

function parseAdvancedAskOptions(
  question: string,
  options: AdvancedAskOptions
): { payload: AskPayload; error: string | null } {
  const payload: AskPayload = { question };
  const metadataText = options.metadataText.trim();
  const topKText = options.topK.trim();
  const scoreThresholdText = options.scoreThreshold.trim();

  if (metadataText) {
    try {
      const parsed = JSON.parse(metadataText) as unknown;
      if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
        return { payload, error: "Metadata must be a JSON object, for example {\"packageId\":\"BILLS-115hr1625enr\"}." };
      }
      payload.metadata = parsed as Record<string, unknown>;
    } catch {
      return { payload, error: "Metadata must be valid JSON." };
    }
  }

  if (topKText) {
    const topK = Number(topKText);
    if (!Number.isInteger(topK) || topK < 1 || topK > 50) {
      return { payload, error: "Top K must be a whole number from 1 through 50." };
    }
    payload.topK = topK;
  }

  if (scoreThresholdText) {
    const scoreThreshold = Number(scoreThresholdText);
    if (!Number.isFinite(scoreThreshold) || scoreThreshold < 0) {
      return { payload, error: "Score threshold must be a number greater than or equal to 0." };
    }
    payload.scoreThreshold = scoreThreshold;
  }

  return { payload, error: null };
}

export function ChatPanel() {
  const initial = useMemo(() => {
    const s = createSession();
    return { sessions: [s] as ChatSession[], activeId: s.id };
  }, []);

  const [sessions, setSessions] = useState<ChatSession[]>(initial.sessions);
  const [activeId, setActiveId] = useState(initial.activeId);
  const [pending, setPending] = useState(false);
  const [requestError, setRequestError] = useState<string | null>(null);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [advancedOptions, setAdvancedOptions] = useState<AdvancedAskOptions>({
    ...DEFAULT_ADVANCED_ASK_OPTIONS,
  });
  const latestMessageRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    try {
      if (localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "1") {
        setSidebarCollapsed(true);
      }
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(SIDEBAR_COLLAPSED_KEY, sidebarCollapsed ? "1" : "0");
    } catch {
      /* ignore */
    }
  }, [sidebarCollapsed]);

  const activeSession = sessions.find((s) => s.id === activeId);
  const messages = activeSession?.messages ?? [];
  const input = activeSession?.draftInput ?? "";

  const latestMessageId = messages.at(-1)?.id;

  useEffect(() => {
    latestMessageRef.current?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  }, [latestMessageId, activeId, pending]);

  const setDraftForActive = useCallback(
    (value: string) => {
      setSessions((prev) =>
        prev.map((s) => (s.id === activeId ? { ...s, draftInput: value } : s))
      );
    },
    [activeId]
  );

  const createNewSession = useCallback(() => {
    const s = createSession();
    setSessions((prev) => [s, ...prev]);
    setActiveId(s.id);
    setRequestError(null);
    setMobileSidebarOpen(false);
  }, []);

  const expandSidebar = useCallback(() => {
    setSidebarCollapsed(false);
  }, []);

  const selectSession = useCallback((id: string) => {
    setActiveId(id);
    setRequestError(null);
    setMobileSidebarOpen(false);
  }, []);

  const deleteSession = useCallback(
    (id: string) => {
      setRequestError(null);
      const filtered = sessions.filter((s) => s.id !== id);
      if (filtered.length === 0) {
        const fresh = createSession();
        setSessions([fresh]);
        setActiveId(fresh.id);
        return;
      }
      setSessions(filtered);
      if (id === activeId) {
        const idx = sessions.findIndex((s) => s.id === id);
        const pick = filtered[Math.max(0, idx - 1)] ?? filtered[0];
        setActiveId(pick.id);
      }
    },
    [sessions, activeId]
  );

  const clearConversation = useCallback(() => {
    setSessions((prev) =>
      prev.map((s) =>
        s.id !== activeId
          ? s
          : {
              ...s,
              messages: [],
              draftInput: "",
              title: "New chat",
              updatedAt: Date.now(),
            }
      )
    );
    setRequestError(null);
  }, [activeId]);

  const clearAdvancedOptions = useCallback(() => {
    setAdvancedOptions({ metadataText: "", topK: "", scoreThreshold: "" });
    setRequestError(null);
  }, []);

  const send = async () => {
    const trimmed = input.trim();
    if (!trimmed || pending) return;

    const sessionId = activeId;
    const { payload, error } = parseAdvancedAskOptions(trimmed, advancedOptions);

    if (error) {
      setRequestError(error);
      return;
    }

    setRequestError(null);
    setAdvancedOpen(false);
    const userMsg: ChatMessage = { id: newId(), role: "user", content: trimmed };
    setSessions((prev) =>
      prev.map((s) => {
        if (s.id !== sessionId) return s;
        const nextTitle =
          s.title === "New chat" ? titleFromFirstQuestion(trimmed) : s.title;
        return {
          ...s,
          title: nextTitle,
          draftInput: "",
          updatedAt: Date.now(),
          messages: [...s.messages, userMsg],
        };
      })
    );
    setPending(true);

    const appendAssistant = (msg: ChatMessage) => {
      setSessions((prev) =>
        prev.map((s) =>
          s.id !== sessionId
            ? s
            : { ...s, messages: [...s.messages, msg], updatedAt: Date.now() }
        )
      );
    };

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(payload),
      });

      let json: unknown;
      try {
        json = await res.json();
      } catch {
        appendAssistant({
          id: newId(),
          role: "assistant",
          error: true,
          content: "Response was not valid JSON.",
        });
        setRequestError("Response was not valid JSON.");
        return;
      }

      if (!res.ok) {
        const msg = formatRagClientError(json);
        setRequestError(msg);
        appendAssistant({
          id: newId(),
          role: "assistant",
          error: true,
          content: msg,
        });
        return;
      }

      const parsed = parseAskSuccessResponse(json);
      if (!parsed) {
        const fallback =
          "question-api returned JSON that does not match the expected AskResponse shape (answer, citations, usedContextCount, provider).";
        setRequestError(fallback);
        appendAssistant({
          id: newId(),
          role: "assistant",
          error: true,
          content: `${fallback}\n\nRaw: ${JSON.stringify(json).slice(0, 800)}`,
        });
        return;
      }

      appendAssistant(successToMessage(parsed));
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setRequestError(msg);
      appendAssistant({
        id: newId(),
        role: "assistant",
        error: true,
        content: msg,
      });
    } finally {
      setPending(false);
    }
  };

  const showExpandedSidebar = mobileSidebarOpen || !sidebarCollapsed;

  return (
    <div className="relative flex h-[100dvh] overflow-hidden bg-gradient-to-b from-background via-background to-muted/25 text-foreground">
      {mobileSidebarOpen ? (
        <button
          type="button"
          className="fixed inset-0 z-30 bg-black/40 backdrop-blur-[1px] md:hidden"
          aria-label="Close session list"
          onClick={() => setMobileSidebarOpen(false)}
        />
      ) : null}

      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex shrink-0 flex-col border-sidebar-border border-r bg-sidebar text-sidebar-foreground shadow-xl transition-[transform,width,min-width] duration-200 ease-out",
          "w-[min(280px,92vw)]",
          mobileSidebarOpen ? "translate-x-0" : "-translate-x-full",
          "md:static md:z-0 md:translate-x-0 md:shadow-none",
          sidebarCollapsed ? "md:w-[56px] md:min-w-[56px] md:max-w-[56px]" : "md:w-[272px] md:min-w-[272px] md:max-w-[272px]"
        )}
        aria-label="Chat sessions"
      >
        {showExpandedSidebar ? (
          <div className="flex h-full min-h-0 w-full flex-col">
            <div className="flex shrink-0 items-center justify-between gap-2 border-sidebar-border border-b px-3 py-2.5">
              <div className="min-w-0">
                <p className="truncate font-semibold text-sidebar-foreground text-sm tracking-tight">
                  Chats
                </p>
                <p className="hidden text-[10px] text-sidebar-foreground/60 leading-tight md:line-clamp-1 md:block">
                  Sessions for this tab only
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-1">
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  className="hidden text-sidebar-foreground md:inline-flex"
                  aria-label="Collapse sidebar"
                  title="Collapse sidebar"
                  onClick={() => setSidebarCollapsed(true)}
                >
                  <ChevronsLeft className="size-4" aria-hidden />
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  className="text-sidebar-foreground md:hidden"
                  aria-label="Close session list"
                  onClick={() => setMobileSidebarOpen(false)}
                >
                  <X className="size-4" aria-hidden />
                </Button>
              </div>
            </div>

            <div className="flex shrink-0 flex-col gap-2 border-sidebar-border border-b p-3">
              <Button
                type="button"
                className="w-full justify-start gap-2 rounded-lg bg-sidebar-primary text-sidebar-primary-foreground shadow-sm hover:bg-sidebar-primary/90"
                onClick={createNewSession}
                disabled={pending}
              >
                <MessageSquarePlus className="size-4 shrink-0" aria-hidden />
                New chat
              </Button>
              <p className="text-sidebar-foreground/70 px-0.5 text-xs leading-snug">
                In-tab only. Each turn calls{" "}
                <code className="rounded-md bg-sidebar-accent px-1 py-px text-[10px] text-sidebar-accent-foreground">
                  POST /ask
                </code>{" "}
                with the current question.
              </p>
            </div>

            <ScrollArea className="min-h-0 flex-1">
              <nav className="flex flex-col gap-1 p-2" aria-label="Chat sessions list">
                {sessions.map((s) => {
                  const isActive = s.id === activeId;
                  return (
                    <div
                      key={s.id}
                      className={cn(
                        "group flex items-stretch gap-0.5 rounded-xl border border-transparent transition-colors",
                        isActive &&
                          "border-sidebar-ring/35 bg-sidebar-accent/90 shadow-sm"
                      )}
                    >
                      <button
                        type="button"
                        onClick={() => selectSession(s.id)}
                        className={cn(
                          "min-w-0 flex-1 rounded-l-xl px-3 py-2.5 text-left text-sm transition-colors",
                          isActive
                            ? "text-sidebar-accent-foreground"
                            : "text-sidebar-foreground hover:bg-sidebar-accent/50"
                        )}
                      >
                        <span className="line-clamp-2 font-medium leading-snug">{s.title}</span>
                        <span className="mt-0.5 block text-[11px] text-sidebar-foreground/55">
                          {s.messages.length} message{s.messages.length === 1 ? "" : "s"}
                        </span>
                      </button>
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon-xs"
                        className="shrink-0 self-center text-sidebar-foreground/45 opacity-0 transition-opacity hover:bg-destructive/15 hover:text-destructive group-hover:opacity-100 md:opacity-100"
                        aria-label={`Delete ${s.title}`}
                        onClick={(e) => {
                          e.stopPropagation();
                          deleteSession(s.id);
                        }}
                      >
                        <X className="size-3.5" />
                      </Button>
                    </div>
                  );
                })}
              </nav>
            </ScrollArea>
          </div>
        ) : (
          <div className="hidden h-full min-h-0 w-full flex-col items-center gap-2 border-sidebar-border border-transparent py-3 md:flex">
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              className="text-sidebar-foreground hover:bg-sidebar-accent"
              aria-label="Expand sidebar"
              title="Expand sidebar"
              onClick={expandSidebar}
            >
              <ChevronsRight className="size-4" aria-hidden />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              className="text-sidebar-primary hover:bg-sidebar-accent"
              aria-label="New chat"
              title="New chat"
              onClick={createNewSession}
              disabled={pending}
            >
              <MessageSquarePlus className="size-4" aria-hidden />
            </Button>
            <Separator className="my-1 w-8 bg-sidebar-border" />
            <ScrollArea className="min-h-0 w-full flex-1 px-1">
              <div className="flex flex-col items-center gap-1.5 pb-2" role="list">
                {sessions.map((s) => {
                  const isActive = s.id === activeId;
                  return (
                    <button
                      key={s.id}
                      type="button"
                      role="listitem"
                      title={s.title}
                      aria-label={s.title}
                      aria-current={isActive ? "true" : undefined}
                      onClick={() => selectSession(s.id)}
                      className={cn(
                        "flex size-10 shrink-0 items-center justify-center rounded-xl border border-transparent transition-all outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring",
                        isActive
                          ? "border-sidebar-ring/40 bg-sidebar-primary text-sidebar-primary-foreground shadow-md"
                          : "bg-sidebar-accent/50 text-sidebar-accent-foreground hover:bg-sidebar-accent"
                      )}
                    >
                      <span className="font-semibold text-xs leading-none">
                        {sessionInitialLetter(s.title)}
                      </span>
                    </button>
                  );
                })}
              </div>
            </ScrollArea>
          </div>
        )}
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex shrink-0 items-center justify-between gap-3 border-border/60 border-b bg-card/40 px-3 py-3 backdrop-blur-sm md:px-4">
          <div className="flex min-w-0 items-center gap-2">
            <Button
              type="button"
              variant="outline"
              size="icon-sm"
              className="shrink-0 md:hidden"
              aria-label="Open sessions"
              onClick={() => setMobileSidebarOpen(true)}
            >
              <PanelLeft className="size-4" />
            </Button>
            <Button
              type="button"
              variant="outline"
              size="icon-sm"
              className={cn("hidden shrink-0", sidebarCollapsed ? "md:inline-flex" : "md:hidden")}
              aria-label="Expand sidebar"
              title="Expand sidebar"
              onClick={expandSidebar}
            >
              <PanelLeft className="size-4" aria-hidden />
            </Button>
            <div className="min-w-0">
              <h1 className="truncate text-lg font-semibold tracking-tight text-foreground">
                RAG chat
              </h1>
              <p className="text-muted-foreground text-xs">
                <span className="font-medium text-primary">Active:</span>{" "}
                <span className="truncate">{activeSession?.title ?? "—"}</span>
              </p>
            </div>
          </div>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={clearConversation}
            disabled={pending}
          >
            <Trash2 className="mr-2 size-4" aria-hidden />
            Clear
          </Button>
        </header>

        {requestError ? (
          <div className="shrink-0 px-3 pt-3 md:px-4">
            <Alert variant="destructive" className="border-destructive/40 shadow-sm">
              <AlertTitle>Request failed</AlertTitle>
              <AlertDescription className="whitespace-pre-wrap break-words">
                {requestError}
              </AlertDescription>
            </Alert>
          </div>
        ) : null}

        <div className="flex min-h-0 flex-1 flex-col overflow-hidden px-3 py-4 md:px-4">
          <ScrollArea className="min-h-0 flex-1">
            <div className="mx-auto flex max-w-3xl flex-col gap-4 pb-32">
              {messages.length === 0 && !pending ? (
                <Card className="border-primary/20 bg-gradient-to-br from-primary/6 via-card to-muted/40 shadow-sm">
                  <CardContent className="space-y-2 pt-6 text-center text-muted-foreground text-sm">
                    <p>
                      Ask a question. Answers use{" "}
                      <span className="font-semibold text-foreground">rag-pgvector</span> when
                      question-api is up at{" "}
                      <code className="rounded-md bg-muted px-1.5 py-0.5 text-foreground text-xs">
                        RAG_QUESTION_API_URL
                      </code>
                      .
                    </p>
                    <p className="text-xs">
                      <span className="text-primary font-medium">Tip:</span> start a{" "}
                      <span className="font-medium text-secondary-foreground">New chat</span> for a
                      fresh thread (still client-only).
                    </p>
                  </CardContent>
                </Card>
              ) : null}

              {messages.map((m) => (
                <div
                  key={m.id}
                  ref={m.id === latestMessageId ? latestMessageRef : undefined}
                  className="scroll-mt-4"
                >
                  <MessageRow message={m} />
                </div>
              ))}

              {pending ? <AssistantThinkingLoader /> : null}
            </div>
          </ScrollArea>
        </div>

        <div className="shrink-0 border-border/60 border-t bg-card/50 p-3 backdrop-blur-md supports-[backdrop-filter]:bg-card/40 md:p-4">
          <div className="mx-auto flex max-w-3xl flex-col gap-2">
            <Textarea
              placeholder="Message…"
              value={input}
              onChange={(e) => setDraftForActive(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void send();
                }
              }}
              rows={3}
              disabled={pending}
              className="min-h-[80px] resize-none border-input/80 shadow-sm focus-visible:border-primary/50 focus-visible:ring-primary/25"
              aria-label="Chat message"
            />
            <details
              open={advancedOpen}
              onToggle={(e) => setAdvancedOpen(e.currentTarget.open)}
              className="rounded-xl border border-border/70 bg-background/70 px-3 py-2 text-sm shadow-sm"
            >
              <summary className="cursor-pointer select-none font-medium text-foreground">
                Advanced options
                <span className="ml-2 font-normal text-muted-foreground text-xs">
                  metadata, topK, scoreThreshold
                </span>
              </summary>
              <p className="mt-2 text-muted-foreground text-xs">
                Defaults match <code>scripts/ps/Ask.ps1</code>. Clear a field to omit it.
              </p>
              <div className="mt-3 grid gap-3 md:grid-cols-[1fr_8rem_10rem]">
                <label className="flex flex-col gap-1 text-xs font-medium text-foreground">
                  Metadata JSON
                  <textarea
                    value={advancedOptions.metadataText}
                    onChange={(e) =>
                      setAdvancedOptions((prev) => ({
                        ...prev,
                        metadataText: e.target.value,
                      }))
                    }
                    placeholder="{}"
                    rows={3}
                    disabled={pending}
                    className="min-h-20 resize-y rounded-md border border-input bg-background px-3 py-2 font-mono text-xs font-normal shadow-sm outline-none transition-colors placeholder:text-muted-foreground focus-visible:border-primary/50 focus-visible:ring-2 focus-visible:ring-primary/25"
                  />
                </label>
                <label className="flex flex-col gap-1 text-xs font-medium text-foreground">
                  Top K
                  <input
                    type="number"
                    min={1}
                    max={50}
                    step={1}
                    value={advancedOptions.topK}
                    onChange={(e) =>
                      setAdvancedOptions((prev) => ({ ...prev, topK: e.target.value }))
                    }
                    placeholder="Backend default"
                    disabled={pending}
                    className="rounded-md border border-input bg-background px-3 py-2 font-normal shadow-sm outline-none transition-colors placeholder:text-muted-foreground focus-visible:border-primary/50 focus-visible:ring-2 focus-visible:ring-primary/25"
                  />
                </label>
                <label className="flex flex-col gap-1 text-xs font-medium text-foreground">
                  Score threshold
                  <input
                    type="number"
                    min={0}
                    step="0.01"
                    value={advancedOptions.scoreThreshold}
                    onChange={(e) =>
                      setAdvancedOptions((prev) => ({
                        ...prev,
                        scoreThreshold: e.target.value,
                      }))
                    }
                    placeholder="Backend default"
                    disabled={pending}
                    className="rounded-md border border-input bg-background px-3 py-2 font-normal shadow-sm outline-none transition-colors placeholder:text-muted-foreground focus-visible:border-primary/50 focus-visible:ring-2 focus-visible:ring-primary/25"
                  />
                </label>
              </div>
              <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-muted-foreground text-xs">
                <span>Blank fields are omitted from the request.</span>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={clearAdvancedOptions}
                  disabled={pending}
                >
                  Clear options
                </Button>
              </div>
            </details>
            <div className="flex justify-end">
              <Button
                type="button"
                onClick={() => void send()}
                disabled={pending || !input.trim()}
                className="shadow-md"
              >
                <SendHorizontal className="mr-2 size-4" aria-hidden />
                Send
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function AssistantThinkingLoader() {
  return (
    <div
      className="flex gap-3"
      role="status"
      aria-live="polite"
      aria-busy="true"
      aria-label="Assistant is generating a response"
    >
      <Avatar className="size-9 shrink-0 ring-2 ring-primary/35 animate-ai-glow">
        <AvatarFallback className="bg-gradient-to-br from-primary to-primary/75 text-primary-foreground shadow-md">
          <Bot className="size-4" aria-hidden />
        </AvatarFallback>
      </Avatar>

      <Card className="relative max-w-[85%] flex-1 overflow-hidden border-primary/30 bg-gradient-to-br from-card via-card to-muted/40 shadow-md">
        <div
          className="pointer-events-none absolute inset-y-0 -left-[40%] w-[45%] skew-x-[-12deg] bg-gradient-to-r from-transparent via-primary/40 to-transparent animate-ai-sweep"
          aria-hidden
        />
        <div
          className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_30%_0%,var(--primary)_0%,transparent_55%)] opacity-[0.12] animate-ai-glow"
          aria-hidden
        />

        <CardContent className="relative space-y-4 pt-4 pb-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
              Generating
            </span>
            <span className="flex items-center gap-1.5" aria-hidden>
              <span className="size-1.5 rounded-full bg-primary ring-2 ring-primary/45 animate-ai-dot" />
              <span className="size-1.5 rounded-full bg-primary/70 ring-2 ring-primary/35 animate-ai-dot [animation-delay:160ms]" />
              <span className="size-1.5 rounded-full bg-primary/45 ring-2 ring-primary/30 animate-ai-dot [animation-delay:320ms]" />
            </span>
          </div>

          <div className="space-y-2.5">
            <div className="h-2 overflow-hidden rounded-full bg-muted/80">
              <div className="h-full w-[55%] rounded-full bg-gradient-to-r from-primary/55 via-primary/75 to-primary/55 animate-pulse" />
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-muted/80">
              <div className="h-full w-[82%] rounded-full bg-gradient-to-r from-primary/40 via-primary/65 to-primary/45 animate-pulse [animation-delay:180ms]" />
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-muted/80">
              <div className="h-full w-[48%] rounded-full bg-gradient-to-r from-primary/35 via-primary/55 to-primary/40 animate-pulse [animation-delay:360ms]" />
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function successToMessage(data: AskSuccessResponse): ChatMessage {
  return {
    id: newId(),
    role: "assistant",
    content: data.answer,
    citations: data.citations,
    usedContextCount: data.usedContextCount,
    provider: data.provider,
  };
}

function MessageRow({ message: m }: { message: ChatMessage }) {
  const isUser = m.role === "user";
  const isErr = m.role === "assistant" && "error" in m && m.error;

  return (
    <div className={cn("flex gap-3", isUser ? "flex-row-reverse" : "")}>
      <Avatar className="size-9 shrink-0 ring-2 ring-background">
        <AvatarFallback
          className={cn(
            isUser
              ? "bg-gradient-to-br from-primary to-primary/80 text-primary-foreground shadow-sm"
              : "bg-gradient-to-br from-muted to-primary/15 text-foreground"
          )}
        >
          {isUser ? <User className="size-4" /> : <Bot className="size-4" />}
        </AvatarFallback>
      </Avatar>

      <Card
        className={cn(
          "max-w-[85%] flex-1 shadow-sm transition-shadow",
          isUser &&
            "border-primary/20 bg-gradient-to-br from-primary to-primary/90 text-primary-foreground",
          !isUser &&
            !isErr &&
            "border-border/70 border-l-4 border-l-primary/45 bg-card text-card-foreground",
          isErr && "border-destructive/40 bg-destructive/10"
        )}
      >
        <CardContent className="space-y-3 pt-4 text-sm leading-relaxed">
          <p className="whitespace-pre-wrap break-words">{m.content}</p>

          {m.role === "assistant" && !("error" in m) ? (
            <>
              <Separator className="bg-border/80" />
              <p className="text-muted-foreground text-xs">
                <span className="text-primary font-medium">Provider:</span>{" "}
                <span className="font-medium text-foreground">{m.provider}</span>
                {" · "}
                <span className="text-primary font-medium">Context:</span>{" "}
                <span className="font-medium text-foreground">{m.usedContextCount}</span>
              </p>
              {m.citations.length > 0 ? (
                <details className="rounded-md border border-border/60 bg-muted/30 text-xs">
                  <summary className="cursor-pointer px-2 py-2 font-medium text-primary hover:underline">
                    Citations ({m.citations.length})
                  </summary>
                  <ul className="space-y-2 border-border/50 border-t px-2 py-2">
                    {m.citations.map((c, i) => (
                      <li
                        key={`${c.packageId}-${i}`}
                        className="text-muted-foreground"
                      >
                        <div className="font-mono text-[11px] text-foreground">{c.packageId}</div>
                        {c.pageNumber != null ? <div>Page {c.pageNumber}</div> : null}
                        <div>score (distance): {c.score.toFixed(4)}</div>
                        <a
                          href={c.sourceUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-primary underline-offset-2 hover:underline"
                        >
                          Source
                        </a>
                        <p className="mt-1 text-foreground/90">{c.snippet}</p>
                      </li>
                    ))}
                  </ul>
                </details>
              ) : null}
            </>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
