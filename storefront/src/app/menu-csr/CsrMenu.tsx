"use client";
import { useEffect, useState } from "react";
import FoodCard from "@/components/FoodCard";
import { parseItems, type MenuItem } from "@/lib/menu";
export default function CsrMenu() {
  const [items, setItems] = useState<MenuItem[] | null>(null),
    [error, setError] = useState(false),
    [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setError(false);
    setItems(null);
    fetch("/api/menu/items", { cache: "no-store", signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error("API unavailable");
        setItems(parseItems(await response.json()));
      })
      .catch(() => {
        if (!controller.signal.aborted) setError(true);
      });
    return () => controller.abort();
  }, [attempt]);
  return (
    <main className="container page">
      <span className="eyebrow">СРАВНЕНИЕ СПОСОБОВ ЗАГРУЗКИ</span>
      <h1>Меню с клиентской загрузкой</h1>
      <p className="intro">
        Блюда появляются после загрузки JavaScript и запроса из браузера.
      </p>
      {error ? (
        <section className="error-state" role="alert">
          <h2>Не удалось загрузить меню</h2>
          <p>Попробуйте ещё раз чуть позже.</p>
          <button className="primary" onClick={() => setAttempt((x) => x + 1)}>
            Попробовать снова
          </button>
        </section>
      ) : items === null ? (
        <div className="cards" role="status" aria-label="Загрузка меню">
          {Array.from({ length: 6 }, (_, i) => (
            <div className="skeleton skeleton-card" key={i} />
          ))}
        </div>
      ) : items.length ? (
        <div className="cards">
          {items.map((item) => (
            <FoodCard key={item.id} item={item} />
          ))}
        </div>
      ) : (
        <p>Меню пока пустое</p>
      )}
    </main>
  );
}
