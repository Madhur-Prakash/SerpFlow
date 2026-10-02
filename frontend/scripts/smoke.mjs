/**
 * Render the public pages in a real browser and fail on anything broken.
 *
 *     node scripts/smoke.mjs [baseUrl]
 *
 * Checks that matter for a page built out of scroll animations:
 *
 *   - no console errors and no failed requests
 *   - the page has visible text, in both themes
 *   - nothing is left at opacity 0 by a reveal that never ran
 *   - the document is taller than the viewport, so sections actually rendered
 *
 * The last two are the failure mode this kind of UI actually has: a GSAP
 * `set(..., {opacity: 0})` whose ScrollTrigger never fires leaves a section
 * invisible, and every other check still passes.
 */

import { chromium } from "playwright-core";

const BASE = process.argv[2] || "http://localhost:4178";

const PAGES = [
  { path: "/", name: "landing", minHeight: 4000 },
  { path: "/docs", name: "docs index", minHeight: 800 },
  { path: "/docs/architecture/planner", name: "docs page", minHeight: 1200 },
  { path: "/docs/adr/0001-marginal-cost-replanning", name: "adr", minHeight: 900 },
  { path: "/docs/readme:README", name: "repo readme", minHeight: 1200 },
  { path: "/api", name: "api reference", minHeight: 1200 },
];

const IGNORE = [
  /favicon/i,
  /Failed to load resource.*404.*\/v1\//i,
  /net::ERR_CONNECTION_REFUSED.*:8000/i,
];

async function audit(page, target, theme) {
  const errors = [];
  const onConsole = (msg) => {
    if (msg.type() !== "error") return;
    const text = msg.text();
    if (!IGNORE.some((re) => re.test(text))) errors.push(text);
  };
  const onPageError = (error) => errors.push(`uncaught: ${error.message}`);

  page.on("console", onConsole);
  page.on("pageerror", onPageError);

  await page.emulateMedia({ colorScheme: theme });
  await page.goto(BASE + target.path, { waitUntil: "networkidle", timeout: 30_000 });
  await page.waitForTimeout(700);

  // Walk the page so every ScrollTrigger gets a chance to fire.
  await page.evaluate(async () => {
    const step = window.innerHeight * 0.8;
    for (let y = 0; y < document.body.scrollHeight; y += step) {
      window.scrollTo(0, y);
      await new Promise((r) => setTimeout(r, 90));
    }
    window.scrollTo(0, 0);
    await new Promise((r) => setTimeout(r, 300));
  });

  const result = await page.evaluate(() => {
    const text = document.body.innerText.trim();

    // Anything still fully transparent after a full scroll is content the
    // reader will never see.
    const hidden = [];
    for (const el of document.querySelectorAll("[data-reveal], [data-split], main h1, main h2")) {
      const style = getComputedStyle(el);
      if (style.display === "none" || style.visibility === "hidden") continue;
      if (parseFloat(style.opacity) < 0.05 && el.getBoundingClientRect().height > 0) {
        hidden.push((el.textContent || el.tagName).trim().slice(0, 60));
      }
    }

    return {
      textLength: text.length,
      height: document.body.scrollHeight,
      hidden: hidden.slice(0, 6),
      headings: document.querySelectorAll("main h1, main h2").length,
      theme: document.documentElement.dataset.theme,
      ground: getComputedStyle(document.body).backgroundColor,
    };
  });

  page.off("console", onConsole);
  page.off("pageerror", onPageError);
  return { ...result, errors };
}

const browser = await chromium.launch({ channel: "chrome", headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await context.newPage();

let failures = 0;

for (const target of PAGES) {
  for (const theme of ["dark", "light"]) {
    let report;
    try {
      report = await audit(page, target, theme);
    } catch (error) {
      console.log(`  FAIL  ${target.name} [${theme}] - ${error.message.split("\n")[0]}`);
      failures += 1;
      continue;
    }

    const problems = [];
    if (report.errors.length) problems.push(`${report.errors.length} console error(s)`);
    if (report.textLength < 400) problems.push(`only ${report.textLength} chars of text`);
    if (report.height < target.minHeight) {
      problems.push(`height ${report.height} < ${target.minHeight}`);
    }
    if (report.hidden.length) problems.push(`${report.hidden.length} invisible element(s)`);
    if (report.theme !== theme) problems.push(`theme is ${report.theme}, expected ${theme}`);

    const label = `${target.name} [${theme}]`.padEnd(34);
    if (problems.length) {
      failures += 1;
      console.log(`  FAIL  ${label} ${problems.join("; ")}`);
      report.errors.slice(0, 3).forEach((e) => console.log(`          ${e.slice(0, 160)}`));
      report.hidden.forEach((h) => console.log(`          invisible: ${h}`));
    } else {
      console.log(
        `  ok    ${label} ${String(report.height).padStart(6)}px  ` +
          `${String(report.textLength).padStart(6)} chars  ` +
          `${report.headings} headings  ${report.ground}`,
      );
    }
  }
}

await browser.close();

console.log("");
if (failures) {
  console.log(`  ${failures} check(s) failed.`);
  process.exit(1);
}
console.log("  All pages render in both themes.");
