"use client";
import { useAuth } from "../hooks/use-auth";
import { useApi } from "../hooks/use-api";
import { api } from "../lib/api-client";
import { T } from "../lib/theme";
import { tokens } from "../config/theme/tokens";
import type { Event, Excuse } from "../lib/types";
import type { Fine } from "../lib/contracts/fines";
import { adaptFines } from "../lib/adapters/fines";
import { isUpcomingEvent } from "../lib/event-time";
import { formatMoney } from "../lib/formatters/money";
import { ApiErrorBanner } from "../components/api-error-banner";
import { DashboardStats } from "../components/modules/dashboard/dashboard-stats";
import { UpcomingEventsWidget } from "../components/modules/dashboard/upcoming-events-widget";
import { PendingExcusesWidget } from "../components/modules/dashboard/pending-excuses-widget";
import { MyFinesWidget } from "../components/modules/dashboard/my-fines-widget";

export function DashboardPage() {
  const { user } = useAuth();
  const events = useApi<Event[]>(() => api.getEvents());
  const fines = useApi<Fine[]>(() => api.getFines().then(adaptFines));
  const excuses = useApi<Excuse[]>(() => api.getExcuses(user.role === "officer" ? "pending" : null));

  const now = new Date();
  const upcoming = (events.data || []).filter((e) => isUpcomingEvent(e, now));
  const unpaidFines = (fines.data || []).filter((f) => f.status === "unpaid");
  const pendingExcuses = (excuses.data || []).filter((e) => e.status === "pending");

  const upcomingStatValue =
    events.loading && !(events.data || []).length ? "…" : events.error ? "—" : String(upcoming.length);

  const officerExcuseStat =
    excuses.loading && !(excuses.data || []).length ? "…" : excuses.error ? "—" : String(pendingExcuses.length);

  const unpaidTotal = unpaidFines.reduce((s, f) => s + f.amountCents, 0);
  const finesStatValue =
    fines.loading && !(fines.data || []).length
      ? "…"
      : fines.error
        ? "—"
        : user.role === "officer"
          ? formatMoney(unpaidTotal)
          : String(unpaidFines.length);

  const stats =
    user.role === "officer"
      ? [
          { label: "Upcoming Events", value: upcomingStatValue, icon: "cal", color: T.ac },
          { label: "Pending Excuses", value: officerExcuseStat, icon: "file", color: T.warn },
          { label: "Unpaid Fines", value: finesStatValue, icon: "dollar", color: T.err },
        ]
      : [
          { label: "Upcoming Events", value: upcomingStatValue, icon: "cal", color: T.ac },
          { label: "My Unpaid Fines", value: finesStatValue, icon: "dollar", color: T.err },
        ];

  return (
    <div>
      {events.error && (
        <ApiErrorBanner message={`Events: ${events.error}`} onRetry={events.reload} loading={events.loading} />
      )}
      {fines.error && (
        <ApiErrorBanner message={`Fines: ${fines.error}`} onRetry={fines.reload} loading={fines.loading} />
      )}
      {excuses.error && (
        <ApiErrorBanner message={`Excuses: ${excuses.error}`} onRetry={excuses.reload} loading={excuses.loading} />
      )}
      <DashboardStats stats={stats} />
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: tokens.space[4] }}>
        <UpcomingEventsWidget events={upcoming} loading={events.loading} error={events.error} />
        {user.role === "officer" ? (
          <PendingExcusesWidget excuses={excuses.data} loading={excuses.loading} error={excuses.error} onReload={excuses.reload} />
        ) : (
          <MyFinesWidget fines={fines.data} loading={fines.loading} error={fines.error} />
        )}
      </div>
    </div>
  );
}
