export function ProductMockup() {
  return (
    <div className="opacity-0-start animate-fade-up-d4 relative mx-auto mt-16 max-w-4xl sm:mt-20">
      <div className="mockup-glow overflow-hidden rounded-2xl border border-border bg-surface text-left">
        <div className="flex items-center gap-2 border-b border-border bg-surface-bright/50 px-4 py-3">
          <div className="flex gap-1.5">
            <div className="h-2.5 w-2.5 rounded-full bg-red-500/60" />
            <div className="h-2.5 w-2.5 rounded-full bg-yellow-500/60" />
            <div className="h-2.5 w-2.5 rounded-full bg-green-500/60" />
          </div>
          <div className="mx-8 flex-1">
            <div className="mx-auto flex h-5 max-w-[190px] items-center justify-center rounded-md bg-border/50">
              <span className="text-[9px] text-muted">greekos.app/chapter-command</span>
            </div>
          </div>
        </div>

        <div className="grid gap-4 p-5 lg:grid-cols-[0.7fr_1.3fr]">
          <aside className="rounded-xl border border-border bg-background p-4">
            <div className="mb-5 flex items-center justify-between">
              <div>
                <p className="text-sm font-bold text-primary">TKE Dashboard</p>
                <p className="text-[11px] text-muted">Spring 2026 command view</p>
              </div>
              <span className="rounded-full bg-accent/15 px-2.5 py-1 text-[10px] font-bold text-red-100">LIVE</span>
            </div>
            <div className="space-y-2">
              {[
                ["Treasury", "82% collected"],
                ["Events", "7 active"],
                ["Tasks", "37 open"],
                ["Standards", "4 flags"],
              ].map(([label, value]) => (
                <div key={label} className="flex items-center justify-between rounded-lg border border-border bg-surface/60 px-3 py-2">
                  <span className="text-xs text-secondary">{label}</span>
                  <span className="text-xs font-bold text-primary">{value}</span>
                </div>
              ))}
            </div>
          </aside>

          <div className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-3">
              {[
                { label: "Dues collected", value: "82%", tone: "text-gold" },
                { label: "Pending proof", value: "8", tone: "text-primary" },
                { label: "Auto tasks", value: "37", tone: "text-gradient-red" },
              ].map((stat) => (
                <div key={stat.label} className="rounded-xl border border-border bg-background p-4">
                  <p className={`text-2xl font-black ${stat.tone}`}>{stat.value}</p>
                  <p className="mt-1 text-[11px] text-muted">{stat.label}</p>
                </div>
              ))}
            </div>

            <div className="grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
              <div className="rounded-xl border border-border bg-background p-4">
                <div className="mb-3 flex items-center justify-between">
                  <p className="text-sm font-bold text-primary">Treasurer review queue</p>
                  <span className="text-[10px] font-bold text-gold">ZELLE PROOF</span>
                </div>
                {[
                  ["Brother A", "$450 dues", "Screenshot uploaded"],
                  ["Brother B", "$950 rent", "Needs review"],
                  ["Brother C", "$25 fine", "Awaiting approval"],
                ].map(([name, amount, status]) => (
                  <div key={name} className="mb-2 flex items-center justify-between rounded-lg bg-surface/70 px-3 py-2 last:mb-0">
                    <div>
                      <p className="text-xs font-semibold text-primary">{name}</p>
                      <p className="text-[10px] text-muted">{status}</p>
                    </div>
                    <p className="text-xs font-bold text-primary">{amount}</p>
                  </div>
                ))}
              </div>

              <div className="rounded-xl border border-border bg-background p-4">
                <p className="mb-3 text-sm font-bold text-primary">AI task generator</p>
                <div className="rounded-lg border border-accent/20 bg-accent/10 p-3 text-[11px] leading-5 text-red-50">
                  “Create 5 days of tabling shifts for philanthropy week. Prioritize brothers with highest delinquency score.”
                </div>
                <div className="mt-3 space-y-2">
                  {["12 tabling shifts", "6 setup owners", "8 cleanup owners"].map((item) => (
                    <div key={item} className="flex items-center gap-2 text-[11px] text-secondary">
                      <span className="h-1.5 w-1.5 rounded-full bg-gold" />
                      {item}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div className="absolute inset-x-10 -bottom-5 h-10 rounded-b-2xl bg-accent/10 blur-2xl" />
    </div>
  );
}
