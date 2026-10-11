# The public web surface

<p>
  <a href="../architecture/README.md"><img alt="docs: Architecture" src="https://img.shields.io/badge/docs-Architecture-2F6BFF?logo=readthedocs&logoColor=white"></a>
  <img alt="React: 19" src="https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black">
  <img alt="GSAP: ScrollTrigger" src="https://img.shields.io/badge/GSAP-ScrollTrigger-88CE02?logo=greensock&logoColor=black">
  <img alt="Tailwind CSS: 4" src="https://img.shields.io/badge/Tailwind%20CSS-4-06B6D4?logo=tailwindcss&logoColor=white">
  <a href="../../frontend/src/routes/index.tsx"><img alt="source: routes/index.tsx" src="https://img.shields.io/badge/source-routes%2Findex.tsx-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 12 min" src="https://img.shields.io/badge/read-12%20min-555555">
</p>

[Docs](../README.md) › [Architecture](../architecture/README.md) › **The public web surface** · page 22 of 50

**Three pages share one shell:** the landing page, the documentation browser and the API reference. The signed-in console is the [frontend](frontend.md).

- The three pages are **lazy-loaded chunks**, separate from the console ([`routes/index.tsx`](../../frontend/src/routes/index.tsx))
- A user who goes straight to `/app` does not download the landing page, the docs tree or the API reference; only the `MarketingLayout` shell, and Lenis in the shared `motion` vendor chunk ([`vite.config.ts`](../../frontend/vite.config.ts)), load with the console

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
- **Switching uses the View Transitions API** ([`lib/theme.ts`](../../frontend/src/lib/theme.ts)): the new theme grows as a circle from the control that was pressed

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

- **GSAP with ScrollTrigger, SplitText and DrawSVG, loaded on demand** by `loadScrollTools()`, once, so the plugins split into their own chunks:

```
ScrollTrigger  44 kB    SplitText  7.4 kB    DrawSVGPlugin  4 kB
```

- **The console uses the same loader** for its card rise and figure counters ([frontend: animation](frontend.md#animation)), so a signed-in user fetches these chunks on first navigation too. GSAP core is in the main bundle, for the plan graph
- **Every hook in `animations/scroll.ts` is a no-op under reduced motion** (the OS setting, or the in-app preference), and leaves elements in their **finished** state, not their starting one
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

- **The thesis section is the one piece of real scroll choreography:** four beats, pinned, **scrubbed rather than played** ([`ThesisStory.tsx`](../../frontend/src/pages/landing/ThesisStory.tsx))
- It tells [the thesis](../product/product-overview.md#the-thesis): ranking on [marginal cost instead of cold cost](marginal-replanning.md#the-distinction) changes which plan is selected
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

Code: [`hooks/useSmoothScroll.ts`](../../frontend/src/hooks/useSmoothScroll.ts) · [`lib/scroll.ts`](../../frontend/src/lib/scroll.ts)

- **Lenis, on the public pages only:** `MarketingLayout` calls `useSmoothScroll()`, and nothing else does
- It drives the **native window scroll**, not a transformed container, so `position: sticky`, ScrollTrigger pinning, find-in-page and the real scrollbar all keep working
- **Never started under reduced motion**, whether from the OS setting or the in-app preference
- **Anything that scrolls on its own is left alone:** dialogs, listboxes, menus, Radix popovers, the command palette's list, `pre` blocks and anything marked `data-lenis-prevent`
- **Lenis pauses** while Radix marks `<body data-scroll-locked>`, or it would keep driving the page behind an open dialog
- **Programmatic scrolling goes through `lib/scroll.ts`** (`scrollToElement`, `scrollToTop`, `scrollToAnchor`), never a raw `window.scrollTo`, which would fight Lenis and land between the two positions
  - targets clear the sticky header by an 88 px offset
  - `lenis.resize()` runs first, because Lenis caches the document height and content loaded since would clamp the target short
  - a route change starts at the top; a hash scrolls to its section once the page has rendered, and moves focus there
- **The console scrolls natively**, inside its own container ([frontend: animation](frontend.md#animation))
  - Lenis was removed from the app shell because it cached the first page's height, so a taller page stopped short
  - and an operator scanning a run table wants the position their pointer asked for, not an eased approximation

## The documentation browser

Code: [`lib/docs.ts`](../../frontend/src/lib/docs.ts) · [`pages/DocsPage.tsx`](../../frontend/src/pages/DocsPage.tsx) · [`components/docs/Markdown.tsx`](../../frontend/src/components/docs/Markdown.tsx)

- **`import.meta.glob("../../../docs/**/*.md")`** reads the repository's own markdown at build time
  - so the published site and the committed files **cannot describe different systems**
  - the four root files, `README.md`, `CONTRIBUTING.md`, `SECURITY.md` and `CHANGELOG.md`, are read the same way and listed under **Repository**, at `/docs/readme:NAME`
- **Each file is a separate dynamic import**, one chunk per page, so opening one page does not download the rest
- **The sidebar follows the docs index:** sections in the order of [`docs/README.md`](../README.md), pages inside them in the reading order `make docs-nav` writes to [`docs-order.generated.ts`](../../frontend/src/lib/docs-order.generated.ts)
  - the previous / next pager walks the same order, so it agrees with the footer on every page
  - a page missing from the order sorts last; a page in an unlisted folder lands under **More**, still reachable
  - the sidebar filters by title or path; an "On this page" contents list appears when a page has two or more headings, and a link opens the source file on GitHub
- **Rendered by [`components/docs/Markdown.tsx`](../../frontend/src/components/docs/Markdown.tsx)**, covering exactly the subset these docs use
  - **nothing is rendered as raw HTML:** inline markup is parsed into React elements, so a stray `<script>` is text by construction, not by filtering
  - **a small HTML whitelist** (`p`, `a`, `img`, `div`, tables and a few more) is parsed into elements too. That is how the badge headers render. Unknown tags become their text; unknown attributes are dropped; an `img` renders only from an `http(s)` source
  - **headings get GitHub-style ids**, the same slugs the link checker verifies, so `#anchor` links work in both places
  - **not supported:** HTML comments (they render as text), task-list checkboxes, inline images in markdown syntax

### How links resolve

`resolveDocLink(href, fromSlug)` turns a link written for GitHub into one the app can follow:

- **Absolute URLs** are left alone and open in a new tab; **`#anchor`** links stay on the page
- **Everything else resolves in repository coordinates, against the file the link is written in**, not against the URL
  - the file matters, not the slug: `/docs/architecture` is `docs/architecture/README.md`, so its links resolve from `docs/architecture/`
  - and `../README.md` from a section page is the docs index, not the project README

| The link lands on | Opens as |
| --- | --- |
| a `.md` page or a folder under `docs/` | `/docs/<slug>`, in the browser; a `README.md` is its folder's index |
| `README.md`, `CONTRIBUTING.md`, `SECURITY.md` or `CHANGELOG.md` at the root | `/docs/readme:NAME`, in the browser |
| anything else: `backend/`, `frontend/`, `sdk/`, `scripts/`, `docker/`, `.env.example`, `Makefile`, `LICENSE` | the file on GitHub, `Madhur-Prakash/SerpFlow`, branch `main`, in a new tab |

- The fragment is kept in every case, so the same markdown works on GitHub and in the app
- **Container deployments:** deep links under `/docs/*` currently hit an nginx proxy rule. See [Docker: known issue](../deployment/docker.md#known-issue-docs-deep-links)

### Generated parts, and the checker

- **Every page's badge header, breadcrumb and previous / next footer are generated** by `make docs-nav` ([`scripts/build_docs_nav.py`](../../scripts/build_docs_nav.py)), in one reading order
  - the badges: the section, facts about the page's subject, the stack it covers, the first source file the body links to, and a reading time at 200 words a minute, code blocks excluded
  - the breadcrumb: back to the index and section, with the page's place in the order
  - the footer: previous, index, next
  - rerunning replaces the generated blocks instead of appending; `make docs-nav ARGS=--check` exits non-zero if any page is stale, or if a page is missing from the order
  - it also writes `docs-order.generated.ts`, which is how the app's sidebar and pager stay in step
- **`make docs-check`** ([`scripts/check_doc_links.py`](../../scripts/check_doc_links.py)) fails on any relative link that does not resolve, in every markdown file in the repository
  - it also checks backticked paths such as `backend/app/core/text.py` and `app/services/planner/cost.py`, because a doc that names a file it does not link is just as wrong when that file moves
  - `--anchors` also checks every `#fragment` against the target's headings
  - `--interlinks` requires every page to end with a `## Related` of at least three links and to be linked from another page's body, and lists one-way Related links

## The API reference

**Generated, not written:**

```bash
make api-reference                  # from a running API (localhost:8000/openapi.json)
make api-reference ARGS=--offline   # imports the app and asks FastAPI for the schema, no server
```

- [`scripts/generate_api_reference.py`](../../scripts/generate_api_reference.py) reads the OpenAPI document and writes [`api-reference.generated.ts`](../../frontend/src/lib/api-reference.generated.ts): every operation with its parameters, body and responses, grouped by tag, plus the operation and path counts
  - a tag the script does not name still renders, at the end, so a new router appears without editing it
- [`pages/ApiReferencePage.tsx`](../../frontend/src/pages/ApiReferencePage.tsx) renders it with a filter; nothing on the page is typed by hand
- **A hand-maintained list of [85 operations across 74 paths](../api/overview.md) goes stale.** This one describes the schema as of its last generation, so rerun it after changing a router
- To exercise every operation against a running instance, see [checking every operation](../api/overview.md#checking-every-operation)

## Verifying it

```bash
make test-ui
```

Renders the public pages in a real browser, in **both themes**: the landing page, the docs index, a docs page, a section index, the project README at `/docs/readme:README`, and the API reference ([`smoke.mjs`](../../frontend/scripts/smoke.mjs)). It fails on:

- any console error, failed resource loads included, or uncaught exception
- a page with less than 400 characters of text
- a document shorter than that page's minimum height, which means sections did not render
- a page whose resolved theme is not the one requested
- any `[data-reveal]` element still at opacity 0 after a full scroll

Why that last check:

- **it is the failure mode this kind of interface actually has**
- a `gsap.set(el, { opacity: 0 })` whose ScrollTrigger never fires leaves a section invisible, and every other check still passes

A second check walks the pinned thesis story:

- it asserts the beat counter, the progress rail and the cards agree
- so Plan B is never shown as selected while the counter still reads an earlier beat
- the timeline is one unit per beat precisely so that cannot drift

A third looks for horizontal overflow at 320, 390, 414, 768 and 1024 px on the landing page, the docs and the API reference, and names the elements past the viewport edge ([`responsive-check.mjs`](../../frontend/scripts/responsive-check.mjs)).

**It is one script**, [`frontend/scripts/verify-ui.mjs`](../../frontend/scripts/verify-ui.mjs): it builds, starts the preview server, runs all three checks and tears it down.

- A `make` recipe that backgrounds a server, sleeps and kills it by pid depends on shell quoting, line continuations and line endings all being right at once. On Windows they are not
- **It runs against `vite preview`, not nginx**, so it does not exercise the container's proxy rules
- It needs Google Chrome installed: [troubleshooting](../operations/troubleshooting.md#make-test-ui-cannot-launch-a-browser)

## Related

- [Frontend](frontend.md): the console, its native scrolling and its smaller motion vocabulary
- [Product overview](../product/product-overview.md): the argument the landing page tells on scroll
- [Marginal-cost replanning](marginal-replanning.md#worked-example-the-reference-demo): the selection change the pinned story animates
- [API overview](../api/overview.md): the operations the generated reference lists
- [Docker: known issue](../deployment/docker.md#known-issue-docs-deep-links): `/docs` deep links behind nginx
- [Troubleshooting: frontend](../operations/troubleshooting.md#frontend): build, animation and `make test-ui` failures

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Frontend](../architecture/frontend.md) | [Docs index](../README.md) · [Architecture index](../architecture/README.md) | [API index](../api/README.md) |
