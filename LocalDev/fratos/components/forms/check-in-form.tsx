"use client";
import { useState } from "react";
import { api } from "../../lib/api-client";
import { T } from "../../lib/theme";
import { Btn } from "../ui/btn";

interface CheckInFormProps {
  onSuccess: (msg: string) => void;
  onClose: () => void;
}

export function CheckInForm({ onSuccess, onClose }: CheckInFormProps) {
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    setError("");
    setLoading(true);
    try {
      const res = await api.checkinViaLink(code.trim());
      onSuccess(`Checked in to ${res.event_title}!`);
    } catch (e) {
      setError((e as Error).message);
    }
    setLoading(false);
  };

  return (
    <>
      <h3 style={{ margin: "0 0 4px", color: T.tx }}>Check In</h3>
      <p style={{ color: T.txm, fontSize: 13, margin: "0 0 16px" }}>Enter the code shown by your officer</p>
      <input
        value={code}
        onChange={(e) => setCode(e.target.value.toUpperCase())}
        placeholder="e.g. A7X9KP"
        style={{
          width: "100%",
          padding: 14,
          borderRadius: 8,
          border: `1px solid ${T.bd}`,
          background: T.bg,
          color: T.tx,
          fontSize: 20,
          fontFamily: "monospace",
          textAlign: "center",
          letterSpacing: 4,
          boxSizing: "border-box",
          marginBottom: 8,
        }}
      />
      {error && <div style={{ color: T.err, fontSize: 12, marginBottom: 8, textAlign: "center" }}>{error}</div>}
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 8 }}>
        <Btn variant="ghost" onClick={onClose}>Cancel</Btn>
        <Btn onClick={submit} disabled={loading}>{loading ? "Checking in..." : "Check In"}</Btn>
      </div>
    </>
  );
}
