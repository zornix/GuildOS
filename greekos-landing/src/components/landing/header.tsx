"use client";

import { useState } from "react";

import { NAV_LINKS } from "@/config/landing-content";

export function Header() {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  return (
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
  );
}
