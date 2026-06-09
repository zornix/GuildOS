"use client";
import { AuthProvider } from "./hooks/use-auth";
import { AppShell } from "./components/layout/app-shell";

export default function App() {
  return (
    <AuthProvider>
      <AppShell />
    </AuthProvider>
  );
}
