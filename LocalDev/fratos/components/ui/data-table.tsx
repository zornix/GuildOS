"use client";
import type { ReactNode } from "react";
import { tokens } from "../../config/theme/tokens";

export interface Column<T> {
  key: string;
  header: string;
  render: (row: T) => ReactNode;
  width?: string;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  emptyMessage?: string;
}

export function DataTable<T>({ columns, rows, rowKey, emptyMessage = "No data" }: DataTableProps<T>) {
  if (rows.length === 0) {
    return (
      <div style={{ color: tokens.color.textMuted, textAlign: "center", padding: tokens.space[8] }}>
        {emptyMessage}
      </div>
    );
  }

  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: tokens.font.sizeMd }}>
        <thead>
          <tr>
            {columns.map((col) => (
              <th
                key={col.key}
                style={{
                  textAlign: "left",
                  padding: `${tokens.space[2]} ${tokens.space[3]}`,
                  borderBottom: `1px solid ${tokens.color.border}`,
                  color: tokens.color.textMuted,
                  fontWeight: 600,
                  fontSize: tokens.font.sizeSm,
                  textTransform: "uppercase",
                  letterSpacing: 0.5,
                  width: col.width,
                }}
              >
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={rowKey(row)} style={{ borderBottom: `1px solid ${tokens.color.border}` }}>
              {columns.map((col) => (
                <td
                  key={col.key}
                  style={{
                    padding: `${tokens.space[2]} ${tokens.space[3]}`,
                    color: tokens.color.text,
                    verticalAlign: "middle",
                  }}
                >
                  {col.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
