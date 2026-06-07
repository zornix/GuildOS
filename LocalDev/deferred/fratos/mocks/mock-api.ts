import { MOCK_DB } from "./mock-db";

const delay = (ms: number) => new Promise((r) => setTimeout(r, ms));
const uid = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 6);

interface MockResponse {
  ok: boolean;
  status?: number;
  json: () => Promise<unknown>;
}

export const mockApi = {
  async fetch(path: string, opts: RequestInit = {}): Promise<MockResponse> {
    await delay(200);
    const method = opts.method || "GET";
    const body = opts.body ? JSON.parse(opts.body as string) : null;
    const user = MOCK_DB.user;

    // AUTH
    if (path === "/api/auth/me") return { ok: true, json: async () => user };
    if (path === "/api/auth/invite") {
      return { ok: true, json: async () => ({ invited: body.emails, failed: [] }) };
    }

    // EVENTS
    if (path === "/api/events" && method === "GET") {
      const sorted = [...MOCK_DB.events].sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime());
      return { ok: true, json: async () => sorted };
    }
    if (path === "/api/events" && method === "POST") {
      const ev = { id: uid(), chapter_id: user!.chapter_id, created_by: user!.id, ...body };
      MOCK_DB.events.push(ev);
      return { ok: true, json: async () => ev };
    }
    const evMatch = path.match(/^\/api\/events\/([\w]+)$/);
    if (evMatch && method === "GET") {
      const ev = MOCK_DB.events.find((e) => e.id === evMatch[1]);
      if (ev) {
        ev.attendance_count = MOCK_DB.attendance.filter((a) => a.event_id === ev.id && a.checked_in).length;
      }
      return { ok: !!ev, status: ev ? 200 : 404, json: async () => ev || { detail: "Not found" } };
    }
    if (evMatch && method === "DELETE") {
      MOCK_DB.events = MOCK_DB.events.filter((e) => e.id !== evMatch[1]);
      return { ok: true, json: async () => ({ deleted: true }) };
    }

    // CHECK-IN LINKS
    const linkMatch = path.match(/^\/api\/events\/([\w]+)\/checkin-link$/);
    if (linkMatch && method === "POST") {
      MOCK_DB.checkin_links = MOCK_DB.checkin_links.map((l) =>
        l.event_id === linkMatch[1] ? { ...l, active: false } : l,
      );
      const code = Math.random().toString(36).slice(2, 8).toUpperCase();
      const link = {
        event_id: linkMatch[1],
        short_code: code,
        url: `/c/${code}`,
        expires_at: new Date(Date.now() + 600000).toISOString(),
        active: true,
        created_by: user!.id,
      };
      MOCK_DB.checkin_links.push(link);
      return { ok: true, json: async () => link };
    }
    if (linkMatch && method === "DELETE") {
      MOCK_DB.checkin_links = MOCK_DB.checkin_links.map((l) =>
        l.event_id === linkMatch[1] ? { ...l, active: false } : l,
      );
      return { ok: true, json: async () => ({ deactivated: true }) };
    }

    // ATTENDANCE
    const checkinMatch = path.match(/^\/api\/attendance\/checkin\/([\w]+)$/);
    if (checkinMatch && method === "POST") {
      const link = MOCK_DB.checkin_links.find((l) => l.short_code === checkinMatch[1] && l.active);
      if (!link || new Date(link.expires_at) < new Date())
        return { ok: false, status: 410, json: async () => ({ detail: "Link expired or invalid" }) };
      const exists = MOCK_DB.attendance.find((a) => a.event_id === link.event_id && a.member_id === user!.id);
      if (exists?.checked_in) return { ok: false, status: 409, json: async () => ({ detail: "Already checked in" }) };
      const att = {
        event_id: link.event_id,
        member_id: user!.id,
        checked_in: true,
        checked_in_at: new Date().toISOString(),
        method: "link" as const,
      };
      if (exists) Object.assign(exists, att);
      else MOCK_DB.attendance.push(att);
      const ev = MOCK_DB.events.find((e) => e.id === link.event_id);
      return { ok: true, json: async () => ({ status: "checked_in", event_title: ev?.title }) };
    }
    const attMatch = path.match(/^\/api\/attendance\/event\/([\w]+)$/);
    if (attMatch) {
      const eid = attMatch[1];
      const roster = MOCK_DB.members.map((m) => {
        const a = MOCK_DB.attendance.find((x) => x.event_id === eid && x.member_id === m.id);
        const exc = MOCK_DB.excuses.find((x) => x.event_id === eid && x.member_id === m.id);
        return {
          member_id: m.id,
          name: m.name,
          checked_in: !!(a?.checked_in),
          checked_in_at: a?.checked_in_at || null,
          method: a?.method || null,
          excuse_status: exc?.status || null,
        };
      });
      return { ok: true, json: async () => roster };
    }
    const manualMatch = path.match(/^\/api\/attendance\/event\/([\w]+)\/manual\/([\w]+)$/);
    if (manualMatch && method === "POST") {
      const [, eid, mid] = manualMatch;
      const exists = MOCK_DB.attendance.find((a) => a.event_id === eid && a.member_id === mid);
      const att = {
        event_id: eid,
        member_id: mid,
        checked_in: true,
        checked_in_at: new Date().toISOString(),
        method: "manual" as const,
      };
      if (exists) Object.assign(exists, att);
      else MOCK_DB.attendance.push(att);
      return { ok: true, json: async () => ({ status: "checked_in", method: "manual" }) };
    }

    // EXCUSES
    const excPostMatch = path.match(/^\/api\/excuses\/event\/([\w]+)$/);
    if (excPostMatch && method === "POST") {
      const eventId = excPostMatch[1];
      const existing = MOCK_DB.excuses.find(
        (e) => e.event_id === eventId && e.member_id === user!.id && (e.status === "pending" || e.status === "approved"),
      );
      if (existing) return { ok: false, status: 409, json: async () => ({ detail: "Excuse already submitted for this event" }) };
      MOCK_DB.excuses = MOCK_DB.excuses.filter(
        (e) => !(e.event_id === eventId && e.member_id === user!.id && e.status === "denied"),
      );
      const exc = {
        id: uid(),
        event_id: eventId,
        member_id: user!.id,
        reason: body.reason,
        status: "pending" as const,
        reviewed_by: null,
        submitted_at: new Date().toISOString(),
      };
      MOCK_DB.excuses.push(exc);
      return { ok: true, json: async () => exc };
    }
    if (path === "/api/excuses" && method === "GET") {
      const excuses =
        user!.role === "officer"
          ? MOCK_DB.excuses.map((e) => ({
              ...e,
              members: MOCK_DB.members.find((m) => m.id === e.member_id),
              events: MOCK_DB.events.find((ev) => ev.id === e.event_id),
            }))
          : MOCK_DB.excuses
              .filter((e) => e.member_id === user!.id)
              .map((e) => ({
                ...e,
                events: MOCK_DB.events.find((ev) => ev.id === e.event_id),
              }));
      return { ok: true, json: async () => excuses };
    }
    const reviewMatch = path.match(/^\/api\/excuses\/([\w]+)\/review$/);
    if (reviewMatch && method === "PUT") {
      const exc = MOCK_DB.excuses.find((e) => e.id === reviewMatch[1]);
      if (!exc) return { ok: false, status: 404, json: async () => ({ detail: "Not found" }) };
      exc.status = body.status;
      exc.reviewed_by = user!.id;
      if (body.status === "approved") {
        MOCK_DB.fines = MOCK_DB.fines.filter(
          (f) => !(f.event_id === exc.event_id && f.member_id === exc.member_id && f.status === "unpaid"),
        );
      }
      return { ok: true, json: async () => exc };
    }

    // FINES
    if (path === "/api/fines" && method === "GET") {
      const fines =
        user!.role === "officer"
          ? MOCK_DB.fines.map((f) => ({
              ...f,
              members: MOCK_DB.members.find((m) => m.id === f.member_id),
              events: MOCK_DB.events.find((e) => e.id === f.event_id),
            }))
          : MOCK_DB.fines
              .filter((f) => f.member_id === user!.id)
              .map((f) => ({
                ...f,
                events: MOCK_DB.events.find((e) => e.id === f.event_id),
              }));
      return { ok: true, json: async () => fines };
    }
    const payMatch = path.match(/^\/api\/fines\/([\w]+)\/pay$/);
    if (payMatch) {
      const fine = MOCK_DB.fines.find((f) => f.id === payMatch[1]);
      if (fine) {
        fine.status = "paid";
        fine.paid_at = new Date().toISOString();
      }
      return { ok: !!fine, json: async () => fine || { detail: "Not found" } };
    }
    const waiveMatch = path.match(/^\/api\/fines\/([\w]+)\/waive$/);
    if (waiveMatch) {
      const fine = MOCK_DB.fines.find((f) => f.id === waiveMatch[1]);
      if (fine) {
        fine.status = "waived";
        fine.waived_by = user!.id;
      }
      return { ok: !!fine, json: async () => fine || { detail: "Not found" } };
    }
    if (path === "/api/fines/summary") {
      const s = { total_unpaid: 0, total_paid: 0, total_waived: 0, count_unpaid: 0 };
      MOCK_DB.fines.forEach((f) => {
        if (f.status === "unpaid") {
          s.total_unpaid += f.amount;
          s.count_unpaid++;
        } else if (f.status === "paid") s.total_paid += f.amount;
        else s.total_waived += f.amount;
      });
      return { ok: true, json: async () => s };
    }

    // MEMBERS
    if (path === "/api/members") return { ok: true, json: async () => MOCK_DB.members };

    // DELINQUENCY
    if (path === "/api/delinquency/scores" && method === "GET") {
      const requiredEvents = MOCK_DB.events.filter((e) => e.required && new Date(e.date) <= new Date());
      const totalRequired = requiredEvents.length;
      const eventIds = new Set(requiredEvents.map((e) => e.id));

      const scores = MOCK_DB.members.map((m) => {
        const attended = MOCK_DB.attendance.filter(
          (a) => a.member_id === m.id && a.checked_in && eventIds.has(a.event_id),
        ).length;
        const excused = MOCK_DB.excuses.filter(
          (e) => e.member_id === m.id && e.status === "approved" && eventIds.has(e.event_id),
        ).length;
        const missed = Math.max(totalRequired - attended - excused, 0);
        const memberFines = MOCK_DB.fines.filter((f) => f.member_id === m.id && f.status === "unpaid");
        const unpaidAmount = memberFines.reduce((s, f) => s + f.amount, 0);

        const attPct = totalRequired ? attended / totalRequired : 1;
        const excPct = totalRequired ? excused / totalRequired : 0;
        const finePenalty = Math.min(unpaidAmount / 200, 0.1);
        const score = Math.round((attPct * 70 + excPct * 20 + (1 - finePenalty) * 10) * 10) / 10;

        return {
          member_id: m.id, name: m.name, email: m.email,
          score: Math.max(0, Math.min(100, score)),
          attended, excused, missed, total_required: totalRequired,
          unpaid_fines: memberFines.length, unpaid_amount: unpaidAmount,
        };
      });
      scores.sort((a, b) => a.score - b.score);
      return { ok: true, json: async () => scores };
    }

    const delinqMemberMatch = path.match(/^\/api\/delinquency\/member\/([\w]+)$/);
    if (delinqMemberMatch && method === "GET") {
      const mid = delinqMemberMatch[1];
      const member = MOCK_DB.members.find((m) => m.id === mid);
      if (!member) return { ok: false, status: 404, json: async () => ({ detail: "Not found" }) };

      const requiredEvents = MOCK_DB.events.filter((e) => e.required);
      const breakdown = requiredEvents.map((ev) => {
        const att = MOCK_DB.attendance.find((a) => a.event_id === ev.id && a.member_id === mid);
        const exc = MOCK_DB.excuses.find((e) => e.event_id === ev.id && e.member_id === mid);
        const fine = MOCK_DB.fines.find((f) => f.event_id === ev.id && f.member_id === mid);

        let status: string;
        if (att?.checked_in) status = "present";
        else if (exc?.status === "approved") status = "excused";
        else if (exc?.status === "pending") status = "excuse_pending";
        else status = "absent";

        return {
          event_id: ev.id, event_title: ev.title, event_date: ev.date,
          status, fine_amount: fine?.amount ?? null, fine_status: fine?.status ?? null,
        };
      });
      return { ok: true, json: async () => ({ member: { id: member.id, name: member.name, email: member.email }, breakdown }) };
    }

    if (path === "/api/delinquency/assign-security" && method === "POST") {
      const requiredEvents = MOCK_DB.events.filter((e) => e.required && new Date(e.date) <= new Date());
      const totalRequired = requiredEvents.length;
      const eventIds = new Set(requiredEvents.map((e) => e.id));

      const scores = MOCK_DB.members.map((m) => {
        const attended = MOCK_DB.attendance.filter(
          (a) => a.member_id === m.id && a.checked_in && eventIds.has(a.event_id),
        ).length;
        const attPct = totalRequired ? attended / totalRequired : 1;
        return { member_id: m.id, name: m.name, score: Math.round(attPct * 100 * 10) / 10 };
      });
      scores.sort((a, b) => a.score - b.score);
      return { ok: true, json: async () => ({ assigned: scores.slice(0, 3) }) };
    }

    const remindMatch = path.match(/^\/api\/delinquency\/remind\/([\w]+)$/);
    if (remindMatch && method === "POST") {
      const member = MOCK_DB.members.find((m) => m.id === remindMatch[1]);
      if (!member) return { ok: false, status: 404, json: async () => ({ detail: "Not found" }) };
      const unpaid = MOCK_DB.fines.filter((f) => f.member_id === member.id && f.status === "unpaid");
      return {
        ok: true,
        json: async () => ({
          sent_to: member.email, name: member.name,
          unpaid_count: unpaid.length, unpaid_total: unpaid.reduce((s, f) => s + f.amount, 0),
          message: "Reminder queued",
        }),
      };
    }

    return { ok: false, status: 404, json: async () => ({ detail: "Not found" }) };
  },
};
