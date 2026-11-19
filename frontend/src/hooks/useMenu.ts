import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { message } from "../lib/format";
import type { Category, Item } from "../types";

export function useMenu() {
  const [items, setItems] = useState<Item[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    try {
      const [i, c] = await Promise.all([
        api<Item[]>("/menu/items"),
        api<Category[]>("/menu/categories"),
      ]);
      setItems(i);
      setCategories(c);
      setError("");
    } catch (err) {
      setError(message(err));
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    void load();
  }, []);
  return { items, categories, error, loading, load };
}
