export function Cta() {
  return (
    <section id="cta" className="relative px-6 py-24 sm:py-32">
      <div className="absolute inset-0">
        <div className="absolute left-1/2 top-0 h-[320px] w-[640px] -translate-x-1/2 rounded-full bg-accent/10 blur-[110px]" />
      </div>
      <div className="relative z-10 mx-auto max-w-3xl text-center">
        <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-2xl border border-gold/30 bg-gold/5 font-serif text-4xl font-black text-gold">
          Γ
        </div>
        <h2 className="font-heading text-4xl font-black tracking-[-0.04em] text-gradient sm:text-6xl">
          Build the chapter infrastructure Greek life has been missing.
        </h2>
        <p className="mx-auto mt-5 max-w-xl text-base leading-8 text-secondary">
          GreekOS gives chapters cleaner finances, better events, stronger accountability, smoother officer transitions, and an AI layer that preserves institutional memory.
        </p>
        <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <a href="mailto:studiozipgames@gmail.com?subject=GreekOS%20Early%20Access" className="btn-shine accent-gradient rounded-full px-10 py-3.5 text-sm font-bold text-white">
            Request early access →
          </a>
          <a href="#features" className="text-sm text-secondary transition-colors hover:text-primary">
            Review feature set
          </a>
        </div>
      </div>
    </section>
  );
}
