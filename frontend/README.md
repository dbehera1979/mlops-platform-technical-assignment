# MLOps Platform — Frontend

Angular 18 standalone app: model registry, deployment lifecycle, and
monitoring views over the FastAPI backend in `../backend`.

## Run locally

```bash
npm install
npm start          # ng serve, http://localhost:4200
```

`environment.ts` points at `http://localhost:8000` (the backend's default
port) directly — no proxy needed for local dev as long as the backend's
CORS origins include `http://localhost:4200` (they do, by default — see
`backend/app/config.py`).

`proxy.conf.json` is provided as an alternative if you'd rather route
through Angular's dev-server proxy instead (`ng serve --proxy-config
proxy.conf.json`); in that mode requests go to `/api/*` and
`environment.ts`'s `apiBaseUrl` would need to become `/api`.

## Build

```bash
npm run build       # production build, output in dist/frontend
```

Font inlining is disabled in `angular.json` for environments without
outbound access to Google Fonts at build time (e.g. CI sandboxes) — fonts
still load normally at runtime via the `<link>` tags in `index.html`.

## Demo auth

There's no real identity provider — sign in by picking one of four demo
roles (admin / approver / operator / viewer) on the login screen. See
`backend/app/core/security.py` for how the backend issues these tokens.

## Structure

- `core/` — models (mirroring backend Pydantic schemas), the single
  `ApiService` HTTP choke point, HTTP interceptors, RxJS-backed state
  services (one per domain), and the auth guard.
- `shared/components/` — `StateMessageComponent` (loading/empty/error/
  success, used everywhere) and `StatusChipComponent` (one status→color
  mapping used for both lifecycle stage and deployment status).
- `features/` — the five routed views: model-inventory,
  model-version-detail, deployments, monitoring, event-timeline — plus
  their dialogs.

## Tests

```bash
npm test
```

Uses Karma + Jasmine (Angular CLI default). **Note:** these specs were
written and reviewed but not executed in the sandbox this project was
built in — no headless Chrome was available there (snap-packaged
Chromium doesn't run without a working snapd). They follow standard
Angular `TestBed` patterns and are wired into `.github/workflows/ci.yml`;
run them locally or in CI to confirm.
