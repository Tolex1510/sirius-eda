import { cpSync, mkdirSync } from "node:fs";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
const root = fileURLToPath(new URL("../", import.meta.url));
mkdirSync(root + ".next/standalone/.next", { recursive: true });
cpSync(root + ".next/static", root + ".next/standalone/.next/static", {
  recursive: true,
});
cpSync(root + "public", root + ".next/standalone/public", { recursive: true });
const child = spawn(process.execPath, [root + ".next/standalone/server.js"], {
  stdio: "inherit",
  env: {
    ...process.env,
    PORT: process.env.PORT || "3001",
    HOSTNAME: process.env.STOREFRONT_HOST || "127.0.0.1",
  },
});
for (const signal of ["SIGINT", "SIGTERM"])
  process.on(signal, () => child.kill(signal));
child.on("exit", (code) => process.exit(code || 0));
