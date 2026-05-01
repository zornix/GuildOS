"use client";

import { T } from "../lib/theme";
import { Card } from "./ui/card";
import { Btn } from "./ui/btn";

type Props = {
  message: string;
  onRetry: () => void;
  loading?: boolean;
};

export function ApiErrorBanner({ message, onRetry, loading }: Props) {
  return (
    <Card
      style={{
        marginBottom: 16,
        padding: 16,
        border: `1px solid ${T.err}44`,
        background: `${T.err}14`,
      }}
    >
      <div style={{ fontSize: 13, color: T.tx, marginBottom: 10 }}>{message}</div>
      <Btn variant="primary" onClick={onRetry} disabled={loading}>
        {loading ? "Retrying…" : "Retry"}
      </Btn>
    </Card>
  );
}
