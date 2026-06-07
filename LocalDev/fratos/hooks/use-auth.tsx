"use client";
import { useState, useEffect, createContext, useContext, type ReactNode } from "react";
import { api } from "../lib/api-client";
import { T } from "../lib/theme";
import type { Member } from "../lib/types";

interface AuthContextValue {
  user: Member;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Member | null>(null);
  const [loading, setLoading] = useState(true);
  const [loginEmail, setLoginEmail] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [showPasswordField, setShowPasswordField] = useState(false);
  const [loginError, setLoginError] = useState("");
  const [loginLoading, setLoginLoading] = useState(false);

  // Set-password flow (officer first login without password)
  const [showSetPassword, setShowSetPassword] = useState(false);
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function initSession() {
      if (typeof window === "undefined") {
        setLoading(false);
        return;
      }

      const token = api.getToken();
      if (token) {
        try {
          const me = await api.getMe();
          if (!cancelled) setUser(me);
        } catch {
          if (!cancelled) api.setToken(null);
        }
      }
      if (!cancelled) setLoading(false);
    }

    void initSession();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleLogin = async (email: string, password?: string) => {
    setLoginError("");
    setLoginLoading(true);
    try {
      const normalizedEmail = email.trim().toLowerCase();
      const res = await api.login(normalizedEmail, password || undefined);
      if (res.access_token) {
        api.setToken(res.access_token);
        if (res.password_setup_required) {
          setShowSetPassword(true);
        } else {
          const me = await api.getMe();
          setUser(me);
        }
      }
    } catch (e) {
      const msg = (e as Error).message;
      if (msg.includes("PASSWORD_REQUIRED")) {
        setShowPasswordField(true);
        setLoginError("Officers must enter a password");
      } else {
        setLoginError(msg);
      }
    } finally {
      setLoginLoading(false);
    }
  };

  const handleSetPassword = async () => {
    setLoginError("");
    if (newPassword.length < 8) {
      setLoginError("Password must be at least 8 characters");
      return;
    }
    if (newPassword !== confirmPassword) {
      setLoginError("Passwords do not match");
      return;
    }
    setLoginLoading(true);
    try {
      await api.setPassword(newPassword);
      const me = await api.getMe();
      setShowSetPassword(false);
      setNewPassword("");
      setConfirmPassword("");
      setUser(me);
    } catch (e) {
      setLoginError((e as Error).message);
    } finally {
      setLoginLoading(false);
    }
  };

  const logout = () => {
    setUser(null);
    setShowSetPassword(false);
    setShowPasswordField(false);
    setLoginPassword("");
    setNewPassword("");
    setConfirmPassword("");
    api.setToken(null);
  };

  const inputStyle = { width: "100%", padding: "12px 14px", borderRadius: 8, border: `1px solid ${T.bd}`, background: T.bg, color: T.tx, fontSize: 14, marginBottom: 12, boxSizing: "border-box" as const };

  if (loading)
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100vh", background: T.bg, color: T.txm }}>
        Loading...
      </div>
    );

  if (showSetPassword) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: "100vh", background: T.bg, fontFamily: "'Inter', -apple-system, sans-serif", padding: 20 }}>
        <div style={{ background: T.sf, borderRadius: 16, padding: 32, maxWidth: 380, width: "100%", border: `1px solid ${T.bd}` }}>
          <div style={{ textAlign: "center", marginBottom: 24 }}>
            <div style={{ fontSize: 22, fontWeight: 800, color: T.tx }}>
              <span style={{ color: T.ac }}>Fraternity</span>OS
            </div>
            <p style={{ color: T.txm, fontSize: 13, marginTop: 4 }}>Set your officer password</p>
          </div>
          <input
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            placeholder="New password (min 8 characters)"
            style={inputStyle}
          />
          <input
            type="password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") handleSetPassword(); }}
            placeholder="Confirm password"
            style={inputStyle}
          />
          {loginError && <div style={{ color: T.err, fontSize: 12, marginBottom: 8 }}>{loginError}</div>}
          <button
            onClick={handleSetPassword}
            disabled={loginLoading || !newPassword || !confirmPassword}
            style={{ width: "100%", padding: "12px", borderRadius: 8, border: "none", background: T.ac, color: "#fff", fontSize: 14, fontWeight: 600, cursor: loginLoading ? "wait" : "pointer", opacity: loginLoading ? 0.6 : 1 }}
          >
            {loginLoading ? "Setting password..." : "Set Password & Continue"}
          </button>
        </div>
      </div>
    );
  }

  if (!user) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: "100vh", background: T.bg, fontFamily: "'Inter', -apple-system, sans-serif", padding: 20 }}>
        <div style={{ background: T.sf, borderRadius: 16, padding: 32, maxWidth: 380, width: "100%", border: `1px solid ${T.bd}` }}>
          <div style={{ textAlign: "center", marginBottom: 24 }}>
            <div style={{ fontSize: 22, fontWeight: 800, color: T.tx }}>
              <span style={{ color: T.ac }}>Fraternity</span>OS
            </div>
            <p style={{ color: T.txm, fontSize: 13, marginTop: 4 }}>Sign in</p>
          </div>
          <input
            type="email"
            value={loginEmail}
            onChange={(e) => setLoginEmail(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && loginEmail) handleLogin(loginEmail, showPasswordField ? loginPassword : undefined); }}
            placeholder="you@chapter.org"
            style={inputStyle}
          />
          {showPasswordField && (
            <input
              type="password"
              value={loginPassword}
              onChange={(e) => setLoginPassword(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && loginEmail) handleLogin(loginEmail, loginPassword); }}
              placeholder="Password"
              style={inputStyle}
            />
          )}
          {loginError && <div style={{ color: T.err, fontSize: 12, marginBottom: 8 }}>{loginError}</div>}
          <button
            onClick={() => handleLogin(loginEmail, showPasswordField ? loginPassword : undefined)}
            disabled={loginLoading || !loginEmail}
            style={{ width: "100%", padding: "12px", borderRadius: 8, border: "none", background: T.ac, color: "#fff", fontSize: 14, fontWeight: 600, cursor: loginLoading ? "wait" : "pointer", opacity: loginLoading ? 0.6 : 1 }}
          >
            {loginLoading ? "Signing in..." : "Sign In"}
          </button>
        </div>
      </div>
    );
  }

  return <AuthContext.Provider value={{ user, logout }}>{children}</AuthContext.Provider>;
}

export const useAuth = () => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
};
