/**
 * Build, serve, check, tear down.
 *
 *     node scripts/verify-ui.mjs
 *
 * Owning the preview server here rather than in the Makefile keeps the whole
 * thing in one language. A multi-line `make` recipe that backgrounds a server,
 * sleeps, runs two checks and then kills it by pid depends on shell quoting,
 * line continuations and line endings all being right at once, and on Windows
 * they are not.
 */

import { spawn } from "node:child_process";
import { once } from "node:events";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";

const PORT = 4178;
const BASE = `http://localhost:${PORT}`;
const CHECKS = [
  "scripts/smoke.mjs",
  "scripts/story-check.mjs",
  "scripts/responsive-check.mjs",
];

// Vite's JS entry, reached by path rather than by `npx`: Node refuses to
// spawn a .cmd without a shell, and going through one would put Windows
// quoting back into the picture - the thing this script exists to avoid.
// `require.resolve` is no use here because vite's package exports do not list
// ./bin/vite.js.
const VITE = fileURLToPath(new URL("../node_modules/vite/bin/vite.js", import.meta.url));
if (!existsSync(VITE)) {
  console.error("\n  vite is not installed. Run `npm install` in frontend/ first.\n");
  process.exit(1);
}
const node = process.execPath;

function run(command, args) {
  const child = spawn(command, args, { stdio: "inherit", shell: false });
  return once(child, "close").then(([code]) => code ?? 1);
}

async function waitForServer(timeoutMs = 30_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(BASE + "/", { signal: AbortSignal.timeout(2000) });
      if (response.ok) return true;
    } catch {
      // Not up yet.
    }
    await new Promise((resolve) => setTimeout(resolve, 400));
  }
  return false;
}

const buildCode = await run(node, [VITE, "build"]);
if (buildCode !== 0) process.exit(buildCode);

const preview = spawn(node, [VITE, "preview", "--port", String(PORT), "--strictPort"], {
  stdio: "ignore",
  shell: false,
  detached: process.platform !== "win32",
});

let status = 1;
try {
  if (!(await waitForServer())) {
    console.error(`\n  The preview server did not come up on ${BASE}.`);
    status = 1;
  } else {
    status = 0;
    for (const check of CHECKS) {
      const code = await run(node, [check, BASE]);
      if (code !== 0) status = code;
    }
  }
} finally {
  // On Windows a detached tree needs taskkill; elsewhere the process group.
  try {
    if (process.platform === "win32") {
      spawn("taskkill", ["/pid", String(preview.pid), "/T", "/F"], { stdio: "ignore" });
    } else {
      process.kill(-preview.pid, "SIGTERM");
    }
  } catch {
    // Already gone.
  }
}

process.exit(status);
