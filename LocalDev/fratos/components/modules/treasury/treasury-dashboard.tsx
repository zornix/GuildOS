"use client";
import type { ReactNode } from "react";
import { tokens } from "../../../config/theme/tokens";
import { formatMoney } from "../../../lib/formatters/money";
import type {
  PaymentSubmission,
  TreasuryDashboardData,
  TreasuryExpense,
  TreasuryPayment,
  TreasuryStat,
} from "../../../lib/contracts/treasury";
import { Badge } from "../../ui/badge";
import { Btn } from "../../ui/btn";
import { Card } from "../../ui/card";
import { Icon } from "../../ui/icon";

const palette = {
  globalBg: "#102A43",
  surface: "#1A3B5C",
  shadowAccent: "#4B1D67",
  cta: "#7AE582",
  heading: "#D7C9FF",
  body: "#FFFFFF",
  muted: "rgba(255, 255, 255, 0.72)",
  line: "rgba(215, 201, 255, 0.22)",
  row: "rgba(255, 255, 255, 0.055)",
};

const statusColor = {
  pending: "yellow",
  approved: "green",
  verified: "green",
  rejected: "red",
  needs_review: "purple",
  active: "green",
  invalidated: "red",
  scheduled: "blue",
  cleared: "green",
  flagged: "red",
} as const;

type StatusColorKey = keyof typeof statusColor;

interface TableColumn<T> {
  key: string;
  header: string;
  render: (row: T) => ReactNode;
  width?: string;
}

function money(cents: number) {
  return formatMoney(cents);
}

function statusBadge(status: StatusColorKey) {
  return <Badge color={statusColor[status]}>{status.replace("_", " ")}</Badge>;
}

function EmptyMessage({ children }: { children: ReactNode }) {
  return (
    <div
      style={{
        border: `1px solid ${palette.line}`,
        borderRadius: tokens.radius.md,
        color: palette.muted,
        padding: tokens.space[5],
        textAlign: "center",
      }}
    >
      {children}
    </div>
  );
}

function Shell({ children }: { children: ReactNode }) {
  return (
    <div
      style={{
        background: palette.globalBg,
        border: `1px solid ${palette.line}`,
        borderRadius: tokens.radius.lg,
        padding: tokens.space[5],
        color: palette.body,
        boxShadow: `0 18px 42px ${palette.shadowAccent}55`,
      }}
    >
      {children}
    </div>
  );
}

function DesignHeader({
  title,
  description,
  action,
  onAction,
  actionBusy,
}: {
  title: string;
  description: string;
  action: string;
  onAction?: () => void;
  actionBusy?: boolean;
}) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", gap: tokens.space[4], marginBottom: tokens.space[4], flexWrap: "wrap" }}>
      <div style={{ minWidth: 240, flex: "1 1 360px" }}>
        <h2 style={{ margin: 0, color: palette.heading, fontSize: 20, lineHeight: 1.15, fontWeight: 800, letterSpacing: 0 }}>{title}</h2>
        <p style={{ margin: "6px 0 0", color: palette.muted, fontSize: tokens.font.sizeMd, lineHeight: 1.45 }}>
          {description}
        </p>
      </div>
      <Btn
        onClick={onAction}
        disabled={actionBusy || !onAction}
        style={{
          alignSelf: "flex-start",
          background: palette.cta,
          color: palette.globalBg,
          opacity: actionBusy || !onAction ? 0.72 : 1,
          whiteSpace: "nowrap",
        }}
      >
        <Icon type="file" size={15} />
        {actionBusy ? "Exporting" : action}
      </Btn>
    </div>
  );
}

function MetricTile({ stat }: { stat: TreasuryStat }) {
  const tone =
    stat.tone === "mint"
      ? palette.cta
      : stat.tone === "lavender"
        ? palette.heading
        : stat.tone === "plum"
          ? "#C79BFF"
          : "#8CC7FF";

  return (
    <div
      style={{
        minWidth: 0,
        background: palette.surface,
        border: `1px solid ${palette.line}`,
        borderRadius: tokens.radius.md,
        padding: tokens.space[4],
      }}
    >
      <div style={{ color: palette.muted, fontSize: tokens.font.sizeSm, fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.6 }}>
        {stat.label}
      </div>
      <div style={{ color: tone, fontSize: 26, fontWeight: 800, lineHeight: 1.1, marginTop: 8 }}>
        {stat.valueCents !== undefined ? money(stat.valueCents) : stat.value}
      </div>
      <div style={{ color: palette.muted, fontSize: tokens.font.sizeSm, marginTop: 6 }}>{stat.trend}</div>
    </div>
  );
}

function Panel({ title, children, action }: { title: string; children: ReactNode; action?: ReactNode }) {
  return (
    <Card
      style={{
        background: palette.surface,
        borderColor: palette.line,
        color: palette.body,
        padding: tokens.space[4],
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", gap: tokens.space[3], marginBottom: tokens.space[3] }}>
        <h3 style={{ margin: 0, color: palette.heading, fontSize: tokens.font.sizeXl, fontWeight: 800 }}>{title}</h3>
        {action}
      </div>
      {children}
    </Card>
  );
}

function SubmissionList({ rows, unavailableMessage }: { rows: PaymentSubmission[]; unavailableMessage?: string }) {
  if (unavailableMessage) return <EmptyMessage>{unavailableMessage}</EmptyMessage>;
  if (rows.length === 0) return <EmptyMessage>No pending payment proofs.</EmptyMessage>;

  return (
    <div style={{ display: "grid", gap: tokens.space[2] }}>
      {rows.map((row) => (
        <div
          key={row.id}
          style={{
            display: "grid",
            gridTemplateColumns: "minmax(0, 1fr) auto",
            gap: tokens.space[3],
            alignItems: "center",
            padding: tokens.space[3],
            borderRadius: tokens.radius.md,
            background: palette.row,
            border: `1px solid ${palette.line}`,
          }}
        >
          <div style={{ minWidth: 0 }}>
            <div style={{ color: palette.body, fontWeight: 800, fontSize: tokens.font.sizeMd, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              {row.memberName}
            </div>
            <div style={{ color: palette.muted, fontSize: tokens.font.sizeSm, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              {row.memo} - {row.submittedAt}
            </div>
          </div>
          <div style={{ display: "grid", justifyItems: "end", gap: 4 }}>
            <div style={{ fontWeight: 800, color: palette.heading }}>{money(row.amountCents)}</div>
            {statusBadge(row.status)}
          </div>
        </div>
      ))}
    </div>
  );
}

function TreasuryTable<T>({ rows, columns, rowKey, emptyMessage }: { rows: T[]; columns: TableColumn<T>[]; rowKey: (row: T) => string; emptyMessage: string }) {
  if (rows.length === 0) return <EmptyMessage>{emptyMessage}</EmptyMessage>;

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
                  borderBottom: `1px solid ${palette.line}`,
                  color: palette.muted,
                  fontWeight: 700,
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
            <tr key={rowKey(row)} style={{ borderBottom: `1px solid ${palette.line}` }}>
              {columns.map((col) => (
                <td
                  key={col.key}
                  style={{
                    padding: `${tokens.space[2]} ${tokens.space[3]}`,
                    color: palette.body,
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

function PaymentTable({ rows }: { rows: TreasuryPayment[] }) {
  const columns: TableColumn<TreasuryPayment>[] = [
    { key: "member", header: "Member", render: (row) => row.memberName },
    { key: "detail", header: "Detail", render: (row) => row.detail },
    { key: "verified", header: "Verified", render: (row) => row.verifiedAt, width: "118px" },
    { key: "amount", header: "Amount", render: (row) => money(row.amountCents), width: "92px" },
  ];

  return <TreasuryTable columns={columns} rows={rows} rowKey={(row) => row.id} emptyMessage="No verified payments yet." />;
}

function ExpenseTable({ rows }: { rows: TreasuryExpense[] }) {
  const columns: TableColumn<TreasuryExpense>[] = [
    { key: "vendor", header: "Description", render: (row) => row.vendor },
    { key: "category", header: "Category", render: (row) => row.category },
    { key: "date", header: "Date", render: (row) => row.clearsAt, width: "118px" },
    { key: "amount", header: "Amount", render: (row) => money(row.amountCents), width: "92px" },
    { key: "status", header: "Status", render: (row) => statusBadge(row.status), width: "94px" },
  ];

  return <TreasuryTable columns={columns} rows={rows} rowKey={(row) => row.id} emptyMessage="No active expenses yet." />;
}

function LedgerCommand({
  data,
  onExportReport,
  exporting,
}: {
  data: TreasuryDashboardData;
  onExportReport?: () => void;
  exporting?: boolean;
}) {
  return (
    <Shell>
      <DesignHeader
        title="Ledger Command"
        description="Cash position, payment verification, invoice exposure, expense pressure, and month-end export in one officer cockpit."
        action="Export report"
        onAction={onExportReport}
        actionBusy={exporting}
      />
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: tokens.space[3], marginBottom: tokens.space[4] }}>
        {data.stats.map((stat) => (
          <MetricTile key={stat.label} stat={stat} />
        ))}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: tokens.space[4] }}>
        <Panel title="Payment review" action={<Badge color={data.pendingSubmissionTotal > 0 ? "purple" : "gray"}>{data.pendingSubmissionTotal} open</Badge>}>
          <SubmissionList rows={data.submissions.slice(0, 5)} unavailableMessage={data.submissionsUnavailableMessage} />
        </Panel>
        <Panel title="Recent payments">
          <PaymentTable rows={data.payments} />
        </Panel>
      </div>
      <div style={{ marginTop: tokens.space[4] }}>
        <Panel title="Active expenses">
          <ExpenseTable rows={data.expenses} />
        </Panel>
      </div>
    </Shell>
  );
}

export function TreasuryDashboard({
  data,
  onExportReport,
  exporting,
}: {
  data: TreasuryDashboardData;
  onExportReport?: () => void;
  exporting?: boolean;
}) {
  return (
    <div style={{ display: "grid", gap: tokens.space[4], color: palette.body }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          gap: tokens.space[4],
          alignItems: "flex-start",
          flexWrap: "wrap",
        }}
      >
        <div style={{ minWidth: 260, flex: "1 1 360px" }}>
          <h2 style={{ margin: 0, color: palette.heading, fontSize: 18, fontWeight: 800 }}>Treasury</h2>
          <p style={{ margin: "6px 0 0", color: palette.muted, fontSize: tokens.font.sizeMd, lineHeight: 1.45 }}>
            Live treasury data for dues collection, payment review, cash monitoring, and monthly close.
          </p>
        </div>
      </div>
      <LedgerCommand data={data} onExportReport={onExportReport} exporting={exporting} />
    </div>
  );
}
