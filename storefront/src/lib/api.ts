import "server-only";
import { cache } from "react";
import { isItem, parseItems, type MenuItem } from "./menu";

export function apiUrl(path: string) {
  return `${(process.env.API_INTERNAL_URL || "http://127.0.0.1:8000").replace(/\/$/, "")}${path}`;
}
async function request(path: string, fresh = false) {
  try {
    return await fetch(apiUrl(path), {
      ...(fresh
        ? { cache: "no-store" as const }
        : { next: { revalidate: 60 } }),
      signal: AbortSignal.timeout(5000),
    });
  } catch {
    throw new Error("Меню временно недоступно. Попробуйте ещё раз чуть позже.");
  }
}
export const getMenuItems = cache(async (): Promise<MenuItem[]> => {
  const response = await request("/menu/items");
  if (!response.ok) throw new Error("Не удалось получить меню");
  return parseItems(await response.json());
});
export const getMenuItem = cache(
  async (id: string): Promise<MenuItem | null> => {
    if (!/^[1-9]\d*$/.test(id) || !Number.isSafeInteger(Number(id)))
      return null;
    const response = await request(`/menu/items/${id}`);
    if (response.status === 404) return null;
    if (!response.ok) throw new Error("Не удалось получить блюдо");
    const item: unknown = await response.json();
    if (!isItem(item)) throw new Error("Некорректный ответ меню");
    return item;
  },
);
export function cabinetUrl(path: string) {
  return `${(process.env.CABINET_URL || "").replace(/\/$/, "")}${path}`;
}
