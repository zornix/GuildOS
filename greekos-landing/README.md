# GreekOS Landing Page

A Next.js 15 + Tailwind landing page for GreekOS: an old-school Greek-life inspired, AI-native chapter operations platform.

## Run locally

```bash
npm install
npm run dev
```

Then open `http://localhost:3000`.

## Quality checks

```bash
npm run lint
npm run build
```

Both commands should pass before deploying.

## Deploy on Vercel

```bash
npm i -g vercel@latest
vercel login
vercel link
vercel --prod
```

For preview deployments on each change:

```bash
vercel
```

## Main files

- `src/app/page.tsx` — landing page
- `src/app/layout.tsx` — app metadata/layout
- `src/app/globals.css` — Tailwind and custom visual utilities
- `tailwind.config.ts` — color palette, fonts, animations
- `eslint.config.mjs` — ESLint flat config for CI/local linting
