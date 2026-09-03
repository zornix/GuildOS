import { PRICING } from "@/config/landing-content";

export function Pricing() {
  return (
    <section id="pricing" className="border-b border-border px-6 py-24 sm:py-32">
      <div className="mx-auto max-w-6xl">
        <div className="mx-auto mb-14 max-w-2xl text-center">
          <p className="mb-3 text-[13px] font-bold uppercase tracking-[0.24em] text-gold">Pricing</p>
          <h2 className="font-heading text-4xl font-black tracking-[-0.04em] text-gradient sm:text-5xl">
            Chapter-friendly pricing.
          </h2>
          <p className="mt-4 text-base leading-7 text-secondary">
            Start with a founding chapter pilot. Scale into a full operating system once the workflows prove themselves.
          </p>
        </div>

        <div className="grid gap-4 md:grid-cols-3">
          {PRICING.map((plan) => (
            <article
              key={plan.name}
              className={`relative rounded-2xl border p-7 transition-all duration-300 ${
                plan.highlight
                  ? "border-accent/50 bg-accent/10 shadow-2xl shadow-red-950/20"
                  : "feature-gradient-1 border-border hover:border-border-bright"
              }`}
            >
              {plan.highlight && (
                <span className="accent-gradient absolute -top-3 left-1/2 -translate-x-1/2 rounded-full px-3 py-1 text-[10px] font-bold uppercase tracking-[0.16em] text-white">
                  Most useful
                </span>
              )}
              <h3 className="font-heading text-xl font-black text-primary">{plan.name}</h3>
              <p className="mt-2 text-sm leading-6 text-secondary">{plan.description}</p>
              <div className="mt-6 flex items-end gap-1">
                <span className="text-4xl font-black text-primary">{plan.price}</span>
                {plan.period && <span className="mb-1 text-sm text-muted">{plan.period}</span>}
              </div>
              <ul className="mt-6 space-y-3">
                {plan.features.map((feature) => (
                  <li key={feature} className="flex items-start gap-2 text-sm text-secondary">
                    <span className="mt-0.5 text-accent">✓</span>
                    {feature}
                  </li>
                ))}
              </ul>
              <a
                href="#cta"
                className={`mt-8 block rounded-full px-5 py-3 text-center text-sm font-bold transition ${
                  plan.highlight ? "btn-shine accent-gradient text-white" : "border border-border text-primary hover:border-border-bright hover:bg-surface-bright"
                }`}
              >
                {plan.cta}
              </a>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
