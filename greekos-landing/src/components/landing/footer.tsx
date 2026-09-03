export function Footer() {
  return (
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
  );
}
