"use client";

import { useCallback, useEffect, useState } from "react";
import { Headphones, Loader2, Mic, ShieldCheck, ShieldX } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

type PermissionUiState = "unknown" | "prompt" | "granted" | "denied" | "unsupported" | "checking";

type VoiceMediaPermissionPromptProps = {
  className?: string;
  disabled?: boolean;
  onReadyChange?: (ready: boolean) => void;
};

type AudioOutputMediaDevices = MediaDevices & {
  selectAudioOutput?: () => Promise<MediaDeviceInfo>;
};

type AudioOutputNavigator = Navigator & {
  mediaDevices?: AudioOutputMediaDevices;
};

function permissionLabel(state: PermissionUiState): string {
  switch (state) {
    case "granted":
      return "ready";
    case "denied":
      return "blocked";
    case "unsupported":
      return "browser default";
    case "checking":
      return "checking";
    case "prompt":
      return "needs approval";
    case "unknown":
      return "not checked";
  }
}

function isReady(microphone: PermissionUiState, speaker: PermissionUiState): boolean {
  return microphone === "granted" && speaker !== "denied";
}

async function queryPermission(name: PermissionName): Promise<PermissionUiState> {
  if (!navigator.permissions?.query) {
    return "unknown";
  }

  try {
    const status = await navigator.permissions.query({ name });
    return status.state;
  } catch {
    return "unsupported";
  }
}

export function VoiceMediaPermissionPrompt({
  className,
  disabled = false,
  onReadyChange,
}: VoiceMediaPermissionPromptProps) {
  const [microphone, setMicrophone] = useState<PermissionUiState>("unknown");
  const [speaker, setSpeaker] = useState<PermissionUiState>("unknown");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;

    async function checkPermissions() {
      setMicrophone("checking");
      setSpeaker("checking");

      const [microphoneState, speakerState] = await Promise.all([
        queryPermission("microphone" as PermissionName),
        queryPermission("speaker-selection" as PermissionName),
      ]);

      if (!mounted) return;
      setMicrophone(microphoneState);
      setSpeaker(speakerState);
      onReadyChange?.(isReady(microphoneState, speakerState));
    }

    void checkPermissions();
    return () => {
      mounted = false;
    };
  }, [onReadyChange]);

  const requestPermissions = useCallback(async () => {
    setError(null);
    setMicrophone("checking");
    setSpeaker("checking");

    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        setMicrophone("unsupported");
        throw new Error("This browser does not support microphone capture.");
      }

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach((track) => track.stop());
      setMicrophone("granted");

      const mediaDevices = (navigator as AudioOutputNavigator).mediaDevices;
      if (mediaDevices?.selectAudioOutput) {
        try {
          await mediaDevices.selectAudioOutput();
          setSpeaker("granted");
          onReadyChange?.(true);
        } catch (err) {
          setSpeaker("denied");
          onReadyChange?.(false);
          throw err;
        }
      } else {
        setSpeaker("unsupported");
        onReadyChange?.(true);
      }
    } catch (err) {
      const detail = err instanceof Error ? err.message : String(err);
      if (detail.toLowerCase().includes("permission") || detail.toLowerCase().includes("denied")) {
        setMicrophone((current) => (current === "checking" ? "denied" : current));
      }
      setError(detail);
    }
  }, [onReadyChange]);

  const ready = isReady(microphone, speaker);

  return (
    <div
      className={cn(
        "rounded-lg border border-border bg-background/80 p-2.5 text-xs shadow-sm",
        ready && "border-primary/30 bg-primary/5",
        (microphone === "denied" || speaker === "denied") && "border-destructive/40 bg-destructive/10",
        className
      )}
    >
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-start gap-2">
          {ready ? (
            <ShieldCheck className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden />
          ) : microphone === "denied" || speaker === "denied" ? (
            <ShieldX className="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden />
          ) : (
            <Mic className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
          )}
          <div className="min-w-0">
            <p className="font-medium text-foreground">Voice permissions</p>
            <p className="text-muted-foreground leading-snug">
              Allow microphone input and browser audio output before starting Nova Sonic voice chat.
            </p>
          </div>
        </div>

        <Button
          type="button"
          variant={ready ? "secondary" : "outline"}
          size="sm"
          onClick={() => void requestPermissions()}
          disabled={disabled || microphone === "checking" || speaker === "checking"}
          aria-label="Enable microphone and speaker permissions"
        >
          {microphone === "checking" || speaker === "checking" ? (
            <Loader2 className="mr-2 size-3.5 animate-spin" aria-hidden />
          ) : (
            <Headphones className="mr-2 size-3.5" aria-hidden />
          )}
          {ready ? "Permissions ready" : "Enable mic and speaker"}
        </Button>
      </div>

      <div className="mt-2 flex flex-wrap gap-1.5 text-[11px] text-muted-foreground">
        <span className="rounded-md bg-muted px-1.5 py-0.5">Mic: {permissionLabel(microphone)}</span>
        <span className="rounded-md bg-muted px-1.5 py-0.5">Speaker: {permissionLabel(speaker)}</span>
      </div>

      {error ? <p className="mt-2 text-destructive leading-snug">{error}</p> : null}
    </div>
  );
}
