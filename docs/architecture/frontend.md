# Frontend

<p>
  <a href="../architecture/README.md"><img alt="docs: Architecture" src="https://img.shields.io/badge/docs-Architecture-2F6BFF?logo=readthedocs&logoColor=white"></a>
  <img alt="React: 19" src="https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black">
  <img alt="TypeScript: 5.9" src="https://img.shields.io/badge/TypeScript-5.9-3178C6?logo=typescript&logoColor=white">
  <img alt="Vite: 6" src="https://img.shields.io/badge/Vite-6-646CFF?logo=vite&logoColor=white">
  <img alt="Tailwind CSS: 4" src="https://img.shields.io/badge/Tailwind%20CSS-4-06B6D4?logo=tailwindcss&logoColor=white">
  <a href="../../frontend/src/hooks/useRunStream.ts"><img alt="source: hooks/useRunStream.ts" src="https://img.shields.io/badge/source-hooks%2FuseRunStream.ts-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 8 min" src="https://img.shields.io/badge/read-8%20min-555555">
</p>

[Docs](../README.md) › [Architecture](../architecture/README.md) › **Frontend** · page 21 of 57

**React 19, TypeScript, Vite, Tailwind CSS v4**, plus Radix primitives, TanStack Query, Zustand, Framer Motion, GSAP, Lenis, Recharts and Lucide.

This page is the signed-in console under `/app`. The landing page, the docs browser and the API reference are the [public web surface](web.md).

## What it is not

**Not a generic admin dashboard.** The target is infrastructure software: an observability console, a cloud control plane. That means:

- a **near-black ground** and **one restrained accent**
- **borders** doing the structural work, instead of shadows
- **high information density** where it earns its place
- a **monospace face** for every identifier, credit figure and engine name, so columns of numbers line up and stay scannable

## Structure

```
src/
├── components/
│   ├── ui/          Radix behaviour plus Tailwind styling, no wrapper library
│   ├── layout/      AppShell, MarketingLayout, CommandPalette
│   ├── charts/      Recharts with one palette and one tooltip
│   ├── graphs/      PlanGraph (edges drawn with GSAP) and CatalogGraph
│   ├── docs/        the markdown renderer for the docs browser
│   ├── marketing/   landing-page sections, SectionRail
│   └── shared/      ModeBadge, CacheLayerBadge, CostComparison, EmptyState,
│                    Pipeline, ThemeToggle
├── pages/           one per route, plus landing/ and settings/
├── hooks/           useQueries (TanStack), useRunStream and usePacedRun (SSE),
│                    useConsoleMotion, useSmoothScroll, useReducedMotion,
│                    useMediaQuery
├── lib/             api client, formatters, theme, scroll, docs loader,
│                    generated API reference and docs reading order
├── stores/          session, ui-prefs
├── animations/      Framer variants, GSAP helpers
├── styles/          globals.css
├── types/           api.ts, the server's response shapes
└── routes/
```

- **Domain components carry the [SerpFlow vocabulary](../product/glossary.md):** [execution mode](../product/execution-modes.md), [cache layer](caching.md), warm versus cold, [naive versus marginal](marginal-replanning.md#the-distinction)
- The product concepts appear **consistently**, instead of being re-described on every screen

## No fake data

- **There is no mock layer and no fixture data in the frontend**
- **Every number on every chart was computed by the server**
- **Stored decisions are read, not recomputed:** the Plan Inspector's counterfactual comes from the persisted Plan and its candidates
  - a recomputation that disagreed with what actually executed would be worse than no display at all
- **When a run finishes, the search page fetches the persisted run** and renders that, rather than reconstructing the result from stream frames

## The pipeline animation

The search page animates **eleven stages**. Each one advances because an [SSE frame](../api/streaming.md#the-stage-sequence) arrived saying it did:

```
analyzing intent -> finding candidate engines -> synthesizing parameters ->
inferring freshness requirements -> finding valid paths ->
generating candidate plans -> inspecting cache state ->
calculating marginal cost -> re-ranking plans -> checking budget ->
executing required steps
```

Code: [`hooks/useRunStream.ts`](../../frontend/src/hooks/useRunStream.ts) · [`pages/SearchPage.tsx`](../../frontend/src/pages/SearchPage.tsx) · [`components/shared/Pipeline.tsx`](../../frontend/src/components/shared/Pipeline.tsx)

- **The search page starts a streamed run:** `POST /v1/search` with `stream: true` returns 202 and the run id ([starting a run you can stream](../api/streaming.md#starting-a-run-you-can-stream))
- **`useRunStream`** opens an `EventSource` on `/v1/runs/{id}/stream`; the server replays what it has buffered for the run, then live frames follow
  - the access token travels as a query parameter, because `EventSource` cannot set headers ([streaming: authentication](../api/streaming.md#authentication))
  - a stream that closes before any frame arrives surfaces as `STREAM_DISCONNECTED`
- **No simulated progression.** A stage only completes when its real frame arrives. If the backend sits on "inspecting cache state" for two seconds, so does the UI
- **Paced, in order:** planning stages often finish within milliseconds of each other, so `usePacedRun` reveals them one at a time, holding each as running for at least `STAGE_DWELL_MS` (320 ms), or `EXECUTING_DWELL_MS` (600 ms) for execution
  - it never shows a stage complete before its real frame, never runs ahead of the backend, the timings shown are the real ones, and the result appears only once the reveal has caught up
  - `executing` emits a frame per step, so it settles only when the run ends; a failed stage ends the reveal there
- **Each stage renders detail straight from the frame's [`detail`](../api/streaming.md#what-detail-carries) object:**
  - which engines were retrieved
  - which parameters were bound
  - how many candidates were generated, and how many steps are warm
  - what each candidate costs cold and on the margin
- **A failed run still shows a result panel** instead of waiting forever: the error code and message, the persisted run's credits and mode, and a link to the Run Inspector
  - a failed run's transaction is rolled back, so it records 0 credits and no steps even when an earlier step was billed ([executor: when a run fails](executor.md#when-a-run-fails))
- **A billed search that found nothing shows SerpApi's own message** (`summary.notice`, typed in [`types/api.ts`](../../frontend/src/types/api.ts)) under "SerpApi found no results", and says it was counted and cached ([executor: an empty answer](executor.md#an-empty-answer-is-still-a-billed-answer))

## Animation

| Library | Used for | Reduced motion |
| --- | --- | --- |
| Lenis | Smooth scrolling on the public pages only; the console scrolls natively ([web: smooth scrolling](web.md#smooth-scrolling)) | Never started |
| Framer Motion | Page transitions, dialogs, lists, cards | Variants collapse to instant |
| GSAP | Plan graph edges, console card rise and figure count-ups, landing-page scroll scenes | Helpers set the end state directly |

- **`prefers-reduced-motion` is honoured in JavaScript**, and again in CSS as a backstop. An in-app reduce-motion preference (in `ui-prefs`) turns it on too; either one wins
- **The console scrolls inside its own container, natively.** Lenis was removed from the app shell because it cached the first page's height, so a taller page stopped short
  - a navigation starts at the top: the scroller resets when the outgoing page's exit animation completes ([`AppShell.tsx`](../../frontend/src/components/layout/AppShell.tsx))
- **Console motion is deliberately small** ([`hooks/useConsoleMotion.ts`](../../frontend/src/hooks/useConsoleMotion.ts)): `[data-card]` children rise on mount, not on scroll, and `[data-figure]` numbers count up, with the final value always in the DOM
  - on mount because ScrollTrigger watches the window, and the console scrolls an inner container: cards below the fold never triggered and stayed invisible

## Icons

- **Lucide only**
- **No emojis anywhere:** UI, empty states, toasts or documentation
- No decorative sparkle or star glyphs

## Permissions

- **The session store mirrors the server-resolved permission set** ([roles](../security/api-keys.md#roles)), so the UI hides what the caller cannot do instead of offering an action that returns 403
- **The server remains the authority** ([checks are centralised](../security/api-keys.md#checks-are-centralised)). This is a usability layer, not a security one

## Data fetching

- **TanStack Query**, with **4xx responses never retried**: the answer will not change, and retrying only delays a clear error ([`App.tsx`](../../frontend/src/App.tsx))
  - other failures are retried up to twice; no refetch on window focus; 30 s stale time
- **Mutations that touch a run invalidate together:** runs, dashboard, savings, cache dashboard and entries, budgets, guard rejections, cross-project, audit and alerts ([`hooks/useQueries.ts`](../../frontend/src/hooks/useQueries.ts))

## Routes

```
/                          landing page                     public
/docs/*                    docs browser (this folder)       public
/api                       API reference, from OpenAPI      public

/login  /register  /verify-email  /forgot-password  /reset-password
```

- **Everything under `/app` is protected.** Each console page reads a backend documented elsewhere:

| Route | Page | Backend side |
| --- | --- | --- |
| `/app` | overview: recent runs, layer distribution, budget and quota, cross-project benefit, alerts | [Instrumentation](marginal-replanning.md#instrumentation), [organization-level sharing](caching.md#organization-level-sharing) |
| `/app/search` | the central interaction | [Streaming](../api/streaming.md), [executor](executor.md) |
| `/app/runs` | run history | [API: runs](../api/overview.md#runs) |
| `/app/runs/:id` | Run Inspector: executed plan, provenance, stage trace, false-hit report | [Per-step record](executor.md#per-step-record), [rejections are evidence](caching.md#rejections-are-evidence) |
| `/app/plans`, `/app/plans/:id` | Plan Inspector: cold against marginal choice, every candidate, rejected engines, budget reduction | [What the Plan stores](planner.md#what-the-plan-stores), [ranking](marginal-replanning.md#ranking), [`changed_selection`](marginal-replanning.md#what-changed_selection-means) |
| `/app/catalog` | Catalog Explorer | [Catalog Explorer](catalog.md#catalog-explorer) |
| `/app/cache` | cache dashboard: layers, entries, guard rejections, partitions, storage | [Caching](caching.md), [the guard](caching.md#the-entity-and-numeral-guard), [invalidation](caching.md#invalidation) |
| `/app/budgets` | budgets, upstream quota, and project policy: semantic threshold, engine denylist, retention, shared cache | [Budget-aware reduction](marginal-replanning.md#budget-aware-reduction-happens-before-ranking), [budget enforcement](executor.md#budget-enforcement), [engine policy](executor.md#engine-policy), [retention](executor.md#retention) |
| `/app/analytics` | savings decomposition, engine reach, routing signal, measured volatility | [Spend and savings](../operations/observability.md#spend-and-savings), [adaptive TTL](caching.md#adaptive-ttl) |
| `/app/benchmarks` | routing accuracy and failure analysis | [Routing benchmark](../product/benchmark.md) |
| `/app/audit` | the hash-chained log | [The audit log](../database/rls.md#the-audit-log) |
| `/app/settings/*` | organization, members, roles, projects, api-keys, credentials, security, notifications | see below |

- **Settings:**
  - **roles** ([`settings/RolesSettings.tsx`](../../frontend/src/pages/settings/RolesSettings.tsx)): built-in and [custom roles](../security/api-keys.md#custom-roles)
  - **projects:** the project list, and each [project's execution mode](../product/execution-modes.md#setting-it)
  - **api-keys:** live and [test keys](../security/api-keys.md#test-keys), shown once
  - **credentials:** [upstream credentials](../security/credentials.md), encrypted on arrival and never returned ([BYOK](../security/byok.md))
  - **security:** active sessions, and signing out everywhere
  - **notifications:** email and webhook channels ([email](../operations/email.md))
- **The retention fields on the budgets page are stored but not yet applied:** the executor uses the instance values ([executor: retention](executor.md#retention))

## Related

- [The public web surface](web.md): landing page, docs browser, theme and motion
- [Streaming](../api/streaming.md): the SSE contract the pipeline consumes
- [Executor](executor.md): what a run records, which is what the Run Inspector shows
- [Backend](backend.md): the API behind every page
- [API keys](../security/api-keys.md): the roles and permissions the session store mirrors
- [Troubleshooting: the pipeline animation does not move](../operations/troubleshooting.md#the-pipeline-animation-does-not-move): when the stream is not delivering

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Backend](../architecture/backend.md) | [Docs index](../README.md) · [Architecture index](../architecture/README.md) | [The public web surface](../architecture/web.md) |
