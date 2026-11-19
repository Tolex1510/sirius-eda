import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { openSync, readFileSync, writeFileSync } from "node:fs";
import { chromium } from "@playwright/test";
import assert from "node:assert/strict";
const root = fileURLToPath(new URL("../../", import.meta.url));
const children = [];
let browser;
async function ready(url) {
  for (let i = 0; i < 60; i++) {
    try {
      if ((await fetch(url)).ok) return;
    } catch {}
    await new Promise((r) => setTimeout(r, 300));
  }
  throw new Error("Not ready: " + url);
}
try {
  children.push(
    spawn(root + ".venv/bin/python", ["scripts/lab8_fixture_api.py"], {
      cwd: root,
      stdio: [
        "ignore",
        openSync("/tmp/sirius-lab8-handoff-api.log", "w"),
        "ignore",
      ],
    }),
  );
  await ready("http://127.0.0.1:8092/health");
  children.push(
    spawn(
      process.execPath,
      [
        "node_modules/vite/bin/vite.js",
        "--host",
        "127.0.0.1",
        "--port",
        "5174",
        "--strictPort",
      ],
      {
        cwd: root + "frontend",
        env: { ...process.env, SIRIUS_API_URL: "http://127.0.0.1:8092" },
        stdio: [
          "ignore",
          openSync("/tmp/sirius-lab8-handoff-vite.log", "w"),
          "ignore",
        ],
      },
    ),
  );
  await ready("http://127.0.0.1:5174/");
  browser = await chromium.launch({
    headless: true,
    ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE
      ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE }
      : {}),
  });
  const page = await browser.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("http://127.0.0.1:5174/?item=1");
  await page
    .getByRole("heading", { name: "Ваш вкусный выбор", exact: true })
    .waitFor();
  assert(
    (await page.getByRole("dialog").innerText()).includes(
      "Сырники со сметаной",
    ),
  );
  assert.equal(errors.length, 0);
  assert(!new URL(page.url()).searchParams.has("item"));
  const path = root + "docs/lab8/results/verification.json";
  const report = JSON.parse(readFileSync(path, "utf8"));
  report.checks.spa_handoff_opens_selected_dish = true;
  writeFileSync(path, JSON.stringify(report, null, 2) + "\n");
  console.log(
    "PASS: SSR checkout URL opens selected dish in existing SPA; no payment created",
  );
} finally {
  if (browser) await browser.close();
  for (const p of children.reverse()) {
    p.kill("SIGTERM");
    await new Promise((r) => p.once("exit", r));
  }
}
