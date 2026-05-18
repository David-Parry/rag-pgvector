"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Hourglass, Loader2, Mic, MicOff, Radio, Send, Volume2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { VoiceMediaPermissionPrompt } from "@/components/ui/voice-media-permission-prompt";
import { browserQuestionApiUrl } from "@/lib/browser-question-api-url";
import { cn } from "@/lib/utils";

type VoiceStatus = "idle" | "connecting" | "connected" | "error";
type VoiceActivityMeterProps = {
  active: boolean;
  stream: MediaStream | null;
};
type AudioContextWindow = Window &
  typeof globalThis & {
    webkitAudioContext?: typeof AudioContext;
  };

type VoiceStartResponse = {
  sessionId?: string;
  iceConfig?: RTCConfiguration;
};

type VoiceOfferResponse = {
  sdp?: string;
  type?: RTCSdpType;
  pc_id?: string;
};

type VoiceTranscriptEvent = {
  id: number;
  sessionId: string;
  role: "user" | "assistant";
  transcript: string;
  timestamp?: string;
  interrupted?: boolean;
};

type VoiceChatControlProps = {
  sessionId: string;
  topK: number;
  scoreThreshold: number;
  disabled?: boolean;
};

function toPatchCandidate(candidate: RTCIceCandidate) {
  return {
    candidate: candidate.candidate,
    sdp_mid: candidate.sdpMid ?? "0",
    sdp_mline_index: candidate.sdpMLineIndex ?? 0,
  };
}

function getErrorDetail(body: unknown): string {
  if (!body || typeof body !== "object") return "";
  const record = body as Record<string, unknown>;
  const parts = [record.error, record.detail, record.raw]
    .filter((value): value is string => typeof value === "string" && value.trim().length > 0)
    .map((value) => value.trim());
  return parts.join(": ");
}

async function readVoiceJson<T>(res: Response, label: string): Promise<T> {
  const contentType = res.headers.get("content-type") ?? "";
  const text = await res.text();
  let body: unknown = {};

  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = { raw: text.slice(0, 500) };
    }
  }

  if (!res.ok) {
    const detail = getErrorDetail(body);
    throw new Error(`${label} failed with HTTP ${res.status}${detail ? `: ${detail}` : ""}`);
  }

  if (text && !contentType.toLowerCase().includes("application/json")) {
    const detail = getErrorDetail(body);
    throw new Error(
      `${label} returned ${contentType || "non-JSON"} instead of JSON${detail ? `: ${detail}` : ""}`
    );
  }

  return body as T;
}

function statusLabel(status: VoiceStatus, muted: boolean): string {
  switch (status) {
    case "connecting":
      return "Connecting voice stream";
    case "connected":
      return muted ? "Generating answer..." : "Voice stream connected";
    case "error":
      return "Voice stream failed";
    case "idle":
      return "Voice stream idle";
  }
}

function parseVoiceTranscriptEvent(raw: string): VoiceTranscriptEvent | null {
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (!parsed || typeof parsed !== "object") return null;

    const record = parsed as Record<string, unknown>;
    if (
      typeof record.id !== "number" ||
      typeof record.sessionId !== "string" ||
      (record.role !== "user" && record.role !== "assistant") ||
      typeof record.transcript !== "string"
    ) {
      return null;
    }

    return {
      id: record.id,
      sessionId: record.sessionId,
      role: record.role,
      transcript: record.transcript,
      timestamp: typeof record.timestamp === "string" ? record.timestamp : undefined,
      interrupted: typeof record.interrupted === "boolean" ? record.interrupted : undefined,
    };
  } catch {
    return null;
  }
}

function VoiceActivityMeter({ active, stream }: VoiceActivityMeterProps) {
  const [level, setLevel] = useState(0);

  useEffect(() => {
    if (!active || !stream) {
      setLevel(0);
      return;
    }

    const AudioContextConstructor = window.AudioContext || (window as AudioContextWindow).webkitAudioContext;
    if (!AudioContextConstructor) return;

    const audioContext = new AudioContextConstructor();
    const analyser = audioContext.createAnalyser();
    analyser.fftSize = 256;

    const source = audioContext.createMediaStreamSource(stream);
    source.connect(analyser);

    const samples = new Uint8Array(analyser.frequencyBinCount);
    let animationFrame = 0;
    let lastUpdate = 0;

    const updateLevel = (timestamp: number) => {
      analyser.getByteTimeDomainData(samples);

      if (timestamp - lastUpdate > 80) {
        let sum = 0;
        for (const sample of samples) {
          const centered = sample - 128;
          sum += centered * centered;
        }
        const rms = Math.sqrt(sum / samples.length) / 128;
        setLevel(Math.min(1, rms * 4));
        lastUpdate = timestamp;
      }

      animationFrame = window.requestAnimationFrame(updateLevel);
    };

    animationFrame = window.requestAnimationFrame(updateLevel);

    return () => {
      window.cancelAnimationFrame(animationFrame);
      source.disconnect();
      void audioContext.close();
    };
  }, [active, stream]);

  const bars = [0.75, 1, 0.6, 0.9, 0.7];

  return (
    <span
      className="inline-flex h-4 items-end gap-0.5 rounded-md bg-primary/10 px-1 py-0.5"
      aria-label={active ? "Microphone input level" : "Microphone input idle"}
      role="meter"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(level * 100)}
    >
      {bars.map((weight, index) => {
        const height = active ? Math.max(3, Math.round((level * weight * 12) + 2)) : 2;
        return (
          <span
            key={weight + index}
            className={cn(
              "w-1 rounded-full bg-primary transition-[height,opacity] duration-100",
              active ? "opacity-90" : "opacity-30"
            )}
            style={{ height }}
            aria-hidden
          />
        );
      })}
    </span>
  );
}

function VoiceTranscriptPanel({
  active,
  transcripts,
  error,
}: {
  active: boolean;
  transcripts: VoiceTranscriptEvent[];
  error: string | null;
}) {
  if (!active && transcripts.length === 0 && !error) return null;

  return (
    <div className="rounded-lg border border-border bg-background/80 p-2.5 text-xs shadow-sm" aria-live="polite">
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <p className="font-medium text-foreground">Voice transcript</p>
        <span className="rounded-md bg-primary/10 px-1.5 py-0.5 text-[11px] text-primary">
          Nova Sonic finalized
        </span>
      </div>

      {transcripts.length > 0 ? (
        <div className="space-y-1.5">
          {transcripts.map((item) => (
            <p key={item.id} className="leading-snug text-muted-foreground">
              <span className="font-medium text-foreground">
                {item.role === "user" ? "You" : "Assistant"}:
              </span>{" "}
              <span>{item.transcript}</span>
            </p>
          ))}
        </div>
      ) : (
        <p className="text-muted-foreground">Listening for finalized speech...</p>
      )}

      {error ? <p className="mt-1.5 text-destructive leading-snug">{error}</p> : null}
    </div>
  );
}

export function VoiceChatControl({
  sessionId,
  topK,
  scoreThreshold,
  disabled = false,
}: VoiceChatControlProps) {
  const [status, setStatus] = useState<VoiceStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [pcId, setPcId] = useState<string | null>(null);
  const [mediaPermissionsReady, setMediaPermissionsReady] = useState(false);
  const [meterStream, setMeterStream] = useState<MediaStream | null>(null);
  const [voiceSessionId, setVoiceSessionId] = useState<string | null>(null);
  const [transcripts, setTranscripts] = useState<VoiceTranscriptEvent[]>([]);
  const [transcriptError, setTranscriptError] = useState<string | null>(null);
  const [muted, setMuted] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const peerRef = useRef<RTCPeerConnection | null>(null);
  const localStreamRef = useRef<MediaStream | null>(null);
  const pendingCandidatesRef = useRef<RTCIceCandidate[]>([]);
  const pcIdRef = useRef<string | null>(null);
  const stoppedRef = useRef(false);

  const stopVoice = useCallback(() => {
    stoppedRef.current = true;
    peerRef.current?.close();
    peerRef.current = null;
    localStreamRef.current?.getTracks().forEach((track) => track.stop());
    localStreamRef.current = null;
    setMeterStream(null);
    setVoiceSessionId(null);
    pendingCandidatesRef.current = [];
    pcIdRef.current = null;
    setPcId(null);
    setStatus("idle");
    setMuted(false);
    if (audioRef.current) {
      audioRef.current.srcObject = null;
    }
  }, []);

  const setMicEnabled = useCallback((enabled: boolean) => {
    const stream = localStreamRef.current;
    if (!stream) return;
    stream.getAudioTracks().forEach((track) => {
      track.enabled = enabled;
    });
    setMuted(!enabled);
  }, []);

  useEffect(() => stopVoice, [stopVoice]);

  useEffect(() => {
    if (!voiceSessionId || (status !== "connecting" && status !== "connected")) return;

    const events = new EventSource(browserQuestionApiUrl(`/voice/transcripts/${voiceSessionId}`));
    events.addEventListener("transcript", (event) => {
      const transcript = parseVoiceTranscriptEvent(event.data);
      if (!transcript) return;
      setTranscriptError(null);
      setTranscripts((current) => [...current, transcript].slice(-6));
      if (transcript.role === "assistant") {
        setMicEnabled(true);
      }
    });
    events.onerror = () => {
      setTranscriptError("Voice transcript stream disconnected.");
    };

    return () => {
      events.close();
    };
  }, [status, voiceSessionId, setMicEnabled]);

  const patchIceCandidates = useCallback(async (connectionId: string, candidates: RTCIceCandidate[]) => {
    if (candidates.length === 0) return;
    const res = await fetch(browserQuestionApiUrl("/voice/api/offer"), {
      method: "PATCH",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({
        pc_id: connectionId,
        candidates: candidates.map(toPatchCandidate),
      }),
    });
    await readVoiceJson<unknown>(res, "ICE candidate patch");
  }, []);

  const startVoice = useCallback(async () => {
    if (status === "connecting" || status === "connected") return;
    stoppedRef.current = false;
    setStatus("connecting");
    setError(null);
    setTranscriptError(null);
    setTranscripts([]);
    setMuted(false);

    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error("This browser does not support microphone capture.");
      }

      const startRes = await fetch(browserQuestionApiUrl("/voice/start"), {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          sessionId,
          topK,
          scoreThreshold,
          enableDefaultIceServers: true,
        }),
      });
      const startJson = await readVoiceJson<VoiceStartResponse>(startRes, "Voice start");
      const activeSessionId = startJson.sessionId ?? sessionId;
      setVoiceSessionId(activeSessionId);

      const localStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      localStreamRef.current = localStream;
      setMeterStream(localStream);

      const peer = new RTCPeerConnection(startJson.iceConfig);
      peerRef.current = peer;
      localStream.getAudioTracks().forEach((track) => peer.addTrack(track, localStream));

      peer.ontrack = (event) => {
        const [remoteStream] = event.streams;
        if (remoteStream && audioRef.current) {
          audioRef.current.srcObject = remoteStream;
          void audioRef.current.play().catch(() => {
            /* The next user gesture will allow playback if autoplay is blocked. */
          });
        }
      };

      peer.onconnectionstatechange = () => {
        if (stoppedRef.current) return;
        if (peer.connectionState === "connected") {
          setStatus("connected");
        }
        if (["failed", "disconnected", "closed"].includes(peer.connectionState)) {
          setStatus(peer.connectionState === "closed" ? "idle" : "error");
        }
      };

      peer.onicecandidate = (event) => {
        if (!event.candidate) return;
        const connectionId = pcIdRef.current;
        if (!connectionId) {
          pendingCandidatesRef.current.push(event.candidate);
          return;
        }
        void patchIceCandidates(connectionId, [event.candidate]).catch((err) => {
          setError(err instanceof Error ? err.message : String(err));
          setStatus("error");
        });
      };

      const offer = await peer.createOffer();
      await peer.setLocalDescription(offer);

      const offerRes = await fetch(browserQuestionApiUrl("/voice/api/offer"), {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          sdp: offer.sdp,
          type: offer.type,
          request_data: {
            sessionId: activeSessionId,
          },
        }),
      });
      const answer = await readVoiceJson<VoiceOfferResponse>(offerRes, "Voice offer");
      if (!answer.sdp || !answer.type) {
        throw new Error("Voice offer response did not include an SDP answer.");
      }

      await peer.setRemoteDescription({ sdp: answer.sdp, type: answer.type });
      const connectionId = answer.pc_id ?? null;
      pcIdRef.current = connectionId;
      setPcId(connectionId);
      if (connectionId) {
        const pending = pendingCandidatesRef.current.splice(0);
        await patchIceCandidates(connectionId, pending);
      }
      if (!stoppedRef.current) setStatus("connected");
    } catch (err) {
      stopVoice();
      setStatus("error");
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [patchIceCandidates, scoreThreshold, sessionId, status, stopVoice, topK]);

  const connected = status === "connected";
  const connecting = status === "connecting";

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div
          className={cn(
            "inline-flex min-h-7 items-center gap-2 rounded-lg border border-border bg-background px-2.5 text-xs text-muted-foreground",
            connected && "border-primary/40 bg-primary/10 text-foreground",
            status === "error" && "border-destructive/40 bg-destructive/10 text-destructive"
          )}
          role="status"
          aria-live="polite"
        >
          {connecting ? (
            <Loader2 className="size-3.5 animate-spin" aria-hidden />
          ) : connected && muted ? (
            <Hourglass className="size-3.5 animate-pulse text-primary" aria-hidden />
          ) : connected ? (
            <Radio className="size-3.5 text-primary" aria-hidden />
          ) : status === "error" ? (
            <MicOff className="size-3.5" aria-hidden />
          ) : (
            <Volume2 className="size-3.5" aria-hidden />
          )}
          <span>{statusLabel(status, muted)}</span>
          <VoiceActivityMeter active={Boolean(meterStream) && (connecting || connected)} stream={meterStream} />
          {pcId ? <span className="hidden font-mono text-[10px] sm:inline">{pcId}</span> : null}
        </div>

        <div className="flex items-center gap-2">
          {connected ? (
            <Button
              type="button"
              variant="default"
              size="sm"
              onClick={() => setMicEnabled(muted)}
              aria-pressed={muted}
              aria-label={muted ? "Resume listening" : "Stop talking and send to RAG"}
            >
              {muted ? (
                <Mic className="mr-2 size-4" aria-hidden />
              ) : (
                <Send className="mr-2 size-4" aria-hidden />
              )}
              {muted ? "Resume" : "Stop & Send"}
            </Button>
          ) : null}
          <Button
            type="button"
            variant={connected || connecting ? "secondary" : "outline"}
            size="sm"
            onClick={connected || connecting ? stopVoice : () => void startVoice()}
            disabled={(disabled || !mediaPermissionsReady) && !connected && !connecting}
            aria-pressed={connected}
          >
            {connected || connecting ? (
              <MicOff className="mr-2 size-4" aria-hidden />
            ) : (
              <Mic className="mr-2 size-4" aria-hidden />
            )}
            {connected || connecting ? "Stop voice" : "Voice"}
          </Button>
        </div>
      </div>
      {!connected && !connecting ? (
        <VoiceMediaPermissionPrompt
          disabled={disabled}
          onReadyChange={setMediaPermissionsReady}
          className="max-w-full"
        />
      ) : null}
      <VoiceTranscriptPanel
        active={connecting || connected}
        transcripts={transcripts}
        error={transcriptError}
      />
      {error ? <p className="text-destructive text-xs leading-snug">{error}</p> : null}
      <audio ref={audioRef} autoPlay playsInline className="sr-only">
        <track kind="captions" />
      </audio>
    </div>
  );
}
