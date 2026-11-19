import type { User } from "../types";

let token: string | null = null;
let renewal: Promise<boolean> | null = null;
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}
export async function renew(): Promise<boolean> {
  if (!renewal)
    renewal = (async () => {
      try {
        const r = await fetch("/api/auth/session/refresh", {
          method: "POST",
          credentials: "same-origin",
        });
        if (!r.ok) {
          token = null;
          return false;
        }
        token = (await r.json()).access_token;
        return true;
      } catch {
        token = null;
        return false;
      }
    })().finally(() => {
      renewal = null;
    });
  return renewal;
}
export async function api<T>(
  path: string,
  options: RequestInit = {},
  retry = true,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch("/api" + path, {
      ...options,
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: "Bearer " + token } : {}),
        ...options.headers,
      },
    });
  } catch {
    throw new ApiError(
      "Не удалось связаться с сервером. Проверьте соединение.",
      0,
    );
  }
  if (response.status === 401 && retry && !path.startsWith("/auth/")) {
    if (await renew()) return api(path, options, false);
    window.dispatchEvent(new Event("session-expired"));
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok)
    throw new ApiError(
      typeof data.detail === "string"
        ? data.detail
        : response.status === 422
          ? "Проверьте заполненные поля."
          : "Сервис временно недоступен. Попробуйте ещё раз.",
      response.status,
    );
  return data as T;
}
export async function signIn(email: string, password: string) {
  const pair = await api<{ access_token: string }>(
    "/auth/session/login",
    { method: "POST", body: JSON.stringify({ email, password }) },
    false,
  );
  token = pair.access_token;
  return api<User>("/users/me");
}
export async function signOut() {
  await api("/auth/session/logout", { method: "POST" }, false);
  token = null;
}
export const post = <T>(path: string, body?: unknown, headers?: HeadersInit) =>
  api<T>(path, {
    method: "POST",
    body: body === undefined ? undefined : JSON.stringify(body),
    headers,
  });
export async function trackDelivery(
  id: number,
  onStatus: (status: string) => void,
  signal: AbortSignal,
) {
  while (!signal.aborted) {
    try {
      const response = await fetch(`/api/delivery/${id}/track`, {
        headers: token ? { Authorization: "Bearer " + token } : {},
        signal,
      });
      if (response.status === 401 && (await renew())) continue;
      if (!response.ok || !response.body)
        throw new Error("Трекинг временно недоступен");
      const reader = response.body.getReader(),
        decoder = new TextDecoder();
      let buffer = "";
      try {
        while (!signal.aborted) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const events = buffer.split("\n\n");
          buffer = events.pop() || "";
          for (const event of events) {
            const data = event
              .split("\n")
              .find((line) => line.startsWith("data: "));
            if (data) {
              const update = JSON.parse(data.slice(6));
              if (typeof update.status === "string") {
                onStatus(update.status);
                if (["completed", "cancelled"].includes(update.status)) return;
              }
            }
          }
        }
      } finally {
        await reader.cancel().catch(() => {});
      }
    } catch {
      if (signal.aborted) return;
    }
    await new Promise<void>((resolve) => {
      const finish = () => {
        clearTimeout(timer);
        signal.removeEventListener("abort", finish);
        resolve();
      };
      const timer = setTimeout(finish, 3000);
      signal.addEventListener("abort", finish, { once: true });
      if (signal.aborted) finish();
    });
  }
}
