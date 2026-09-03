import { OPS } from "@/config/landing-content";

import { ProductMockup } from "./product-mockup";

export function Hero() {
  return (
    <>
      <section id="top" className="relative px-6 pb-20 pt-36 sm:pt-44 md:pb-28">
        <div className="hero-glow" />
        <div className="absolute left-1/2 top-28 h-44 w-44 -translate-x-1/2 rounded-full border border-gold/10 bg-gold/5 blur-3xl" />

        <div className="relative z-10 mx-auto max-w-6xl text-center">
          <div className="opacity-0-start animate-fade-up">
            <span className="mb-8 inline-flex items-center gap-2 rounded-full border border-gold/20 bg-gold/5 px-4 py-1.5 text-[11px] font-bold uppercase tracking-[0.24em] text-gold/90">
              <span className="h-1.5 w-1.5 rounded-full bg-gold animate-pulse-glow" />
              Old-school chapter values · AI-native operations
            </span>
          </div>

          <h1 className="opacity-0-start animate-fade-up-d1 mx-auto max-w-5xl font-heading text-5xl font-black leading-[0.92] tracking-[-0.055em] text-gradient sm:text-7xl lg:text-8xl">
            The operating system for modern Greek life.
          </h1>

          <p className="opacity-0-start animate-fade-up-d2 mx-auto mt-6 max-w-2xl text-base leading-8 text-secondary sm:text-lg">
            GreekOS brings dues, rent, fines, events, task generation, officer workflows, and AI-powered chapter memory into one command center built for Greek-letter organizations.
          </p>

          <div className="opacity-0-start animate-fade-up-d3 mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <a href="#cta" className="btn-shine accent-gradient rounded-full px-8 py-3.5 text-sm font-bold text-white shadow-xl shadow-red-950/30">
              Empower Your Chapter →
            </a>
            <a href="#ai-layer" className="group flex items-center gap-2 rounded-full border border-border px-6 py-3.5 text-sm text-secondary transition-all hover:border-border-bright hover:text-primary">
              See the AI layer
              <span className="transition-transform group-hover:translate-x-0.5">→</span>
            </a>
          </div>

          <ProductMockup />
        </div>
      </section>

      <section className="border-y border-border bg-surface/40 py-5">
        <div className="animate-marquee gap-10 text-sm font-bold uppercase tracking-[0.24em] text-muted">
          {Array.from({ length: 2 }).map((_, loop) => (
            <span key={loop} className="flex gap-10">
              {OPS.map((item) => <span key={`${loop}-${item}`}>{item}</span>)}
            </span>
          ))}
        </div>
      </section>
    </>
  );
}
