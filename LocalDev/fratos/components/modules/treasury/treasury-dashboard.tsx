"use client";
import { useState, useEffect, type ReactNode } from "react";
import { tokens } from "../../../config/theme/tokens";
import { formatMoney } from "../../../lib/formatters/money";
import type {
  PaymentSubmission,
  TreasuryDashboardData,
  TreasuryExpense,
  TreasuryPayment,
  TreasuryStat,
  TreasuryReportDataset,
  TreasurySubmissionStatus,
  TreasuryPaymentSubmissionsPage,
} from "../../../lib/contracts/treasury";
import { Badge } from "../../ui/badge";
import { Btn } from "../../ui/btn";
import { Card } from "../../ui/card";
import { Icon } from "../../ui/icon";

const statusColorMap = {
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

type StatusColorKey = keyof typeof statusColorMap;

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
  return <Badge color={statusColorMap[status] as "green" | "yellow" | "red" | "purple" | "blue"}>{status.replace("_", " ")}</Badge>;
}

function EmptyMessage({ children }: { children: ReactNode }) {
  return (
    <div
      style={{
        border: `1px solid ${tokens.color.border}`,
        borderRadius: tokens.radius.lg,
        color: tokens.color.textMuted,
        padding: tokens.space[6],
        textAlign: "center",
        fontSize: tokens.font.sizeLg,
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
  onAction?: (dataset: TreasuryReportDataset) => void;
  actionBusy?: boolean;
}) {
  const [dataset, setDataset] = useState<TreasuryReportDataset>("ledger");
  return (
    <Card style={{ marginBottom: tokens.space[5], padding: tokens.space[6], borderRadius: tokens.radius.xl }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: tokens.space[5], flexWrap: "wrap", alignItems: "center" }}>
        <div style={{ minWidth: 280, flex: "1 1 400px" }}>
          <h2 style={{ margin: 0, color: tokens.color.text, fontSize: tokens.font.size3xl, fontWeight: 800 }}>{title}</h2>
          <p style={{ margin: "8px 0 0", color: tokens.color.textMuted, fontSize: tokens.font.sizeLg, lineHeight: 1.5 }}>
            {description}
          </p>
        </div>
        <div style={{ display: "flex", gap: tokens.space[3], alignItems: "center" }}>
          <select 
            value={dataset} 
            onChange={(e) => setDataset(e.target.value as TreasuryReportDataset)}
            style={{ 
              background: tokens.color.bg, 
              color: tokens.color.text, 
              border: `1px solid ${tokens.color.border}`, 
              padding: tokens.space[3], 
              borderRadius: tokens.radius.md,
              outline: "none",
              fontSize: tokens.font.sizeMd,
            }}
          >
            <option value="ledger">Master Ledger</option>
            <option value="payments">Verified Payments</option>
            <option value="invoices">Invoice Registry</option>
            <option value="expenses">Expense Log</option>
            <option value="member_balances">Member Balances</option>
          </select>
          <Btn
            onClick={() => onAction?.(dataset)}
            disabled={actionBusy || !onAction}
            style={{
              padding: `${tokens.space[3]} ${tokens.space[4]}`,
              fontSize: tokens.font.sizeMd,
              whiteSpace: "nowrap",
            }}
          >
            <Icon type="file" size={18} />
            {actionBusy ? "Exporting..." : action}
          </Btn>
        </div>
      </div>
    </Card>
  );
}

function MetricTile({ stat }: { stat: TreasuryStat }) {
  const toneMap: Record<string, string> = {
    mint: tokens.color.success,
    lavender: tokens.color.accent,
    plum: "#C79BFF",
  };
  
  const tone = toneMap[stat.tone || ""] || tokens.color.text;

  return (
    <Card style={{ padding: tokens.space[6], borderRadius: tokens.radius.xl, display: "flex", flexDirection: "column", gap: tokens.space[2] }}>
      <div style={{ color: tokens.color.textMuted, fontSize: tokens.font.sizeMd, fontWeight: 700, textTransform: "uppercase", letterSpacing: 1.2 }}>
        {stat.label}
      </div>
      <div style={{ color: tone, fontSize: 42, fontWeight: 800, lineHeight: 1.1, margin: "8px 0" }}>
        {stat.valueCents !== undefined ? money(stat.valueCents) : stat.value}
      </div>
      <div style={{ color: tokens.color.textMuted, fontSize: tokens.font.sizeMd, display: "flex", alignItems: "center", gap: "6px" }}>
        <Icon type="chart" size={16} />
        {stat.trend}
      </div>
    </Card>
  );
}

function Panel({ title, children, action }: { title: string; children: ReactNode; action?: ReactNode }) {
  return (
    <Card style={{ padding: tokens.space[6], borderRadius: tokens.radius.xl }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: tokens.space[4], marginBottom: tokens.space[5] }}>
        <h3 style={{ margin: 0, color: tokens.color.text, fontSize: tokens.font.size2xl, fontWeight: 800 }}>{title}</h3>
        {action}
      </div>
      {children}
    </Card>
  );
}

function SubmissionList({ rows, unavailableMessage }: { rows: PaymentSubmission[]; unavailableMessage?: string }) {
  if (unavailableMessage) return <EmptyMessage>{unavailableMessage}</EmptyMessage>;
  if (rows.length === 0) return <EmptyMessage>No pending payment proofs in queue.</EmptyMessage>;

  return (
    <div style={{ display: "grid", gap: tokens.space[3] }}>
      {rows.map((row) => (
        <div
          key={row.id}
          style={{
            display: "grid",
            gridTemplateColumns: "minmax(0, 1fr) auto",
            gap: tokens.space[4],
            alignItems: "center",
            padding: tokens.space[4],
            borderRadius: tokens.radius.lg,
            background: tokens.color.bg,
            border: `1px solid ${tokens.color.border}`,
          }}
        >
          <div style={{ minWidth: 0 }}>
            <div style={{ color: tokens.color.text, fontWeight: 700, fontSize: tokens.font.sizeLg, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              {row.memberName}
            </div>
            <div style={{ color: tokens.color.textMuted, fontSize: tokens.font.sizeMd, marginTop: "4px", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              {row.memo} <span style={{ margin: "0 6px", opacity: 0.5 }}>•</span> {row.submittedAt}
            </div>
          </div>
          <div style={{ display: "grid", justifyItems: "end", gap: 6 }}>
            <div style={{ fontWeight: 800, fontSize: tokens.font.sizeXl, color: tokens.color.text }}>{money(row.amountCents)}</div>
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
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: tokens.font.sizeLg }}>
        <thead>
          <tr>
            {columns.map((col) => (
              <th
                key={col.key}
                style={{
                  textAlign: "left",
                  padding: `${tokens.space[3]} ${tokens.space[4]}`,
                  borderBottom: `2px solid ${tokens.color.border}`,
                  color: tokens.color.textMuted,
                  fontWeight: 700,
                  fontSize: tokens.font.sizeMd,
                  textTransform: "uppercase",
                  letterSpacing: 1,
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
                    padding: `${tokens.space[4]} ${tokens.space[4]}`,
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

function PaymentTable({ rows }: { rows: TreasuryPayment[] }) {
  const columns: TableColumn<TreasuryPayment>[] = [
    { key: "member", header: "Member", render: (row) => <span style={{ fontWeight: 700 }}>{row.memberName}</span> },
    { key: "detail", header: "Detail", render: (row) => row.detail },
    { key: "verified", header: "Verified", render: (row) => <span style={{ color: tokens.color.textMuted }}>{row.verifiedAt}</span>, width: "140px" },
    { key: "amount", header: "Amount", render: (row) => <span style={{ fontWeight: 800, color: tokens.color.success }}>+{money(row.amountCents)}</span>, width: "120px" },
  ];

  return <TreasuryTable columns={columns} rows={rows} rowKey={(row) => row.id} emptyMessage="No verified payments yet." />;
}

function ExpenseTable({ rows }: { rows: TreasuryExpense[] }) {
  const columns: TableColumn<TreasuryExpense>[] = [
    { key: "vendor", header: "Description / Vendor", render: (row) => <span style={{ fontWeight: 700 }}>{row.vendor}</span> },
    { key: "category", header: "Category", render: (row) => <Badge color="blue">{row.category}</Badge> },
    { key: "date", header: "Date", render: (row) => <span style={{ color: tokens.color.textMuted }}>{row.clearsAt}</span>, width: "140px" },
    { key: "amount", header: "Amount", render: (row) => <span style={{ fontWeight: 800, color: tokens.color.danger }}>-{money(row.amountCents)}</span>, width: "120px" },
    { key: "status", header: "Status", render: (row) => statusBadge(row.status), width: "110px" },
  ];

  return <TreasuryTable columns={columns} rows={rows} rowKey={(row) => row.id} emptyMessage="No active expenses yet." />;
}

interface BigLedgerEntry {
  id: string;
  date: string;
  description: string;
  category: string;
  amountCents: number;
  type: "in" | "out";
}

function BigLedgerTable({ payments, expenses }: { payments: TreasuryPayment[], expenses: TreasuryExpense[] }) {
  const ledgerEntries: BigLedgerEntry[] = [
    ...payments.map(p => ({
      id: `p_${p.id}`,
      date: p.verifiedAt || "",
      description: `Payment from ${p.memberName} - ${p.detail}`,
      category: "Dues & Fines",
      amountCents: p.amountCents,
      type: "in" as const
    })),
    ...expenses.map(e => ({
      id: `e_${e.id}`,
      date: e.clearsAt || "",
      description: `Expense to ${e.vendor}`,
      category: e.category,
      amountCents: e.amountCents,
      type: "out" as const
    }))
  ].filter(e => e.date).sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());

  const columns: TableColumn<BigLedgerEntry>[] = [
    { key: "date", header: "Date", render: (row) => <span style={{ color: tokens.color.textMuted, fontWeight: 600 }}>{new Date(row.date).toLocaleDateString()}</span>, width: "140px" },
    { key: "desc", header: "Description", render: (row) => <span style={{ fontWeight: 700 }}>{row.description}</span> },
    { key: "cat", header: "Category", render: (row) => <Badge color={row.type === "in" ? "green" : "purple"}>{row.category}</Badge>, width: "160px" },
    { key: "amount", header: "Net Amount", render: (row) => (
      <span style={{ fontWeight: 800, color: row.type === "in" ? tokens.color.success : tokens.color.danger }}>
        {row.type === "in" ? "+" : "-"}{money(row.amountCents)}
      </span>
    ), width: "140px" },
  ];

  return (
    <Panel title="Immutable Big Ledger" action={<Badge color="blue">{ledgerEntries.length} Records</Badge>}>
      <TreasuryTable columns={columns} rows={ledgerEntries} rowKey={(row) => row.id} emptyMessage="No ledger history available." />
    </Panel>
  );
}

function LedgerCommand({
  data,
  onExportReport,
  exporting,
  fetchSubmissions,
  activeTab = "overview",
}: {
  data: TreasuryDashboardData;
  onExportReport?: (dataset: TreasuryReportDataset) => void;
  exporting?: boolean;
  fetchSubmissions?: (status: TreasurySubmissionStatus, cursor?: string | null) => Promise<TreasuryPaymentSubmissionsPage>;
  activeTab?: "overview" | "submissions" | "payments" | "expenses" | "big_ledger";
}) {
  const [submissionsTab, setSubmissionsTab] = useState<TreasurySubmissionStatus>("pending");
  const [submissions, setSubmissions] = useState<PaymentSubmission[]>(data.submissions.slice(0, 5));
  const [loadingSubmissions, setLoadingSubmissions] = useState(false);

  useEffect(() => {
    if (submissionsTab === "pending" && data.submissions) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setSubmissions(data.submissions.slice(0, 5));
      return;
    }
    if (!fetchSubmissions) return;
    let valid = true;
    setLoadingSubmissions(true);
    fetchSubmissions(submissionsTab, null).then((page) => {
      if (valid) {
        setSubmissions(page.data.map(r => ({
          id: r.id,
          memberName: r.member_id,
          memo: r.method,
          amountCents: r.claimed_amount_cents,
          status: r.status,
          submittedAt: r.created_at || "",
        })));
        setLoadingSubmissions(false);
      }
    }).catch(() => {
      if (valid) setLoadingSubmissions(false);
    });
    return () => { valid = false; };
  }, [submissionsTab, data.submissions, fetchSubmissions]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: tokens.space[5] }}>
      {activeTab === "overview" && (
        <>
          <DesignHeader
            title="Ledger Command"
            description="Cash position, payment verification, invoice exposure, expense pressure, and month-end export in one officer cockpit."
            action="Export Report"
            onAction={onExportReport}
            actionBusy={exporting}
          />
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: tokens.space[5] }}>
            {data.stats.map((stat) => (
              <MetricTile key={stat.label} stat={stat} />
            ))}
          </div>
        </>
      )}

      {activeTab === "big_ledger" && (
        <BigLedgerTable payments={data.payments} expenses={data.expenses} />
      )}
      
      {activeTab === "submissions" && (
        <Panel 
          title="Payment Review Queue" 
          action={
            <select 
              value={submissionsTab} 
              onChange={(e) => setSubmissionsTab(e.target.value as TreasurySubmissionStatus)}
              style={{ 
                background: tokens.color.bg, 
                color: tokens.color.text, 
                border: `1px solid ${tokens.color.border}`, 
                padding: `${tokens.space[2]} ${tokens.space[3]}`, 
                borderRadius: tokens.radius.md,
                outline: "none",
                fontSize: tokens.font.sizeMd,
              }}
            >
              <option value="pending">Pending Review</option>
              <option value="approved">Approved</option>
              <option value="verified">Verified</option>
              <option value="rejected">Rejected</option>
            </select>
          }
        >
          {loadingSubmissions ? (
            <EmptyMessage>Loading submissions...</EmptyMessage>
          ) : (
            <SubmissionList rows={submissions} unavailableMessage={submissionsTab === "pending" ? data.submissionsUnavailableMessage : undefined} />
          )}
        </Panel>
      )}

      {activeTab === "payments" && (
        <Panel title="Recent Verified Payments">
          <PaymentTable rows={data.payments} />
        </Panel>
      )}

      {activeTab === "expenses" && (
        <Panel title="Active Organization Expenses">
          <ExpenseTable rows={data.expenses} />
        </Panel>
      )}
    </div>
  );
}

export function TreasuryDashboard({
  data,
  onExportReport,
  exporting,
  fetchSubmissions,
}: {
  data: TreasuryDashboardData;
  onExportReport?: (dataset: TreasuryReportDataset) => void;
  exporting?: boolean;
  fetchSubmissions?: (status: TreasurySubmissionStatus, cursor?: string | null) => Promise<TreasuryPaymentSubmissionsPage>;
}) {
  const [activeTab, setActiveTab] = useState<"overview" | "big_ledger" | "submissions" | "payments" | "expenses">("overview");

  return (
    <div style={{ display: "grid", gap: tokens.space[5], color: tokens.color.text }}>
      <div style={{ display: "flex", gap: tokens.space[3], flexWrap: "wrap", paddingBottom: tokens.space[2], borderBottom: `1px solid ${tokens.color.border}` }}>
        <Btn onClick={() => setActiveTab("overview")} variant={activeTab === "overview" ? "primary" : "ghost"} style={{ fontSize: tokens.font.sizeLg, padding: `${tokens.space[3]} ${tokens.space[5]}` }}>Overview</Btn>
        <Btn onClick={() => setActiveTab("big_ledger")} variant={activeTab === "big_ledger" ? "primary" : "ghost"} style={{ fontSize: tokens.font.sizeLg, padding: `${tokens.space[3]} ${tokens.space[5]}` }}>Big Ledger</Btn>
        <Btn onClick={() => setActiveTab("submissions")} variant={activeTab === "submissions" ? "primary" : "ghost"} style={{ fontSize: tokens.font.sizeLg, padding: `${tokens.space[3]} ${tokens.space[5]}` }}>Submissions</Btn>
        <Btn onClick={() => setActiveTab("payments")} variant={activeTab === "payments" ? "primary" : "ghost"} style={{ fontSize: tokens.font.sizeLg, padding: `${tokens.space[3]} ${tokens.space[5]}` }}>Payments</Btn>
        <Btn onClick={() => setActiveTab("expenses")} variant={activeTab === "expenses" ? "primary" : "ghost"} style={{ fontSize: tokens.font.sizeLg, padding: `${tokens.space[3]} ${tokens.space[5]}` }}>Expenses</Btn>
      </div>

      <LedgerCommand data={data} onExportReport={onExportReport} exporting={exporting} fetchSubmissions={fetchSubmissions} activeTab={activeTab} />
    </div>
  );
}

