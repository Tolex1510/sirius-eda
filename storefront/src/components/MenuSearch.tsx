"use client";
import { useEffect, useRef, useState } from "react";
import FoodCard from "./FoodCard";
import { parseItems, type MenuItem } from "@/lib/menu";

type SearchMode = "name" | "wishes";
type SearchResult = {
  items: MenuItem[];
  mode: string;
  explanation?: { constraints: string[]; ranking: string };
};
const examples = ["Горячий обед", "Обед без мяса до 250 рублей", "Кофе с молоком"];

export default function MenuSearch({ items, searchUrl }: { items: MenuItem[]; searchUrl: string }) {
  const [mode, setMode] = useState<SearchMode>("name");
  const [nameQuery, setNameQuery] = useState("");
  const [wishes, setWishes] = useState("");
  const [result, setResult] = useState<SearchResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const request = useRef<AbortController | null>(null);
  useEffect(() => () => request.current?.abort(), []);
  function selectMode(next: SearchMode) {
    request.current?.abort(); setBusy(false); setError(""); setMode(next);
  }
  function changeWishes(value: string) {
    request.current?.abort(); setWishes(value); setResult(null); setBusy(false); setError("");
  }
  async function search() {
    request.current?.abort();
    const controller = new AbortController(); request.current = controller;
    setBusy(true); setError("");
    try {
      const response = await fetch(searchUrl + "?q=" + encodeURIComponent(wishes.trim()), { signal: controller.signal });
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Подбор временно недоступен");
      const found = parseItems(data.items);
      if (!controller.signal.aborted) setResult({ items: found, mode: data.mode, explanation: data.explanation });
    } catch (err) {
      if (!controller.signal.aborted) setError(err instanceof Error ? err.message : "Не удалось подобрать блюда");
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  }
  const visible = mode === "wishes" ? (result?.items || items) : items.filter(item =>
    [item.name, item.description, ...(item.ingredients || [])].join(" ").toLowerCase().includes(nameQuery.toLowerCase()));
  return <section className="catalog-search" aria-label="Поиск и подбор блюд">
    <div className="search-modes" role="tablist" aria-label="Способ поиска">
      <button id="catalog-name-tab" role="tab" aria-selected={mode === "name"} aria-controls="catalog-name-panel" onClick={() => selectMode("name")}>По названию</button>
      <button id="catalog-wishes-tab" role="tab" aria-selected={mode === "wishes"} aria-controls="catalog-wishes-panel" onClick={() => selectMode("wishes")}>По пожеланиям</button>
    </div>
    {mode === "name" ? <div id="catalog-name-panel" role="tabpanel" aria-labelledby="catalog-name-tab" className="search-panel">
      <label htmlFor="catalog-name-input" className="search-label">Название или ингредиент</label>
      <div className="search-field-row">
        <input id="catalog-name-input" aria-label="Поиск по названию" placeholder="Например, борщ или творог" value={nameQuery} onChange={event => setNameQuery(event.target.value)} />
        {nameQuery && <button type="button" className="secondary" onClick={() => setNameQuery("")}>Очистить</button>}
      </div>
      <p className="search-hint">Ищем совпадения в названии, описании и составе. Результат меняется при вводе.</p>
    </div> : <div id="catalog-wishes-panel" role="tabpanel" aria-labelledby="catalog-wishes-tab" className="search-panel">
      <form onSubmit={event => { event.preventDefault(); if (wishes.trim().length >= 2) void search(); }}>
        <label htmlFor="catalog-wishes-input" className="search-label">Какой обед вы хотите?</label>
        <div className="search-field-row">
          <input id="catalog-wishes-input" aria-label="Пожелания к блюду" placeholder="Например, горячий обед без мяса до 250 рублей" maxLength={240} value={wishes} onChange={event => changeWishes(event.target.value)} />
          <button className="primary" disabled={busy || wishes.trim().length < 2}>{busy ? "Подбираем…" : "Подобрать"}</button>
          {wishes && <button type="button" className="secondary" onClick={() => changeWishes("")}>Сбросить</button>}
        </div>
      </form>
      <p className="search-hint">Опишите тип блюда, состав и бюджет. Подбор запускается только по кнопке.</p>
      <div className="search-examples" aria-label="Примеры пожеланий"><span>Например:</span>{examples.map(example => <button key={example} type="button" onClick={() => changeWishes(example)}>{example}</button>)}</div>
    </div>}
    <div className="search-feedback" role="status" aria-live="polite">
      {error && <p className="search-error">{error}</p>}
      {busy ? <p>Подбираем блюда. Первый запрос после простоя может занять больше времени.</p> : <p>{mode === "wishes" && !result ? "Пока показано всё меню. Добавьте пожелания и нажмите «Подобрать»." : `${mode === "wishes" && result?.mode === "semantic" ? "Подобрано" : "Найдено"}: ${visible.length}`}</p>}
      {mode === "wishes" && result?.mode === "keyword" && <p className="search-hint">Подбор по смыслу временно недоступен. Ниже — совпадения по словам. <button className="inline-search-button" onClick={() => selectMode("name")}>Перейти к поиску по названию</button></p>}
    </div>
    {mode === "wishes" && result?.mode === "semantic" && <div className="search-explanation">
      {!!result.explanation?.constraints?.length && <div className="search-constraints" aria-label="Учтённые пожелания">{result.explanation.constraints.map(constraint => <span key={constraint}>{constraint}</span>)}</div>}
      <details><summary>Как работает подбор</summary><p>{result.explanation?.ranking || "Сравниваем пожелания с описаниями блюд, затем проверяем тип блюда, состав и бюджет. Подбираются отдельные позиции меню, а не набор из нескольких блюд."}</p></details>
    </div>}
    {!busy && <div className="cards">{visible.map(item => <FoodCard key={item.id} item={item} />)}</div>}
    {!visible.length && !busy && <div className="empty"><h3>Подходящих блюд не нашлось</h3><p>{mode === "wishes" ? "Попробуйте убрать одно из ограничений или изменить пожелания." : "Попробуйте другое название или ингредиент."}</p></div>}
  </section>;
}
