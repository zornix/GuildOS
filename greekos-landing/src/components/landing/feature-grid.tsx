import { FEATURES } from "@/config/landing-content";

export function FeatureGrid() {
  return (
    <section id="features" className="border-b border-border px-6 py-24 sm:py-32">
      <div className="mx-auto max-w-6xl">
        <div className="mx-auto mb-14 max-w-2xl text-center">
          <p className="mb-3 text-[13px] font-bold uppercase tracking-[0.24em] text-gold">Platform</p>
          <h2 className="font-heading text-4xl font-black tracking-[-0.04em] text-gradient sm:text-5xl">
            Built like a chapter house. Runs like command software.
          </h2>
          <p className="mt-4 text-base leading-7 text-secondary">
            The aesthetic is old-school Greek life. The engine is modern SaaS: permissions, automations, AI retrieval, audit trails, and clean workflows.
          </p>
        </div>

        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          {FEATURES.map((feature) => (
            <article
              key={feature.title}
              className={`${feature.size === "large" ? "md:col-span-2" : "md:col-span-1"} ${feature.gradient} card-glow rounded-2xl border border-border p-7 transition-all duration-300 hover:border-border-bright`}
            >
              <div className="mb-5 flex items-center justify-between">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-gold/20 bg-gold/5 font-serif text-xl font-black text-gold">
                  {feature.icon}
                </div>
                <span className="rounded-full border border-white/10 px-3 py-1 text-[10px] font-bold uppercase tracking-[0.18em] text-muted">
                  {feature.eyebrow}
                </span>
              </div>
              <h3 className="font-heading text-xl font-black text-primary">{feature.title}</h3>
              <p className="mt-2 text-sm leading-7 text-secondary">{feature.description}</p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
