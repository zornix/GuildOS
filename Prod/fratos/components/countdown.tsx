"use client";
import { useState, useEffect } from "react";
import { T } from "../lib/theme";

interface CountdownProps {
  expiresAt: string;
}

export function Countdown({ expiresAt }: CountdownProps) {
  const [left, setLeft] = useState("");

  useEffect(() => {
    const tick = () => {
      const diff = new Date(expiresAt).getTime() - Date.now();
      if (diff <= 0) {
        setLeft("Expired");
        return;
      }
      const m = Math.floor(diff / 60000);
      const s = Math.floor((diff % 60000) / 1000);
      setLeft(`${m}:${s.toString().padStart(2, "0")}`);
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [expiresAt]);

  const expired = left === "Expired";
  return (
    <span style={{ fontFamily: "monospace", fontWeight: 700, fontSize: 20, color: expired ? T.err : T.acl }}>
      {left}
    </span>
  );
}
