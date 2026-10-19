#!/usr/bin/env node
// Screenshots of website/dist/ with headless Chrome over the DevTools protocol (Node 22+, no npm deps).
//   node website/tools/screenshots.mjs          -> website/screenshots/<page>-<width>-<scheme>.png
//   node website/tools/screenshots.mjs --og     -> re-render website/src/assets/img/og-image.png from tools/og-image.html
// Serves dist/ with tools/serve.py (under the basePath, like GitHub Pages); --og serves website/ with http.server.
//   node website/tools/screenshots.mjs --only home,privacy --width 390 --scheme light   (subset)
// Set CHROME=/path/to/chrome to override the browser.
import { spawn } from "node:child_process";
import { mkdirSync, mkdtempSync, writeFileSync, rmSync, readFileSync, readdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const TOOLS = dirname(fileURLToPath(import.meta.url));
const SITE = dirname(TOOLS);
const CHROME = process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const HTTP_PORT = 8765, CDP_PORT = 9333;
const og = process.argv.includes("--og");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const cfg = JSON.parse(readFileSync(join(SITE, "site-config.json"), "utf8"));
const BASE = (cfg.basePath || "").replace(/^\/*|\/*$/g, "") ? "/" + cfg.basePath.replace(/^\/*|\/*$/g, "") : "";
const arg = (name) => { const i = process.argv.indexOf(name); return i > 0 ? process.argv[i + 1] : null; };
const server = og
  ? spawn("python3", ["-m", "http.server", String(HTTP_PORT), "--bind", "127.0.0.1"], { cwd: SITE, stdio: "ignore" })
  : spawn("python3", [join(TOOLS, "serve.py"), String(HTTP_PORT)], { stdio: "ignore" });
const profile = mkdtempSync(join(tmpdir(), "ae-chrome-"));
const chrome = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${CDP_PORT}`, `--user-data-dir=${profile}`,
  "--no-first-run", "--hide-scrollbars", "--force-device-scale-factor=1", "about:blank"], { stdio: "ignore" });

async function cdpTarget() {
  for (let i = 0; i < 50; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${CDP_PORT}/json`)).json();
      const page = list.find((t) => t.type === "page");
      if (page) return page.webSocketDebuggerUrl;
    } catch {}
    await sleep(200);
  }
  throw new Error("Chrome DevTools did not start");
}

let ws, seq = 0;
const pending = new Map(), waiters = [];
function send(method, params = {}) {
  const id = ++seq;
  ws.send(JSON.stringify({ id, method, params }));
  return new Promise((res, rej) => pending.set(id, { res, rej }));
}
function once(method) { return new Promise((res) => waiters.push({ method, res })); }

async function shot(url, width, height, scheme, out, fullPage = true) {
  await send("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile: width < 600 });
  await send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-color-scheme", value: scheme }] });
  const loaded = once("Page.loadEventFired");
  await send("Page.navigate", { url });
  await loaded;
  await send("Runtime.evaluate", { expression: "document.fonts.ready.then(() => true)", awaitPromise: true });
  await sleep(150);
  let clip;
  if (fullPage) {
    const { result } = await send("Runtime.evaluate", { expression: "document.documentElement.scrollHeight", returnByValue: true });
    clip = { x: 0, y: 0, width, height: Math.max(height, result.value), scale: 1 };
  }
  const { data } = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: fullPage, ...(clip ? { clip } : {}) });
  writeFileSync(out, Buffer.from(data, "base64"));
  console.log("wrote", out);
}

try {
  ws = new WebSocket(await cdpTarget());
  await new Promise((r) => ws.addEventListener("open", r));
  ws.addEventListener("message", (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.id && pending.has(msg.id)) {
      const p = pending.get(msg.id); pending.delete(msg.id);
      msg.error ? p.rej(new Error(msg.error.message)) : p.res(msg.result);
    } else if (msg.method) {
      for (let i = waiters.length - 1; i >= 0; i--) if (waiters[i].method === msg.method) waiters.splice(i, 1)[0].res(msg.params);
    }
  });
  await send("Page.enable");
  await sleep(600); // let the server bind
  const base = `http://127.0.0.1:${HTTP_PORT}`;
  if (og) {
    await shot(`${base}/tools/og-image.html`, 1200, 630, "light", join(SITE, "src/assets/img/og-image.png"), false);
  } else {
    const outDir = join(SITE, "screenshots");
    mkdirSync(outDir, { recursive: true });
    // Legal page paths follow the built output (front matter permalinks).
    const legalDir = (prefix) => readdirSync(join(SITE, "dist")).find((d) => d.startsWith(prefix)) || prefix;
    const pages = { home: "/", support: "/support/", privacy: `/${legalDir("privacy")}/`, terms: "/terms/",
      licenses: "/licenses/", "404": "/no-such-page/" };
    const only = arg("--only")?.split(",");
    const widths = arg("--width") ? [Number(arg("--width"))] : [390, 1280];
    const schemes = arg("--scheme") ? [arg("--scheme")] : ["light", "dark"];
    for (const [name, path] of Object.entries(pages)) {
      if (only && !only.includes(name)) continue;
      for (const width of widths)
        for (const scheme of schemes)
          await shot(base + BASE + path, width, width < 600 ? 844 : 800, scheme, join(outDir, `${name}-${width}-${scheme}.png`));
    }
  }
} finally {
  try { ws?.close(); } catch {}
  chrome.kill(); server.kill();
  await sleep(300);
  rmSync(profile, { recursive: true, force: true });
}
