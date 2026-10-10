# Frontend

<p>
  <a href="../README.md#architecture"><img alt="docs: Architecture" src="https://img.shields.io/badge/docs-Architecture-2F6BFF?logo=readthedocs&logoColor=white"></a>
  <img alt="React: 19" src="https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black">
  <img alt="TypeScript: 5.9" src="https://img.shields.io/badge/TypeScript-5.9-3178C6?logo=typescript&logoColor=white">
  <img alt="Vite: 6" src="https://img.shields.io/badge/Vite-6-646CFF?logo=vite&logoColor=white">
  <img alt="Tailwind CSS: 4" src="https://img.shields.io/badge/Tailwind%20CSS-4-06B6D4?logo=tailwindcss&logoColor=white">
  <img alt="read: 3 min" src="https://img.shields.io/badge/read-3%20min-555555">
</p>

[Docs](../README.md) › [Architecture](../README.md#architecture) › **Frontend** · page 17 of 50

**React 19, TypeScript, Vite, Tailwind CSS v4**, plus Radix primitives, TanStack Query, Zustand, Framer Motion, GSAP, Lenis, Recharts and Lucide.

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
│   ├── graphs/      PlanGraph and CatalogGraph, animated with GSAP
│   ├── tables/      dense data tables
│   ├── docs/        the markdown renderer for the docs browser
│   ├── marketing/   landing-page sections
│   └── shared/      ModeBadge, CacheLayerBadge, CostComparison, EmptyState
├── pages/           one per route, plus landing/
├── hooks/           useQueries (TanStack), useRunStream (SSE)
├── lib/             api client, formatters, docs loader
├── stores/          session
├── animations/      Lenis, Framer variants, GSAP helpers
└── routes/
```

- **Domain components carry the SerpFlow vocabulary:** execution mode, cache layer, warm versus cold, naive versus marginal
- The product concepts appear **consistently**, instead of being re-described on every screen

## No fake data

- **There is no mock layer and no fixture data in the frontend**
- **Every number on every chart was computed by the server**
- **Stored decisions are read, not recomputed:** the Plan Inspector's counterfactual comes from the persisted Plan
  - a recomputation that disagreed with what actually executed would be worse than no display at all

## The pipeline animation

The search page animates **eleven stages**. Each one advances because an SSE frame arrived saying it did:

```
analyzing intent -> finding candidate engines -> synthesizing parameters ->
inferring freshness requirements -> finding valid paths ->
generating candidate plans -> inspecting cache state ->
calculating marginal cost -> re-ranking plans -> checking budget ->
executing required steps
```

- **`useRunStream`** opens an `EventSource`, replays anything it missed from the server-side buffer, then tails live frames
- **No timer, no simulated progression** anywhere in that path. If the backend sits on "inspecting cache state" for two seconds, so does the UI
- **Each stage renders detail straight from the frame's `detail` object:**
  - which engines were retrieved
  - which parameters were bound
  - how many candidates were generated, and how many steps are warm
  - what each candidate costs cold and on the margin

## Animation

| Library | Used for | Reduced motion |
| --- | --- | --- |
| Lenis | Smooth scrolling in the app shell | Never started |
| Framer Motion | Page transitions, dialogs, lists, cards | Variants collapse to instant |
| GSAP | Plan graph edges, catalog graph reveal, counting credit figures, landing-page scroll scenes | Helpers set the end state directly |

- **`prefers-reduced-motion` is honoured in JavaScript**, and again in CSS as a backstop

## Icons

- **Lucide only**
- **No emojis anywhere:** UI, empty states, toasts or documentation
- No decorative sparkle or star glyphs

## Permissions

- **The session store mirrors the server-resolved permission set**, so the UI hides what the caller cannot do instead of offering an action that returns 403
- **The server remains the authority.** This is a usability layer, not a security one

## Data fetching

- **TanStack Query**, with **4xx responses never retried**: the answer will not change, and retrying only delays a clear error
- **Mutations that touch a run invalidate together:** runs, dashboard, savings, cache, budgets, guard rejections, cross-project, audit and alerts

## Routes

```
/                          landing page                     public
/docs/*                    docs browser (this folder)       public
/api                       API reference, from OpenAPI      public

/login  /register  /verify-email  /forgot-password  /reset-password

/app                       overview
/app/search                the central interaction
/app/runs                  run history
/app/runs/:id              Run Inspector
/app/plans  /app/plans/:id Plan Inspector
/app/catalog               Catalog Explorer
/app/cache                 cache dashboard
/app/budgets               budgets and project policy
/app/analytics             savings, engine reach, routing quality, volatility
/app/benchmarks            routing accuracy and failure analysis
/app/audit                 the hash-chained log
/app/settings/*            organization, members, projects, api-keys,
                           credentials, security, notifications
```

- **Everything under `/app` is protected**
- The public pages are covered in [web surface](web.md)

## Related

- [Web surface](web.md): landing page, docs browser, theme and motion
- [Streaming](../api/streaming.md): the SSE contract the pipeline consumes
- [Backend](backend.md)

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Backend](../architecture/backend.md) | [Docs index](../README.md) | [The public web surface](../architecture/web.md) |
