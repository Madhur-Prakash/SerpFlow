# Frontend

React 19, TypeScript, Vite, Tailwind CSS v4, Radix primitives, TanStack Query,
Zustand, Framer Motion, GSAP, Lenis, Recharts, Lucide.

## What it is not

Not a generic admin dashboard. The target is infrastructure software: an
observability console, a cloud control plane. That means a near-black ground,
one restrained accent, borders doing the structural work instead of shadows,
high information density where it earns its place, and a monospace face for
every identifier, credit figure and engine name so columns of numbers line up
and stay scannable.

## Structure

```
src/
├── components/
│   ├── ui/          Radix behaviour plus Tailwind styling, no wrapper library
│   ├── layout/      AppShell, CommandPalette
│   ├── charts/      Recharts with one palette and one tooltip
│   ├── graphs/      PlanGraph and CatalogGraph, animated with GSAP
│   └── shared/      ModeBadge, CacheLayerBadge, CostComparison, EmptyState
├── pages/           one per route
├── hooks/           useQueries (TanStack), useRunStream (SSE)
├── lib/             api client, formatters
├── stores/          session
├── animations/      Lenis, Framer variants, GSAP helpers
└── routes/
```

Domain components carry the SerpFlow vocabulary: execution mode, cache layer,
warm versus cold, naive versus marginal. The product concepts appear
consistently rather than being re-described on every screen.

## No fake data

There is no mock layer and no fixture data in the frontend. Every number on
every chart was computed by the server. Where a value is a stored decision,
such as the counterfactual in the Plan Inspector, it is read from the persisted
Plan rather than recomputed in the browser, because a recomputation that
disagreed with what actually executed would be worse than no display at all.

## The pipeline animation

The search page animates eleven stages. Each one advances because an SSE frame
arrived saying it did:

```
analyzing intent -> finding candidate engines -> synthesizing parameters ->
inferring freshness requirements -> finding valid paths ->
generating candidate plans -> inspecting cache state ->
calculating marginal cost -> re-ranking plans -> checking budget ->
executing required steps
```

`useRunStream` opens an `EventSource`, replays anything it missed from the
server-side buffer, then tails live frames. There is no timer and no simulated
progression anywhere in that path. If the backend sits on "inspecting cache
state" for two seconds, so does the UI.

Each stage renders detail straight from the frame `detail` object: which
engines were retrieved, which parameters were bound, how many candidates were
generated, how many steps are warm, what each candidate costs cold and on the
margin.

## Animation

| Library | Used for | Reduced motion |
| --- | --- | --- |
| Lenis | Smooth scrolling in the app shell | Never started |
| Framer Motion | Page transitions, dialogs, lists, cards | Variants collapse to instant |
| GSAP | Plan graph edges, catalog graph reveal, counting credit figures | Helpers set the end state directly |

`prefers-reduced-motion` is honoured in JavaScript and again in CSS as a
backstop.

## Icons

Lucide only. No emojis anywhere, in the UI, empty states, toasts or
documentation, and no decorative sparkle or star glyphs.

## Permissions

The session store mirrors the server resolved permission set so the UI can hide
what the caller cannot do rather than offering an action that will return 403.
The server remains the authority; this is a usability layer, not a security
one.

## Data fetching

TanStack Query, with 4xx responses never retried: the answer will not change,
and retrying only delays a clear error message. Mutations that touch a run
invalidate runs, dashboard, savings, cache, budgets, guard rejections,
cross-project, audit and alerts together.

## Routes

```
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

Everything under `/app` is protected.
