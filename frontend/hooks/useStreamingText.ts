"use client";

import { useEffect, useRef, useState } from "react";

const DEFAULT_CHAR_INTERVAL_MS = 18;

export function useStreamingText(
  text: string | undefined,
  charIntervalMs: number = DEFAULT_CHAR_INTERVAL_MS,
) {
  const [displayed, setDisplayed] = useState("");
  const [prevText, setPrevText] = useState<string | undefined>(undefined);
  const rafRef = useRef<number | null>(null);
  const idxRef = useRef(0);
  const startRef = useRef(0);

  // Reset displayed text during render when input changes (React-recommended pattern)
  if (text !== prevText) {
    setPrevText(text);
    setDisplayed("");
  }

  useEffect(() => {
    if (!text) return;

    idxRef.current = 0;
    startRef.current = performance.now();

    const tick = (now: number) => {
      const elapsed = now - startRef.current;
      const target = Math.min(
        text.length,
        Math.floor(elapsed / charIntervalMs) + 1,
      );
      if (target !== idxRef.current) {
        idxRef.current = target;
        setDisplayed(text.slice(0, target));
      }
      if (target < text.length) {
        rafRef.current = requestAnimationFrame(tick);
      } else {
        rafRef.current = null;
      }
    };

    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current !== null) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
    };
  }, [text, charIntervalMs]);

  const isStreaming = displayed.length < (text?.length ?? 0);
  return { displayed, isStreaming };
}
