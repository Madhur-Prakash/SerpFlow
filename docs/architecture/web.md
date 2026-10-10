# The public web surface

<p>
  <a href="../README.md#architecture"><img alt="docs: Architecture" src="https://img.shields.io/badge/docs-Architecture-2F6BFF?logo=readthedocs&logoColor=white"></a>
  <img alt="React: 19" src="https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black">
  <img alt="GSAP: ScrollTrigger" src="https://img.shields.io/badge/GSAP-ScrollTrigger-88CE02?logo=greensock&logoColor=black">
  <img alt="Tailwind CSS: 4" src="https://img.shields.io/badge/Tailwind%20CSS-4-06B6D4?logo=tailwindcss&logoColor=white">
  <a href="../../frontend/src/components/layout/MarketingLayout.tsx"><img alt="source: layout/MarketingLayout.tsx" src="https://img.shields.io/badge/source-layout%2FMarketingLayout.tsx-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 6 min" src="https://img.shields.io/badge/read-6%20min-555555">
</p>

[Docs](../README.md) › [Architecture](../README.md#architecture) › **The public web surface** · page 18 of 50

**Three pages share one shell:** the landing page, the documentation browser and the API reference.

- They are a **separate bundle** from the console
- Nothing in them loads for a user who goes straight to `/app`

```
/           landing          the argument, told on scroll
/docs/*     documentation    rendered from the repository's own docs/
/api        API reference    generated from the OpenAPI schema
```

Implementation: [`MarketingLayout.tsx`](../../frontend/src/components/layout/MarketingLayout.tsx) · [`components/marketing/`](../../frontend/src/components/marketing) · [`pages/landing/`](../../frontend/src/pages/landing) · [`animations/scroll.ts`](../../frontend/src/animations/scroll.ts)

## Width

- **One container, `.page-shell`**, defined once in [`globals.css`](../../frontend/src/styles/globals.css) instead of repeated as a utility string, so the site's width is a single decision:

```css
.page-shell {
  width: 100%;
  margin-inline: auto;
  max-width: 90rem;
  padding-inline: 1.25rem;  /* 2rem at 640, 2.5rem at 1024, 3.5rem at 1536 */
}
```

- **90rem, not Tailwind's `max-w-7xl` (80rem):** on an 1800px display the narrower cap leaves ~260px of empty gutter each side, which reads as a floating column, not a page
- **The docs and API reference add `.page-shell-wide` (96rem)**, because they run a sidebar beside the content

## Theme

- **Three states, not two:** `dark`, `light` and `system`
- **The default is `system`**: a plain dark/light switch strands anyone whose machine changes at sunset
- **No flash on load:** the resolved value is a class on `<html>`, and an inline script in [`index.html`](../../frontend/index.html) applies the stored value **before the first paint**
  - without it, a light-theme reader gets a full-screen flash of the dark ground on every load, because React runs after the browser paints
- **Switching uses the View Transitions API:** the new theme grows as a circle from the control that was pressed

```ts
const transition = doc.startViewTransition(apply);
transition.ready.then(() =>
  root.animate(
    { clipPath: [`circle(0px at ${x}px ${y}px)`, `circle(${radius}px at ${x}px ${y}px)`] },
    { duration: 620, pseudoElement: "::view-transition-new(root)" },
  ),
);
```

- **`flushSync` wraps the state change**, because the transition snapshots the DOM synchronously after that callback
  - a render scheduled for later would land in the "before" frame, and the transition would animate nothing
- **Fallbacks:** browsers without the API get a colour crossfade; reduced motion switches **instantly**, since a full-page wipe is exactly what that setting exists to avoid
- **The light theme is not a tinted inversion:**
  - the accent moves from `oklch(0.692 0.168 248)` to `oklch(0.62 0.21 255)`, because the dark theme's blue fails contrast on white
  - the semantic colours gain chroma
  - shadows take over the structural work borders do on a dark ground: a 1px line that reads as structure at 14% lightness disappears at 97%

## Motion

- **GSAP with ScrollTrigger, SplitText and DrawSVG, loaded on demand**
- The console never imports them, so they split into their own chunks:

```
ScrollTrigger  44 kB    SplitText  7.4 kB    DrawSVGPlugin  4 kB
```

- **Every hook in `animations/scroll.ts` is a no-op under reduced motion**, and leaves elements in their **finished** state, not their starting one
  - that ordering matters: an animation that never runs must not leave content invisible

| Hook | What it does |
| --- | --- |
| `useReveal` | Fades and lifts `[data-reveal]` children in document order as a section crosses the fold |
| `useTextReveal` | Splits a heading into lines and words; words rise out of a mask |
| `useParallax` | Moves `[data-parallax]` against the scroll, scaled by a per-element depth |
| `useCounters` | Counts `[data-count]` up when it enters view |
| `useMagnetic` | Pulls a control toward the pointer, and releases it elastically |
| `usePinnedStory` | Pins a section and scrubs a timeline across it |
| `useBackdropDrift` | Scales and fades a section's backdrop as it enters |

- **Every hook runs inside `gsap.context()`**, scoped to the section's ref, and reverts on unmount
  - that makes them safe under React strict mode and route changes: a remount cannot leave an orphaned ScrollTrigger measuring a detached node

### The pinned story

- **The thesis section is the one piece of real scroll choreography:** four beats, pinned, **scrubbed rather than played**
- Scrolling back runs it in reverse, and a reader can hold the moment the selection changes

```
beat 1   two candidate plans appear
beat 2   the cold ranking rings Plan A, the cheaper one
beat 3   a warm-up sweeps across Plan B's steps
beat 4   the ring moves to Plan B and the marginal column takes over
```

- **Below 1024px, and under reduced motion,** the same content renders top to bottom in its final state
- **The claim does not depend on the animation**

### Smooth scrolling

- **Lenis, on the public pages only**
- It drives the **native window scroll**, not a transformed container, so `position: sticky`, ScrollTrigger pinning, find-in-page and the real scrollbar all keep working
- **The console keeps plain native scrolling:** an operator scanning a run table wants the position their pointer asked for, not an eased approximation
- **Lenis pauses** while Radix marks `<body data-scroll-locked>`, or it would keep driving the page behind an open dialog

## The documentation browser

- **`import.meta.glob("../../../docs/**/*.md")`** reads the repository's own markdown at build time
  - so the published site and the committed files **cannot describe different systems**
- **Each file is a separate dynamic import** (55 chunks), so opening one page does not download the rest
- **Rendered by [`components/docs/Markdown.tsx`](../../frontend/src/components/docs/Markdown.tsx)**, covering exactly the subset these docs use
  - **nothing is rendered as raw HTML:** inline markup is parsed into React elements, so a stray `<script>` is text by construction, not by filtering
  - **a small HTML whitelist** (`p`, `a`, `img`, `div`, tables and a few more) is parsed into elements too. That is how the badge headers render. Unknown tags become their text; unknown attributes are dropped
  - **not supported:** HTML comments (they render as text), task-list checkboxes, inline images in markdown syntax
- **Links are rewritten by `resolveDocLink`**
  - a relative path like `../database/rls.md` resolves against the current document and maps onto `/docs/...`
  - paths that leave `docs/` for source files become GitHub links
  - so the same markdown works on GitHub and in the app
- **Every page's badge header, breadcrumb and previous/next footer are generated** by `make docs-nav` ([`scripts/build_docs_nav.py`](../../scripts/build_docs_nav.py)), in one reading order
- **Container deployments:** deep links under `/docs/*` currently hit an nginx proxy rule. See [Docker: known issue](../deployment/docker.md#known-issue-docs-deep-links)

## The API reference

**Generated, not written:**

```bash
make api-reference                  # from a running API
make api-reference ARGS=--offline   # from the app, no server
```

- [`scripts/generate_api_reference.py`](../../scripts/generate_api_reference.py) reads the OpenAPI document and emits a typed data file
- A hand-maintained list of **85 operations across 74 paths** goes stale; this one cannot describe an endpoint that does not exist

## Verifying it

```bash
make test-ui
```

Renders every public page in a real browser, in **both themes**, and fails on:

- any console error or uncaught exception
- a page with less than 400 characters of text
- a document shorter than the section count implies
- any `[data-reveal]` element still at opacity 0 after a full scroll

Why that last check:

- **it is the failure mode this kind of interface actually has**
- a `gsap.set(el, { opacity: 0 })` whose ScrollTrigger never fires leaves a section invisible, and every other check still passes

A second check walks the pinned thesis story:

- it asserts the beat counter, the progress rail and the cards agree
- so Plan B is never shown as selected while the counter still reads an earlier beat
- the timeline is one unit per beat precisely so that cannot drift

**It is one script**, [`frontend/scripts/verify-ui.mjs`](../../frontend/scripts/verify-ui.mjs): it builds, starts the preview server, runs both checks and tears it down.

- A `make` recipe that backgrounds a server, sleeps and kills it by pid depends on shell quoting, line continuations and line endings all being right at once. On Windows they are not
- **It runs against `vite preview`, not nginx**, so it does not exercise the container's proxy rules

## Related

- [Frontend architecture](frontend.md): the console
- [Product overview](../product/product-overview.md)

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Frontend](../architecture/frontend.md) | [Docs index](../README.md) | [API overview](../api/overview.md) |
