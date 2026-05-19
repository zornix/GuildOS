"use client";

import { useState } from "react";

const NAV_LINKS = [
  { label: "Features", href: "#features" },
  { label: "AI Layer", href: "#ai-layer" },
  { label: "How It Works", href: "#workflow" },
  { label: "Pricing", href: "#pricing" },
];

const FEATURES = [
  {
    title: "Treasury & Dues",
    description:
      "Track dues, rent, fines, Zelle proof uploads, payment status, approvals, and officer edits without chasing screenshots in group chats.",
    icon: "₿",
    eyebrow: "Finance",
    gradient: "feature-gradient-1",
    size: "large",
  },
  {
    title: "Event Operations",
    description:
      "Create events, verify attendance, manage excuses, and auto-generate setup, cleanup, tabling, and risk tasks.",
    icon: "✦",
    eyebrow: "Events",
    gradient: "feature-gradient-2",
    size: "small",
  },
  {
    title: "Member Accountability",
    description:
      "Centralize roles, class years, attendance, member engagement, service hours, fines, and chapter standing in one member record.",
    icon: "Σ",
    eyebrow: "Roster",
    gradient: "feature-gradient-3",
    size: "small",
  },
  {
    title: "Officer Permissions",
    description:
      "Give chapter executives access to the exact tools they need.",
    icon: "Ω",
    eyebrow: "Exec",
    gradient: "feature-gradient-1",
    size: "small",
  },
  {
    title: "Standards & Compliance",
    description:
      "Track event coordination, GPA requirements, national reporting, and chapter expectations before they become emergencies.",
    icon: "Λ",
    eyebrow: "Standards",
    gradient: "feature-gradient-2",
    size: "small",
  },
  {
    title: "Chapter Knowledge Base",
    description:
      "Turn chapter bylaws, transition docs, meeting minutes, history, and more into searchable institutional memory.",
    icon: "◈",
    eyebrow: "Knowledge",
    gradient: "feature-gradient-3",
    size: "large",
  },
];

const AI_FEATURES = [
  "Ask questions about bylaws, officer duties, event history, or chapter policy",
  "Generate task lists for philanthropy weeks, parties, brotherhood events, and meetings",
  "Summarize exec notes into action items, owners, deadlines, and follow-ups",
  "Flag unpaid balances, missing attendance, incomplete training, and risky patterns",
];

const STEPS = [
  {
    number: "01",
    title: "Map the chapter",
    description:
      "Add members, officers, committees, dues categories, house roles, events, and chapter-specific workflows.",
  },
  {
    number: "02",
    title: "Run operations",
    description:
      "Use GreekOS for finances, events, member accountability, and chapter management. See the AI layer in action.",
  },
  {
    number: "03",
    title: "Keep memory alive",
    description:
      "Every semester adds more context, so future officers inherit a system instead of a half-broken folder of old files.",
  },
];

const PRICING = [
  {
    name: "Founding Chapter",
    price: "Free",
    period: "pilot",
    description: "For early chapters helping shape GreekOS before broad launch.",
    features: ["Core roster", "Event attendance", "Fine tracking", "Officer dashboard"],
    cta: "Join the pilot",
    highlight: false,
  },
  {
    name: "Chapter OS",
    price: "$149",
    period: "/mo",
    description: "For chapters ready to replace spreadsheets and group-chat operations.",
    features: [
      "Treasury workflows",
      "Zelle proof review",
      "Task generation",
      "Role permissions",
      "AI chapter knowledge base",
    ],
    cta: "Request access",
    highlight: true,
  },
  {
    name: "Council / HQ",
    price: "Custom",
    period: "",
    description: "For multi-chapter councils and larger Greek-letter organizations.",
    features: ["Multi-chapter reporting", "Custom onboarding", "Analytics", "Roadmap partnership"],
    cta: "Talk to us",
    highlight: false,
  },
];

const OPS = ["Dues", "Rent", "Fines", "Attendance", "Excuses", "Tasks", "Bylaws", "Reports", "Recruitment", "Transitions"];

export default function GreekOSLandingPage() {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  return (
    <main className="min-h-screen bg-background text-primary grid-pattern overflow-hidden selection:bg-accent/40">
      <header className="fixed inset-x-0 top-0 z-50 px-4 pt-3">
        <nav className="glass mx-auto flex max-w-6xl items-center justify-between rounded-full px-5 py-3 shadow-2xl shadow-black/30">
          <a href="#top" className="flex items-center gap-3">
            <div className="relative flex h-9 w-9 items-center justify-center rounded-lg border border-gold/30 bg-accent shadow-lg shadow-red-950/40">
              <span className="font-serif text-xl font-black text-white">Γ</span>
              <span className="absolute -right-1 -top-1 h-3 w-3 rounded-full border border-background bg-gold" />
            </div>
            <div>
              <p className="font-heading text-lg font-black leading-none tracking-tight text-white">GreekOS</p>
              <p className="hidden text-[10px] uppercase tracking-[0.22em] text-gold sm:block">Chapter Intelligence</p>
            </div>
          </a>

          <div className="hidden items-center gap-8 md:flex">
            {NAV_LINKS.map((link) => (
              <a key={link.href} href={link.href} className="text-[13px] text-secondary transition-colors hover:text-primary">
                {link.label}
              </a>
            ))}
          </div>

          <div className="hidden items-center gap-3 md:flex">
            <a href="#cta" className="text-[13px] text-secondary transition-colors hover:text-primary">Sign in</a>
            <a href="#cta" className="btn-shine accent-gradient rounded-full px-5 py-2 text-[13px] font-bold text-white">
              Request access
            </a>
          </div>

          <button
            className="md:hidden text-primary"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            aria-label="Toggle menu"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              {mobileMenuOpen ? (
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
              ) : (
                <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 9h16.5m-16.5 6.75h16.5" />
              )}
            </svg>
          </button>
        </nav>

        {mobileMenuOpen && (
          <div className="glass mx-4 mt-2 flex flex-col gap-3 rounded-3xl p-5 md:hidden">
            {NAV_LINKS.map((link) => (
              <a key={link.href} href={link.href} className="text-secondary hover:text-primary" onClick={() => setMobileMenuOpen(false)}>
                {link.label}
              </a>
            ))}
            <a href="#cta" className="accent-gradient rounded-full px-5 py-2.5 text-center text-sm font-bold text-white" onClick={() => setMobileMenuOpen(false)}>
              Request access
            </a>
          </div>
        )}
      </header>

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

      <footer className="border-t border-border px-6 py-12">
        <div className="mx-auto flex max-w-6xl flex-col gap-6 md:flex-row md:items-center md:justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-gold/30 bg-accent font-serif font-black text-white">Γ</div>
            <div>
              <p className="font-bold text-primary">GreekOS</p>
              <p className="text-xs text-muted">Old-school values. AI-native operations.</p>
            </div>
          </div>
          <p className="text-sm text-muted">© {new Date().getFullYear()} GreekOS. Built for chapters that want operational excellence.</p>
        </div>
      </footer>
    </main>
  );
}
