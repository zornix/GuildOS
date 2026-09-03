import { STEPS } from "@/config/landing-content";

export function Workflow() {
  return (
    <section id="workflow" className="border-b border-border px-6 py-24 sm:py-32">
      <div className="mx-auto max-w-5xl">
        <div className="mb-14 text-center">
          <p className="mb-3 text-[13px] font-bold uppercase tracking-[0.24em] text-gold">How it works</p>
          <h2 className="font-heading text-4xl font-black tracking-[-0.04em] text-gradient sm:text-5xl">
            From group-chat chaos to institutional memory.
          </h2>
        </div>

        <div className="relative grid gap-6 md:grid-cols-3">
          <div className="absolute left-[18%] right-[18%] top-10 hidden h-px bg-gradient-to-r from-transparent via-accent/30 to-transparent md:block" />
          {STEPS.map((step) => (
            <div key={step.number} className="relative text-center">
              <div className="relative z-10 mx-auto mb-5 flex h-12 w-12 items-center justify-center rounded-full border border-accent/30 bg-accent/10 font-heading text-xs font-black text-accent">
                {step.number}
              </div>
              <h3 className="font-heading text-lg font-black text-primary">{step.title}</h3>
              <p className="mt-2 text-sm leading-7 text-secondary">{step.description}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
