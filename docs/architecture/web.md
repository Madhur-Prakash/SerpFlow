# The public web surface

Three pages share one shell: the landing page, the documentation browser and
the API reference. They are a separate bundle from the console, and nothing in
them loads for a user who goes straight to `/app`.

```
/           landing          the argument, told on scroll
/docs/*     documentation    rendered from the repository's own docs/
/api        API reference    generated from the OpenAPI schema
```

Implementation:
[`components/layout/MarketingLayout.tsx`](../../frontend/src/components/layout/MarketingLayout.tsx),
[`components/marketing/`](../../frontend/src/components/marketing),
[`pages/landing/`](../../frontend/src/pages/landing),
[`animations/scroll.ts`](../../frontend/src/animations/scroll.ts).

## Theme

Three states, not two: `dark`, `light` and `system`. The default is `system`,
because a plain dark/light switch strands anyone whose machine changes at
sunset.

The resolved value is a class on `<html>`, and an inline script in
[`index.html`](../../frontend/index.html) applies the stored value **before the
first paint**. Without that, a reader on the light theme gets a full-screen
flash of the dark ground on every load, because React cannot run until after
the browser has painted.

Switching uses the View Transitions API: the new theme grows as a circle from
the control that was pressed.

```ts
const transition = doc.startViewTransition(apply);
transition.ready.then(() =>
  root.animate(
    { clipPath: [`circle(0px at ${x}px ${y}px)`, `circle(${radius}px at ${x}px ${y}px)`] },
    { duration: 620, pseudoElement: "::view-transition-new(root)" },
  ),
);
```

`flushSync` wraps the state change, because the transition snapshots the DOM
synchronously after that callback - a render scheduled for later would be
captured in the "before" frame and the transition would animate nothing.
Browsers without the API get a colour crossfade; reduced motion switches
instantly, since a full-page wipe is exactly what that setting exists to avoid.

The light theme is not a tinted inversion. The accent darkens from
`oklch(0.682 0.153 248)` to `oklch(0.525 0.182 253)` because the dark theme's
blue fails contrast on white, the semantic colours gain chroma, and the shadows
take over the structural work that borders do on a dark ground - a 1px line
that reads as structure at 14% lightness disappears at 97%.

## Motion

GSAP with ScrollTrigger, SplitText and DrawSVG, **loaded on demand**. The
console never imports them, so they split into their own chunks:

```
ScrollTrigger  44 kB    SplitText  7.4 kB    DrawSVGPlugin  4 kB
```

Every hook in `animations/scroll.ts` is a no-op under reduced motion, and leaves
elements in their finished state rather than their starting one. That ordering
matters: an animation that never runs must not leave content invisible.

| Hook | What it does |
| --- | --- |
| `useReveal` | Fades and lifts `[data-reveal]` children in document order as a section crosses the fold |
| `useTextReveal` | Splits a heading into lines and words; words rise out of a mask |
| `useParallax` | Moves `[data-parallax]` against the scroll, scaled by a per-element depth |
| `useCounters` | Counts `[data-count]` up when it enters view |
| `useMagnetic` | Pulls a control toward the pointer, and releases it elastically |
| `usePinnedStory` | Pins a section and scrubs a timeline across it |
| `useBackdropDrift` | Scales and fades a section's backdrop as it enters |

Every one runs inside `gsap.context()` scoped to the section's ref and reverts
on unmount. That is what makes them safe under React strict mode and route
changes: a remount cannot leave an orphaned ScrollTrigger measuring a detached
node.

### The pinned story

The thesis section is the one piece of real scroll choreography. Four beats,
pinned, **scrubbed rather than played** - so scrolling back runs it in reverse
and a reader can hold the moment the selection changes.

```
beat 1   two candidate plans appear
beat 2   the cold ranking rings Plan A, the cheaper one
beat 3   a warm-up sweeps across Plan B's steps
beat 4   the ring moves to Plan B and the marginal column takes over
```

Below 1024px, and under reduced motion, the same content renders top to bottom
in its final state. The claim does not depend on the animation.

### Smooth scrolling

Lenis, on the public pages only. It drives the native window scroll rather than
a transformed container, so `position: sticky`, ScrollTrigger's pinning, native
find-in-page and the real scrollbar all keep working.

The console keeps plain native scrolling: an operator scanning a run table
wants the position their pointer asked for, not an eased approximation of it.

Lenis pauses while Radix marks `<body data-scroll-locked>`, or it would keep
driving the page behind an open dialog.

## The documentation browser

`import.meta.glob("../../../docs/**/*.md")` reads the repository's own markdown
at build time, so the published site and the committed files cannot describe
different systems. Each file is a separate dynamic import - 53 chunks - so
opening one page does not download the rest.

Markdown is rendered by
[`components/docs/Markdown.tsx`](../../frontend/src/components/docs/Markdown.tsx),
which covers exactly the subset these docs use. **Nothing is rendered as raw
HTML**: inline markup is parsed into React elements, so a stray `<script>` in a
document is text by construction rather than by filtering.

Links are rewritten by `resolveDocLink`, which resolves a relative path like
`../database/rls.md` against the current document and maps it onto `/docs/...`.
Paths that leave `docs/` and point at source files become GitHub links. The
same markdown therefore works on GitHub and in the app.

## The API reference

Generated, not written:

```bash
make api-reference            # from a running API
make api-reference ARGS=--offline   # from the app, no server
```

[`scripts/generate_api_reference.py`](../../scripts/generate_api_reference.py)
reads the OpenAPI document and emits a typed data file. A hand-maintained list
of 78 operations across 69 paths is a list that goes stale; this one cannot
describe an endpoint that does not exist.

## Verifying it

```bash
make test-ui
```

Renders every public page in a real browser, in **both themes**, and fails on:

- any console error or uncaught exception
- a page with less than 400 characters of text
- a document shorter than the section count implies
- any `[data-reveal]` element still at opacity 0 after a full scroll

That last check is the failure mode this kind of interface actually has. A
`gsap.set(el, { opacity: 0 })` whose ScrollTrigger never fires leaves a section
invisible, and every other check still passes.

## Related

- [Frontend architecture](frontend.md) - the console
- [Product overview](../product/product-overview.md)
