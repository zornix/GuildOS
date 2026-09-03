import { AI_FEATURES } from "@/config/landing-content";

export function AiLayer() {
  return (
    <section id="ai-layer" className="relative border-b border-border px-6 py-24 sm:py-32">
      <div className="absolute left-1/2 top-1/2 h-72 w-72 -translate-x-1/2 -translate-y-1/2 rounded-full bg-accent/10 blur-[100px]" />
      <div className="relative mx-auto grid max-w-6xl gap-10 lg:grid-cols-[0.9fr_1.1fr] lg:items-center">
        <div>
          <p className="mb-3 text-[13px] font-bold uppercase tracking-[0.24em] text-gold">AI Layer</p>
          <h2 className="font-heading text-4xl font-black tracking-[-0.04em] text-gradient sm:text-5xl">
            An executive assistant that knows your chapter.
          </h2>
          <p className="mt-5 text-base leading-8 text-secondary">
            GreekOS is not just a database. It becomes the memory layer for the chapter: bylaws, events, officer reports, meeting decisions, risk standards, finance records, and recurring tasks.
          </p>
        </div>

        <div className="rounded-3xl border border-border bg-surface p-5 shadow-2xl shadow-black/30">
          <div className="mb-4 flex items-center justify-between border-b border-border pb-4">
            <div>
              <p className="text-sm font-bold text-primary">GreekOS Copilot</p>
              <p className="text-xs text-muted">Chapter-aware agent interface</p>
            </div>
            <span className="rounded-full bg-gold/10 px-3 py-1 text-[10px] font-bold uppercase tracking-[0.18em] text-gold">RAG Ready</span>
          </div>
          <div className="space-y-3">
            {AI_FEATURES.map((item) => (
              <div key={item} className="flex gap-3 rounded-2xl border border-border bg-background p-4">
                <span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-accent" />
                <p className="text-sm leading-6 text-secondary">{item}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
