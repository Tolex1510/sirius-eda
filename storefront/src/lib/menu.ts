export type MenuItem = {
  id: number;
  name: string;
  price: number;
  is_available: boolean;
  category_id: number | null;
  image_url?: string | null;
  description?: string;
  ingredients?: string[];
  dietary_tags?: string[];
  portion_value?: number | null;
  portion_unit?: string | null;
};
export function formatPrice(price: number) {
  return new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency: "RUB",
    maximumFractionDigits: 2,
  }).format(price);
}
export function parseItems(value: unknown): MenuItem[] {
  if (!Array.isArray(value) || !value.every(isItem))
    throw new Error("Некорректный ответ меню");
  return value;
}
export function isItem(value: unknown): value is MenuItem {
  if (!value || typeof value !== "object") return false;
  const item = value as MenuItem;
  return (
    Number.isSafeInteger(item.id) &&
    item.id > 0 &&
    typeof item.name === "string" &&
    typeof item.price === "number" &&
    Number.isFinite(item.price) &&
    typeof item.is_available === "boolean"
  );
}
