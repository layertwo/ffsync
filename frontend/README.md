# ffsync frontend

React 19 + Vite + Tailwind CSS v4 SPA. It handles OIDC sign-in and the Firefox
device-pairing flow against the ffsync APIs.

## Commands

```bash
npm ci
npm run dev      # Vite dev server
npm test         # vitest, 155 tests (happy-dom)
npm run build    # tsc -b && vite build, writes dist/
npm run preview  # serve the production build
```

There is no lint script: the repo-root ESLint config targets the CDK code, not
this app. `npm test` and `npm run build` are the gates.

## Layout

- `src/App.tsx` — routes and app shell
- `src/lib/` — API clients, OIDC/OAuth, HAWK signing, session storage, and the
  WebSocket pairing channel (TLS 1.3 PSK) in `pairing-channel/`
- `src/components/` — pages and the small UI kit in `components/ui/`
- `src/index.css` — Tailwind v4 theme (CSS-first `@theme` and `.dark` blocks;
  there is deliberately no `tailwind.config.js`)

`vite.config.ts` aliases `@` to `src/` and sets `happy-dom` as the test
environment. The built `dist/` is uploaded by the CDK `FrontendStack`.
