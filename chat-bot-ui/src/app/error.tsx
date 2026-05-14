"use client";

import { useEffect } from "react";
import { AlertTriangle, RotateCcw } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

type ErrorPageProps = {
  error: Error & { digest?: string };
  reset: () => void;
};

export default function ErrorPage({ error, reset }: ErrorPageProps) {
  useEffect(() => {
    console.error("chat-bot-ui route error", error);
  }, [error]);

  return (
    <main className="flex min-h-screen items-center justify-center bg-background p-6 text-foreground">
      <Alert variant="destructive" className="max-w-xl border-destructive/40 shadow-sm">
        <AlertTriangle className="size-4" aria-hidden />
        <AlertTitle>Chat UI failed to render</AlertTitle>
        <AlertDescription className="space-y-3">
          <p>
            The page hit a recoverable client error. Try again after the development server finishes
            recompiling.
          </p>
          <p className="break-words font-mono text-xs">{error.message}</p>
          <Button type="button" variant="outline" size="sm" onClick={reset}>
            <RotateCcw className="mr-2 size-3.5" aria-hidden />
            Try again
          </Button>
        </AlertDescription>
      </Alert>
    </main>
  );
}
