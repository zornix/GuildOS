"use client";
import { useState, useEffect, createContext, useContext, type ReactNode } from "react";
import { api } from "../lib/api-client";
import { AuthLoading } from "../components/modules/auth/auth-loading";
import { LoginForm } from "../components/modules/auth/login-form";
import { SetPasswordForm } from "../components/modules/auth/set-password-form";
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

  if (loading) return <AuthLoading />;

  if (showSetPassword)
    return (
      <SetPasswordForm
        newPassword={newPassword}
        confirmPassword={confirmPassword}
        error={loginError}
        loading={loginLoading}
        onNewPasswordChange={setNewPassword}
        onConfirmPasswordChange={setConfirmPassword}
        onSubmit={handleSetPassword}
      />
    );

  if (!user)
    return (
      <LoginForm
        email={loginEmail}
        password={loginPassword}
        showPasswordField={showPasswordField}
        error={loginError}
        loading={loginLoading}
        onEmailChange={setLoginEmail}
        onPasswordChange={setLoginPassword}
        onSubmit={() => handleLogin(loginEmail, showPasswordField ? loginPassword : undefined)}
      />
    );

  return <AuthContext.Provider value={{ user, logout }}>{children}</AuthContext.Provider>;
}

export const useAuth = () => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
};
