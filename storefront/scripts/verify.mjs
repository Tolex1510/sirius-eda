import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import {
  mkdirSync,
  writeFileSync,
  openSync,
  readFileSync,
  existsSync,
  rmSync,
  cpSync,
} from "node:fs";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";
const root = fileURLToPath(new URL("../../", import.meta.url));
const out = root + "docs/lab8/results/";
mkdirSync(out, { recursive: true });
const python = process.env.LAB8_PYTHON || root + ".venv/bin/python";
const api = "http://127.0.0.1:8092",
  site = "http://127.0.0.1:3001";
let backend, next, browser;
const isrOnly = process.argv.includes("--isr-only");
const previous =
  isrOnly && existsSync(out + "verification.json")
    ? JSON.parse(readFileSync(out + "verification.json", "utf8"))
    : null;
const report = previous || {
  checked_at: new Date().toISOString(),
  mode: "Next.js production; real FastAPI with isolated in-memory repositories",
  checks: {},
  measurements: [],
};
const delay = (ms) => new Promise((r) => setTimeout(r, ms));
async function ready(url) {
  for (let i = 0; i < 60; i++) {
    try {
      if ((await fetch(url)).ok) return;
    } catch {}
    await delay(500);
  }
  throw new Error("Not ready: " + url);
}
function startApi(extra = {}) {
  backend = spawn(python, ["scripts/lab8_fixture_api.py"], {
    cwd: root,
    env: { ...process.env, ...extra },
    stdio: ["ignore", openSync("/tmp/sirius-lab8-fixture.log", "a"), "ignore"],
  });
  return ready(api + "/health");
}
async function stopApi() {
  if (backend && !backend.killed) {
    backend.kill("SIGTERM");
    await new Promise((r) => backend.once("exit", r));
  }
  backend = null;
}
async function pageReady(page, path) {
  await page.goto(site + path);
  await page.locator("[data-dish-id]").first().waitFor({ state: "visible" });
}
try {
  await startApi();
  {
    const runtime = root + "storefront/.next/standalone/.next/";
    rmSync(runtime + "server/route-cache", { recursive: true, force: true });
    rmSync(runtime + "server/app/menu", { recursive: true, force: true });
    cpSync(
      root + "storefront/.next/server/app/menu",
      runtime + "server/app/menu",
      { recursive: true },
    );
    rmSync(runtime + "cache/fetch-cache", { recursive: true, force: true });
  }
  next = spawn(process.execPath, ["scripts/start.mjs"], {
    cwd: root + "storefront",
    env: {
      ...process.env,
      API_INTERNAL_URL: api,
      SITE_URL: site,
      CABINET_URL: "http://localhost:8080",
    },
    stdio: [
      "ignore",
      openSync("/tmp/sirius-lab8-production.log", "a"),
      "ignore",
    ],
  });
  await ready(site + "/menu-csr");
  if (!isrOnly) {
    const list = await (await fetch(api + "/menu/items")).json();
    assert(list.length > 0);
    const first = list.find((i) => i.id === 1),
      second = list.find((i) => i.id === 2);
    const ssr = await fetch(site + "/menu");
    const html = await ssr.text();
    assert.equal(ssr.status, 200);
    assert(html.includes(first.name));
    assert(/<article[^>]*data-dish-id/.test(html));
    const detailResponse = await fetch(site + "/menu/1");
    const detail = await detailResponse.text();
    assert(detail.includes(first.name));
    const head = detail.split("</head>")[0];
    assert(head.includes('property="og:title"'));
    assert(head.includes(first.name));
    assert(/<title>[^<]*Сырники/.test(detail));
    assert(/<meta name="description"/.test(detail));
    assert(/property="og:title"/.test(detail));
    report.checks.ssr_html = true;
    report.checks.dish_html_and_seo = true;
    const missing = await fetch(site + "/menu/999999");
    const missingHtml = await missing.text();
    assert(missingHtml.includes("Блюдо не найдено"));
    assert.equal(missing.status, 404);
    report.checks.missing_page_http = missing.status;
    const csrHtml = await (await fetch(site + "/menu-csr")).text();
    assert(!csrHtml.includes(first.name));
    assert(!/<article[^>]*data-dish-id/.test(csrHtml));
    report.checks.csr_html_has_no_dishes = true;
    browser = await chromium.launch({
      headless: true,
      ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE
        ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE }
        : {}),
    });
    const context = await browser.newContext({
      viewport: { width: 1440, height: 1100 },
    });
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await pageReady(page, "/menu");
    await page.screenshot({ path: out + "menu-desktop.png", fullPage: true });
    await pageReady(page, "/menu/1");
    await page.screenshot({ path: out + "dish-desktop.png", fullPage: true });
    assert(
      (await page.locator("a.primary").getAttribute("href")).endsWith(
        "/?item=1",
      ),
    );
    await page.setViewportSize({ width: 390, height: 844 });
    await pageReady(page, "/menu");
    assert(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    );
    await page.screenshot({ path: out + "menu-mobile.png", fullPage: true });
    await page.setViewportSize({ width: 1440, height: 1100 });
    // Настоящее выключение API, не подмена ответа в браузере.
    await stopApi();
    await page.goto(site + "/menu/2");
    await page.getByRole("button", { name: "Попробовать снова" }).waitFor();
    await page.screenshot({ path: out + "api-error.png", fullPage: true });
    report.checks.api_stopped_error = true;
    await startApi();
    await page.getByRole("button", { name: "Попробовать снова" }).click();
    await page
      .getByRole("heading", { name: second.name, exact: true })
      .waitFor();
    report.checks.retry_after_api_restart = true;
    // Загрузка в клиентской навигации при медленном API (сценарий отдельно от замеров).
    await stopApi();
    await startApi({ LAB8_DELAY_SECONDS: "1" });
    await page.goto(site + "/menu");
    await page
      .getByRole("link", {
        name: "Подробнее: " + list.find((i) => i.id === 3).name,
      })
      .click();
    await page.getByLabel("Загрузка меню", { exact: true }).waitFor();
    report.checks.loading_visible = true;
    await page
      .getByRole("heading", {
        name: list.find((i) => i.id === 3).name,
        exact: true,
      })
      .waitFor();
    await stopApi();
    await startApi();
    assert.equal(errors.length, 0, errors.join(";"));
    report.checks.browser_no_errors = true;
    await context.close();
    // Chrome DevTools Protocol: Disable cache + одинаковое ограничение сети, по 3 прогона.
    for (const path of ["/menu", "/menu-csr"])
      for (let run = 1; run <= 3; run++) {
        const c = await browser.newContext({
            viewport: { width: 1440, height: 1100 },
          }),
          p = await c.newPage(),
          cdp = await c.newCDPSession(p);
        await cdp.send("Network.enable");
        await cdp.send("Network.setCacheDisabled", { cacheDisabled: true });
        await cdp.send("Network.emulateNetworkConditions", {
          offline: false,
          latency: 80,
          downloadThroughput: 200000,
          uploadThroughput: 100000,
          connectionType: "cellular4g",
        });
        await p.addInitScript(() => {
          window.__dishTime = null;
          const check = () => {
            const dish = document.querySelector("[data-dish-id]");
            if (dish && dish.getBoundingClientRect().height > 0) {
              window.__dishTime = performance.now();
              return;
            }
            requestAnimationFrame(check);
          };
          requestAnimationFrame(check);
        });
        const calls = [];
        p.on("request", (r) => {
          if (r.url().includes("/api/menu/items")) calls.push(r.url());
        });
        await pageReady(p, path);
        await p.waitForFunction(() => window.__dishTime !== null);
        await p.waitForTimeout(200);
        const times = await p.evaluate(() => ({
          dish_ms: window.__dishTime,
          ttfb_ms: performance.getEntriesByType("navigation")[0].responseStart,
          fcp_ms:
            performance.getEntriesByName("first-contentful-paint")[0]
              ?.startTime ?? null,
        }));
        assert.equal(calls.length, path === "/menu" ? 0 : 1);
        report.measurements.push({
          path,
          run,
          ...times,
          browser_api_requests: calls.length,
        });
        console.log("MEASURE", path, run, JSON.stringify(times));
        await c.close();
      }
    report.conditions = {
      browser: await browser.version(),
      network:
        "CDP, cache disabled; latency 80 ms; download 200000 B/s; upload 100000 B/s",
      api: "loopback, FastAPI memory repositories, 12 dishes",
      ssr: "Next ISR warm cache, 60-second revalidation",
      note: "FCP measures any first content; dish_ms measures DOM readiness of the first visible dish, not its exact paint. Local comparison, not a production SLA.",
    };
  }
  if (isrOnly) {
    // ISR: меняем цену только в изолированной памяти через настоящий PATCH API.
    const login = await fetch(api + "/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: "lab8@example.ru",
        password: "lab8-local-fixture",
      }),
    });
    assert(login.ok);
    const token = (await login.json()).access_token;
    await (await fetch(site + "/menu/1")).text();
    await delay(1500);
    await (await fetch(site + "/menu/1")).text();
    const changed = await fetch(api + "/menu/items/1", {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        Authorization: "Bearer " + token,
      },
      body: JSON.stringify({ price: 197 }),
    });
    assert(changed.ok);
    const immediate = await (await fetch(site + "/menu/1")).text();
    assert(/data-price[^>]*>190/.test(immediate));
    report.checks.isr_immediate_old_price = true;
    console.log(
      "ISR: waiting 65 seconds for revalidation (only fixture price changes)",
    );
    await delay(65000);
    let refreshed = false;
    for (let i = 0; i < 12; i++) {
      const h = await (await fetch(site + "/menu/1")).text();
      if (/data-price[^>]*>197/.test(h)) {
        refreshed = true;
        break;
      }
      await delay(1500);
    }
    assert(refreshed, "ISR did not refresh price");
    report.checks.isr_price_refreshed_after_ttl = true;
  }
  report.checked_at = new Date().toISOString();
  writeFileSync(
    out + "verification.json",
    JSON.stringify(report, null, 2) + "\n",
  );
  console.log("PASS", JSON.stringify(report.checks));
} catch (e) {
  report.error = String(e);
  writeFileSync(
    out + "verification.failed.json",
    JSON.stringify(report, null, 2) + "\n",
  );
  console.error(e);
  process.exitCode = 1;
} finally {
  if (browser) await browser.close();
  await stopApi();
  if (next) {
    next.kill("SIGTERM");
    await new Promise((r) => next.once("exit", r));
  }
}
