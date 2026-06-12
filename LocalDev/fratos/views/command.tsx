"use client";
import { useState } from "react";
import { useApi } from "../hooks/use-api";
import { usePermissions } from "../hooks/use-permissions";
import { api } from "../lib/api-client";
import { tokens } from "../config/theme/tokens";
import { Card } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Btn } from "../components/ui/btn";
import { Textarea } from "../components/ui/textarea";
import { ListRow } from "../components/ui/list-row";
import { LoadingState } from "../components/ui/loading-state";
import { EmptyState } from "../components/ui/empty-state";
import type { CommandRequest, CommandStatus } from "../lib/types";

const STATUS_BADGE: Record<CommandStatus, { color: "green" | "red" | "yellow" | "blue" | "gray"; label: string }> = {
  pending_approval: { color: "yellow", label: "Pending Approval" },
  approved: { color: "blue", label: "Approved" },
  rejected: { color: "red", label: "Rejected" },
  executed: { color: "green", label: "Executed" },
  failed: { color: "red", label: "Failed" },
};

export function CommandPage() {
  const { can, loading: permsLoading } = usePermissions();
  const canExecute = can("nl_controller:execute");
  const canApprove = can("nl_controller:approve");
  const commands = useApi<CommandRequest[]>(
    () => (canExecute || canApprove ? api.getCommands() : Promise.resolve([])),
    [canExecute, canApprove],
  );
  const [inputText, setInputText] = useState("");
  const [saving, setSaving] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  if (permsLoading) return <LoadingState />;
  if (!canExecute && !canApprove) {
    return (
      <Card style={{ textAlign: "center", color: tokens.color.textMuted, padding: tokens.space[8] }}>
        Command access required to view this page.
      </Card>
    );
  }

  const submit = async () => {
    if (!inputText.trim()) return;
    setSaving(true);
    setActionError(null);
    try {
      await api.submitCommand(inputText.trim());
      setInputText("");
      await commands.reload();
    } catch (e) {
      setActionError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const review = async (id: string, decision: "approve" | "reject") => {
    setActionError(null);
    try {
      await api.reviewCommand(id, decision);
      await commands.reload();
    } catch (e) {
      setActionError((e as Error).message);
    }
  };

  const data = commands.data || [];

  return (
    <div>
      {canExecute && (
        <Card style={{ marginBottom: tokens.space[5] }}>
          <h3 style={{ margin: `0 0 ${tokens.space[3]}`, fontSize: 15 }}>Submit Command</h3>
          <p style={{ color: tokens.color.textMuted, fontSize: tokens.font.sizeXs, margin: `0 0 ${tokens.space[3]}` }}>
            Commands are recorded and require officer approval. Parsing and execution
            are not implemented yet — nothing runs automatically.
          </p>
          <Textarea
            rows={2}
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            placeholder="e.g. Set up Thursday's chapter meeting with attendance and a setup task list"
          />
          <Btn onClick={submit} disabled={saving || !inputText.trim()}>Submit for Approval</Btn>
        </Card>
      )}

      <Card>
        <h3 style={{ margin: `0 0 ${tokens.space[3]}`, fontSize: 15 }}>Command Requests</h3>
        {actionError && (
          <div style={{ color: tokens.color.danger, fontSize: tokens.font.sizeSm, marginBottom: tokens.space[3] }}>{actionError}</div>
        )}
        {commands.loading ? (
          <LoadingState />
        ) : commands.error ? (
          <EmptyState message={commands.error} />
        ) : (
          <div style={{ display: "grid", gap: 6 }}>
            {data.map((c) => {
              const badge = STATUS_BADGE[c.status] ?? STATUS_BADGE.pending_approval;
              return (
                <ListRow
                  key={c.id}
                  primary={c.input_text}
                  secondary={`Submitted ${new Date(c.created_at).toLocaleString()}`}
                  right={
                    <div style={{ display: "flex", alignItems: "center", gap: tokens.space[2] }}>
                      {canApprove && c.status === "pending_approval" && (
                        <>
                          <Btn variant="success" style={{ padding: "4px 10px", fontSize: tokens.font.sizeSm }} onClick={() => review(c.id, "approve")}>
                            Approve
                          </Btn>
                          <Btn variant="danger" style={{ padding: "4px 10px", fontSize: tokens.font.sizeSm }} onClick={() => review(c.id, "reject")}>
                            Reject
                          </Btn>
                        </>
                      )}
                      <Badge color={badge.color}>{badge.label}</Badge>
                    </div>
                  }
                />
              );
            })}
            {data.length === 0 && <EmptyState message="No commands submitted yet" />}
          </div>
        )}
      </Card>
    </div>
  );
}
