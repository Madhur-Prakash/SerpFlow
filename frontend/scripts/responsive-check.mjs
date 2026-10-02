/**
 * Find horizontal overflow at real device widths.
 *
 *     node scripts/responsive-check.mjs [baseUrl]
 *
 * A page that scrolls sideways on a phone is the most common responsive bug
 * and the easiest to miss on a desktop, because nothing looks wrong until the
 * viewport is narrower than the thing that is too wide.
 *
 * For each width this reports whether the document scrolls horizontally, and
 * names the elements whose right edge is past the viewport - skipping those
 * inside an ancestor that legitimately clips or scrolls its own content, so a
 * marquee track or a `overflow-x-auto` table is not reported as a fault.
 */

import { chromium } from "playwright-core";

const BASE = process.argv[2] || "http://localhost:4178";

const WIDTHS = [
  { width: 320, height: 720, label: "320  small phone" },
  { width: 390, height: 844, label: "390  iPhone" },
  { width: 414, height: 896, label: "414  large phone" },
  { width: 768, height: 1024, label: "768  tablet" },
  { width: 1024, height: 768, label: "1024 small laptop" },
];

const PAGES = ["/", "/docs", "/docs/architecture/planner", "/api"];

const findOverflow = () => {
  const vw = document.documentElement.clientWidth;
  const offenders = [];

  const clipped = (el) => {
    let node = el.parentElement;
    while (node && node !== document.body) {
      const style = getComputedStyle(node);
      if (style.overflowX === "hidden" || style.overflowX === "auto" || style.overflowX === "scroll") {
        return true;
      }
      node = node.parentElement;
    }
    return false;
  };

  for (const el of document.querySelectorAll("body *")) {
    const style = getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden") continue;
    if (style.position === "fixed") continue;

    const rect = el.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) continue;
    // 1px of slack: subpixel rounding on borders is not a bug.
    if (rect.right <= vw + 1 && rect.left >= -1) continue;
    if (clipped(el)) continue;

    offenders.push({
      tag: el.tagName.toLowerCase(),
      cls: (typeof el.className === "string" ? el.className : "").slice(0, 70),
      left: Math.round(rect.left),
      right: Math.round(rect.right),
      text: (el.textContent || "").trim().slice(0, 40),
    });
  }

  return {
    vw,
    scrollWidth: document.documentElement.scrollWidth,
    scrolls: document.documentElement.scrollWidth > vw + 1,
    offenders: offenders.slice(0, 6),
  };
};

const browser = await chromium.launch({ channel: "chrome", headless: true });
let failures = 0;

console.log("");
for (const page of PAGES) {
  console.log("  " + page);
  for (const size of WIDTHS) {
    const context = await browser.newContext({
      viewport: { width: size.width, height: size.height },
      isMobile: size.width < 768,
      hasTouch: size.width < 768,
    });
    const tab = await context.newPage();
    await tab.goto(BASE + page, { waitUntil: "networkidle", timeout: 30_000 });
    await tab.waitForTimeout(900);
    // Scroll through, so lazily revealed sections are measured too.
    await tab.evaluate(async () => {
      const step = window.innerHeight * 0.8;
      for (let y = 0; y < document.body.scrollHeight; y += step) {
        window.scrollTo(0, y);
        await new Promise((r) => setTimeout(r, 60));
      }
      window.scrollTo(0, 0);
      await new Promise((r) => setTimeout(r, 200));
    });

    const result = await tab.evaluate(findOverflow);
    const label = size.label.padEnd(20);

    if (result.scrolls || result.offenders.length) {
      failures += 1;
      console.log(
        `    FAIL  ${label} scrollWidth ${result.scrollWidth} > ${result.vw}`,
      );
      for (const o of result.offenders) {
        console.log(
          `            <${o.tag}> right=${o.right} "${o.cls}" ${o.text ? "| " + o.text : ""}`,
        );
      }
    } else {
      console.log(`    ok    ${label} ${result.scrollWidth}px`);
    }

    await context.close();
  }
}

await browser.close();
console.log("");
if (failures) {
  console.log(`  ${failures} viewport(s) overflow horizontally.`);
  process.exit(1);
}
console.log("  No horizontal overflow at any tested width.");
