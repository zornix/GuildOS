"use client";
import { useState } from "react";
import { api } from "../../lib/api-client";
import { tokens } from "../../config/theme/tokens";
import { Btn } from "../ui/btn";
import { Textarea } from "../ui/textarea";
import { FormActions } from "../ui/form-actions";

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
      <h3 style={{ margin: "0 0 4px", color: tokens.color.text }}>Submit Excuse</h3>
      <p style={{ color: tokens.color.textMuted, fontSize: tokens.font.sizeMd, margin: "0 0 16px" }}>{eventTitle}</p>
      <Textarea
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        placeholder="Explain your reason..."
        rows={4}
        error={error}
      />
      <FormActions>
        <Btn variant="ghost" onClick={onClose}>Cancel</Btn>
        <Btn onClick={submit} disabled={loading}>{loading ? "Submitting..." : "Submit"}</Btn>
      </FormActions>
    </>
  );
}
