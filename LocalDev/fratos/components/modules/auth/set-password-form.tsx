"use client";
import { tokens } from "../../../config/theme/tokens";
import { AuthCard } from "./auth-card";

interface SetPasswordFormProps {
  newPassword: string;
  confirmPassword: string;
  error: string;
  loading: boolean;
  onNewPasswordChange: (v: string) => void;
  onConfirmPasswordChange: (v: string) => void;
  onSubmit: () => void;
}

const inputStyle = {
  width: "100%",
  padding: "12px 14px",
  borderRadius: tokens.radius.md,
  border: `1px solid ${tokens.color.border}`,
  background: tokens.color.bg,
  color: tokens.color.text,
  fontSize: tokens.font.sizeLg,
  marginBottom: 12,
  boxSizing: "border-box" as const,
};

export function SetPasswordForm({
  newPassword,
  confirmPassword,
  error,
  loading,
  onNewPasswordChange,
  onConfirmPasswordChange,
  onSubmit,
}: SetPasswordFormProps) {
  return (
    <AuthCard subtitle="Set your officer password">
      <input
        type="password"
        value={newPassword}
        onChange={(e) => onNewPasswordChange(e.target.value)}
        placeholder="New password (min 8 characters)"
        style={inputStyle}
      />
      <input
        type="password"
        value={confirmPassword}
        onChange={(e) => onConfirmPasswordChange(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter") onSubmit(); }}
        placeholder="Confirm password"
        style={inputStyle}
      />
      {error ? <div style={{ color: tokens.color.danger, fontSize: 12, marginBottom: 8 }}>{error}</div> : null}
      <button
        onClick={onSubmit}
        disabled={loading || !newPassword || !confirmPassword}
        style={{
          width: "100%",
          padding: "12px",
          borderRadius: tokens.radius.md,
          border: "none",
          background: tokens.color.accent,
          color: "#fff",
          fontSize: tokens.font.sizeLg,
          fontWeight: 600,
          cursor: loading ? "wait" : "pointer",
          opacity: loading ? 0.6 : 1,
        }}
      >
        {loading ? "Setting password..." : "Set Password & Continue"}
      </button>
    </AuthCard>
  );
}
