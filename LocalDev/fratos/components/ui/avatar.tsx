"use client";
import { T } from "../../lib/theme";

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
        borderRadius: 999,
        background: T.ac + "33",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontSize: size * 0.38,
        fontWeight: 700,
        color: T.acl,
        flexShrink: 0,
      }}
    >
      {initials}
    </div>
  );
}
