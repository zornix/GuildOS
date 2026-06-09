"use client";
import { tokens } from "../../../config/theme/tokens";
import { AuthCard } from "./auth-card";

interface LoginFormProps {
  email: string;
  password: string;
  showPasswordField: boolean;
  error: string;
  loading: boolean;
  onEmailChange: (v: string) => void;
  onPasswordChange: (v: string) => void;
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

export function LoginForm({
  email,
  password,
  showPasswordField,
  error,
  loading,
  onEmailChange,
  onPasswordChange,
  onSubmit,
}: LoginFormProps) {
  return (
    <AuthCard subtitle="Sign in">
      <input
        type="email"
        value={email}
        onChange={(e) => onEmailChange(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter" && email) onSubmit(); }}
        placeholder="you@chapter.org"
        style={inputStyle}
      />
      {showPasswordField && (
        <input
          type="password"
          value={password}
          onChange={(e) => onPasswordChange(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && email) onSubmit(); }}
          placeholder="Password"
          style={inputStyle}
        />
      )}
      {error ? <div style={{ color: tokens.color.danger, fontSize: 12, marginBottom: 8 }}>{error}</div> : null}
      <button
        onClick={onSubmit}
        disabled={loading || !email}
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
        {loading ? "Signing in..." : "Sign In"}
      </button>
    </AuthCard>
  );
}
