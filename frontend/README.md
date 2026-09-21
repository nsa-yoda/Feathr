# Reviewer Operations UI

Feature 023 provides the lightweight reviewer console in `public/index.html`.
It is served by the existing unprivileged nginx image, uses same-origin `/api/`
proxy requests, caps event bursts at 500 with request starts paced across five
seconds, and keeps operations data read-only and secret-safe. The additive
Visualizer page uses the locally vendored D3 7.9.0 dependency and the
read-only `/api/operations/visualizer` snapshot. It polls at most once every
500 ms, never overlaps requests, suspends while the tab is hidden, retains 600
samples (five minutes), defers repaint while the user has text selected inside
the view, restores the viewport scroll anchor after updates, and shows
stale/degraded state without discarding the last successful charts. Open
`http://localhost:3000` from the Compose stack. The static app supports
shareable routes with browser back/forward navigation: `/dashboard`,
`/generator`, `/events`, `/search`, `/analytics`, `/realtime`, `/visualizer`,
and `/operations`. The root path maps to the dashboard, and direct links are
served by the nginx SPA fallback.

Run the frontend checks with:

```bash
npm ci
npm run vendor
npm test
```

The current console is intentionally a static HTML application rather than a
React bundle. D3 owns only the Visualizer SVG nodes; the existing dashboard,
Realtime, analytics, search, events, generator, and operations views remain
unchanged.
