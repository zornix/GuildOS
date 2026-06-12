"use client";
import { useState } from "react";
import { ApiErrorBanner } from "../components/api-error-banner";
import { TreasuryDashboard } from "../components/modules/treasury/treasury-dashboard";
import { EmptyState } from "../components/ui/empty-state";
import { useApi } from "../hooks/use-api";
import { adaptTreasuryDashboard } from "../lib/adapters/treasury";
import { api } from "../lib/api-client";
import type { TreasuryDashboardData, TreasuryPaymentSubmissionsPage } from "../lib/contracts/treasury";

const emptySubmissions = (total: number): TreasuryPaymentSubmissionsPage => ({
  data: [],
  next_cursor: null,
  total,
});

async function loadTreasuryDashboard(): Promise<TreasuryDashboardData> {
  const [dashboardResult, submissionsResult] = await Promise.allSettled([
    api.getTreasuryDashboard(),
    api.getTreasuryPaymentSubmissions("pending", 10),
  ]);

  if (dashboardResult.status === "rejected") throw dashboardResult.reason;

  const dashboard = dashboardResult.value;
  if (submissionsResult.status === "fulfilled") {
    return adaptTreasuryDashboard(dashboard, submissionsResult.value);
  }

  return adaptTreasuryDashboard(
    dashboard,
    emptySubmissions(dashboard.pending_proof_count),
    "Payment review requires payment:review access.",
  );
}

function currentPeriod() {
  const today = new Date();
  return `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}`;
}

function downloadCsv(filename: string, csv: string) {
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export function TreasuryPage() {
  const treasury = useApi<TreasuryDashboardData>(loadTreasuryDashboard);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  const handleExportReport = async () => {
    const period = currentPeriod();
    setExporting(true);
    setExportError(null);
    try {
      const csv = await api.getTreasuryReport(period, "ledger");
      downloadCsv(`treasury_ledger_${period}.csv`, csv);
    } catch (e) {
      setExportError((e as Error).message);
    } finally {
      setExporting(false);
    }
  };

  return (
    <>
      {treasury.error && <ApiErrorBanner message={treasury.error} onRetry={treasury.reload} loading={treasury.loading} />}
      {exportError && <ApiErrorBanner message={exportError} onRetry={handleExportReport} loading={exporting} />}
      {treasury.loading && !treasury.data ? (
        <EmptyState message="Loading treasury data..." />
      ) : treasury.data ? (
        <TreasuryDashboard data={treasury.data} onExportReport={handleExportReport} exporting={exporting} />
      ) : treasury.error ? null : (
        <EmptyState message="No treasury data available." />
      )}
    </>
  );
}
