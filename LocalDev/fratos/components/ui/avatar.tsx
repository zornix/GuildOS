"use client";
import { tokens } from "../../config/theme/tokens";

interface AvatarProps {
  name?: string;
  size?: number;
}

export function Avatar({ name, size = 32 }: AvatarProps) {
  const initials = name
    ?.split(" ")
    .map((n) => n[0])
    .join("") || "?";
  return (
    <div
      style={{
        width: size,
        height: size,
        borderRadius: tokens.radius.pill,
        background: "#6c5ce733",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontSize: size * 0.38,
        fontWeight: 700,
        color: tokens.color.accentMuted,
        flexShrink: 0,
      }}
    >
      {initials}
    </div>
  );
}
