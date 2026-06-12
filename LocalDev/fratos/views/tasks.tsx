"use client";
import { useState } from "react";
import { useApi } from "../hooks/use-api";
import { usePermissions } from "../hooks/use-permissions";
import { api } from "../lib/api-client";
import { tokens } from "../config/theme/tokens";
import { Card } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Btn } from "../components/ui/btn";
import { Input } from "../components/ui/input";
import { Checkbox } from "../components/ui/checkbox";
import { ListRow } from "../components/ui/list-row";
import { LoadingState } from "../components/ui/loading-state";
import { EmptyState } from "../components/ui/empty-state";
import type { Task, TaskStatus } from "../lib/types";

const STATUS_BADGE: Record<TaskStatus, { color: "green" | "red" | "yellow" | "blue" | "gray"; label: string }> = {
  open: { color: "blue", label: "Open" },
  in_progress: { color: "yellow", label: "In Progress" },
  done: { color: "green", label: "Done" },
  cancelled: { color: "gray", label: "Cancelled" },
};

export function TasksPage() {
  const { can } = usePermissions();
  const tasks = useApi<Task[]>(() => api.getTasks(), []);
  const [title, setTitle] = useState("");
  const [required, setRequired] = useState(false);
  const [saving, setSaving] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const create = async () => {
    if (!title.trim()) return;
    setSaving(true);
    setActionError(null);
    try {
      await api.createTask({ title: title.trim(), required });
      setTitle("");
      setRequired(false);
      await tasks.reload();
    } catch (e) {
      setActionError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const setStatus = async (taskId: string, status: TaskStatus) => {
    setActionError(null);
    try {
      await api.updateTaskStatus(taskId, status);
      await tasks.reload();
    } catch (e) {
      setActionError((e as Error).message);
    }
  };

  const data = tasks.data || [];

  return (
    <div>
      {can("tasks:create") && (
        <Card style={{ marginBottom: tokens.space[5] }}>
          <h3 style={{ margin: `0 0 ${tokens.space[3]}`, fontSize: 15 }}>New Task</h3>
          <Input label="Title" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Book venue for formal" />
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: tokens.space[3] }}>
            <Checkbox checked={required} onChange={(e) => setRequired(e.target.checked)} label="Required (counts toward standing)" />
            <Btn onClick={create} disabled={saving || !title.trim()}>Create Task</Btn>
          </div>
        </Card>
      )}

      <Card>
        <h3 style={{ margin: `0 0 ${tokens.space[3]}`, fontSize: 15 }}>Tasks</h3>
        {actionError && (
          <div style={{ color: tokens.color.danger, fontSize: tokens.font.sizeSm, marginBottom: tokens.space[3] }}>{actionError}</div>
        )}
        {tasks.loading ? (
          <LoadingState />
        ) : tasks.error ? (
          <EmptyState message={tasks.error} />
        ) : (
          <div style={{ display: "grid", gap: 6 }}>
            {data.map((t) => {
              const badge = STATUS_BADGE[t.status] ?? STATUS_BADGE.open;
              return (
                <ListRow
                  key={t.id}
                  primary={t.title}
                  secondary={[
                    t.required ? "Required" : "Optional",
                    t.due_at ? `due ${new Date(t.due_at).toLocaleDateString()}` : null,
                    t.description,
                  ].filter(Boolean).join(" · ")}
                  right={
                    <div style={{ display: "flex", alignItems: "center", gap: tokens.space[2] }}>
                      {(t.status === "open" || t.status === "in_progress") && (
                        <Btn variant="success" style={{ padding: "4px 10px", fontSize: tokens.font.sizeSm }} onClick={() => setStatus(t.id, "done")}>
                          Mark Done
                        </Btn>
                      )}
                      <Badge color={badge.color}>{badge.label}</Badge>
                    </div>
                  }
                />
              );
            })}
            {data.length === 0 && <EmptyState message="No tasks yet" />}
          </div>
        )}
      </Card>
    </div>
  );
}
