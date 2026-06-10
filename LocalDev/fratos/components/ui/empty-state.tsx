"use client";
import { tokens } from "../../config/theme/tokens";
import { Card } from "./card";

interface EmptyStateProps {
  message: string;
}

export function EmptyState({ message }: EmptyStateProps) {
  return (
    <Card style={{ textAlign: "center", color: tokens.color.textMuted, padding: tokens.space[7] }}>
      {message}
    </Card>
  );
}
