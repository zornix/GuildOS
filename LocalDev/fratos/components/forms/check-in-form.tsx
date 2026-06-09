"use client";
import { useState } from "react";
import { api } from "../../lib/api-client";
import { tokens } from "../../config/theme/tokens";
import { Btn } from "../ui/btn";
import { CodeInput } from "../ui/code-input";
import { FormActions } from "../ui/form-actions";

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
      <h3 style={{ margin: "0 0 4px", color: tokens.color.text }}>Check In</h3>
      <p style={{ color: tokens.color.textMuted, fontSize: tokens.font.sizeMd, margin: "0 0 16px" }}>Enter the code shown by your officer</p>
      <CodeInput
        value={code}
        onChange={(e) => setCode(e.target.value.toUpperCase())}
        placeholder="e.g. A7X9KP"
        error={error}
      />
      <FormActions>
        <Btn variant="ghost" onClick={onClose}>Cancel</Btn>
        <Btn onClick={submit} disabled={loading}>{loading ? "Checking in..." : "Check In"}</Btn>
      </FormActions>
    </>
  );
}
