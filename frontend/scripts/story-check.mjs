import { chromium } from "playwright-core";

const BASE = process.argv[2] || "http://localhost:4178";

const probe = () => {
  const opacity = (sel) => {
    const el = document.querySelector(sel);
    if (!el) return -1;
    return Math.round(parseFloat(getComputedStyle(el).opacity) * 100);
  };

  const counter =
    [...document.querySelectorAll("span")]
      .map((e) => (e.textContent || "").trim())
      .find((t) => /^0\d \/ 0\d$/.test(t)) || "-";

  const rail = [...document.querySelectorAll("span")]
    .filter((e) => e.className && String(e.className).includes("from-accent to-warm"))
    .map((e) => Math.round(parseFloat(e.style.width) || 0));

  const sweep = document.querySelector("[data-warm-sweep]");
  const sweepPct = sweep
    ? Math.round(
        (new DOMMatrixReadOnly(getComputedStyle(sweep).transform).a || 0) * 100,
      )
    : -1;

  const activeBeat =
    [...document.querySelectorAll("ol li h3")]
      .map((h, i) => ({ i, text: h.textContent.trim(), op: parseFloat(getComputedStyle(h.closest("li")).opacity) }))
      .filter((x) => x.op > 0.9)
      .pop() || { i: -1, text: "-" };

  return {
    counter,
    rail,
    sweepPct,
    coldBadge: opacity('[data-winner="cold"]'),
    selected: opacity('[data-winner="marginal"]'),
    activeBeat: activeBeat.i + 1,
    beatText: activeBeat.text,
  };
};

const browser = await chromium.launch({ channel: "chrome", headless: true });
const context = await browser.newContext({ viewport: { width: 1536, height: 864 } });
const page = await context.newPage();

await page.emulateMedia({ colorScheme: "light" });
await page.goto(BASE + "/", { waitUntil: "networkidle" });
await page.waitForTimeout(2600);

console.log("");
console.log("  scrollY | counter | beat | cold | sel | sweep | rail");
console.log("  " + "-".repeat(72));

let failures = 0;
for (const y of [3000, 3700, 4400, 5100, 5800, 6400]) {
  await page.evaluate(async (target) => {
    const from = window.scrollY;
    const step = (target - from) / 16;
    for (let i = 1; i <= 16; i += 1) {
      window.scrollTo(0, from + step * i);
      await new Promise((r) => setTimeout(r, 50));
    }
  }, y);
  await page.waitForTimeout(650);

  const s = await page.evaluate(probe);
  console.log(
    "  " +
      String(y).padStart(7) +
      " | " +
      s.counter.padEnd(7) +
      " | " +
      String(s.activeBeat).padStart(4) +
      " | " +
      String(s.coldBadge).padStart(4) +
      " | " +
      String(s.selected).padStart(3) +
      " | " +
      String(s.sweepPct).padStart(5) +
      " | " +
      JSON.stringify(s.rail),
  );

  // The counter and the cards must agree: "selected" may only be visible once
  // the counter has reached the final beat.
  const beatNumber = Number((s.counter.split(" / ")[0] || "0").trim());
  if (s.selected > 50 && beatNumber < 4) {
    console.log("        FAIL: Plan B selected while the counter reads " + s.counter);
    failures += 1;
  }
  if (s.coldBadge > 50 && s.selected > 50) {
    console.log("        FAIL: both winner badges visible at once");
    failures += 1;
  }
}

await browser.close();
console.log("");
console.log(failures ? `  ${failures} inconsistency found.` : "  Counter and cards agree throughout.");
process.exit(failures ? 1 : 0);
