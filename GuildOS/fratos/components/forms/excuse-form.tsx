"use client";
import { useState } from "react";
import { api } from "../../lib/api-client";
import { T } from "../../lib/theme";
import { Btn } from "../ui/btn";

interface ExcuseFormProps {
  eventId: string;
  eventTitle: string;
  onSuccess: () => void;
  onClose: () => void;
}

export function ExcuseForm({ eventId, eventTitle, onSuccess, onClose }: ExcuseFormProps) {
  const [reason, setReason] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const submit = async () => {
    if (!reason.trim()) return;
    setError("");
    setLoading(true);
    try {
      await api.submitExcuse(eventId, reason);
      onSuccess();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <h3 style={{ margin: "0 0 4px", color: T.tx }}>Submit Excuse</h3>
      <p style={{ color: T.txm, fontSize: 13, margin: "0 0 16px" }}>{eventTitle}</p>
      <textarea
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        placeholder="Explain your reason..."
        rows={4}
        style={{
          width: "100%",
          padding: 12,
          borderRadius: 8,
          border: `1px solid ${T.bd}`,
          background: T.bg,
          color: T.tx,
          fontSize: 14,
          resize: "vertical",
          boxSizing: "border-box",
          fontFamily: "inherit",
          marginBottom: 8,
        }}
      />
      {error && <div style={{ color: T.err, fontSize: 12, marginBottom: 8 }}>{error}</div>}
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
        <Btn variant="ghost" onClick={onClose}>Cancel</Btn>
        <Btn onClick={submit} disabled={loading}>{loading ? "Submitting..." : "Submit"}</Btn>
      </div>
    </>
  );
}
