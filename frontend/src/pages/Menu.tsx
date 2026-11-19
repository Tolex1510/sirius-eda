import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowRight, Search, Sparkles, Utensils } from "lucide-react";
import { api } from "../lib/api";
import type { Category, Item } from "../types";
import { ErrorBox } from "../components/ui/ErrorBox";
import { Empty } from "../components/ui/Empty";
import { FoodCard } from "../components/menu/FoodCard";

type SearchMode = "name" | "wishes";
type SearchResult = { items: Item[]; mode: string; explanation?: { constraints: string[]; ranking: string } };
const examples = ["Горячий обед", "Обед без мяса до 250 рублей", "Кофе с молоком"];

export function Menu({ items, categories, loading, error, reload, choose }: {
  items: Item[]; categories: Category[]; loading: boolean; error: string; reload: () => void; choose: (item: Item) => void;
}) {
  const [mode, setMode] = useState<SearchMode>("name");
  const [nameQuery, setNameQuery] = useState("");
  const [wishes, setWishes] = useState("");
  const [category, setCategory] = useState<number | null>(null);
  const [result, setResult] = useState<SearchResult | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState("");
  const request = useRef<AbortController | null>(null);
  const [params] = useSearchParams();
  useEffect(() => () => request.current?.abort(), []);
  function selectMode(next: SearchMode) {
    request.current?.abort(); setSearching(false); setSearchError(""); setMode(next); setCategory(null);
  }
  function changeWishes(value: string) {
    request.current?.abort(); setWishes(value); setResult(null); setSearching(false); setSearchError("");
  }
  async function searchByMeaning() {
    request.current?.abort();
    const controller = new AbortController(); request.current = controller;
    setSearching(true); setSearchError(""); setCategory(null);
    try {
      const response = await api<SearchResult>("/menu/search?q=" + encodeURIComponent(wishes.trim()), { signal: controller.signal });
      if (!controller.signal.aborted) setResult(response);
    } catch (err) {
      if (!controller.signal.aborted) setSearchError(err instanceof Error ? err.message : "Не удалось подобрать блюда");
    } finally {
      if (!controller.signal.aborted) setSearching(false);
    }
  }
  const visible = mode === "wishes" ? (result?.items || items) : items.filter(item =>
    (category === null || item.category_id === category) &&
    [item.name, item.description, ...(item.ingredients || [])].join(" ").toLowerCase().includes(nameQuery.toLowerCase()));
  const selected = Number(params.get("item"));
  return <>
    <section className="catalog-hero">
      <div><span className="eyebrow">СИРИУС.ЕДА · СВЕЖЕЕ КАЖДЫЙ ДЕНЬ</span><h1>Обед по вашему вкусу</h1><p>Выберите знакомое блюдо или подберите обед по пожеланиям.</p></div>
      <div className="catalog-hero-note"><strong>{items.length} блюд и напитков</strong><span>Состав, порции и цены — в карточках</span></div>
    </section>
    <section id="menu" className="menu-section">
      <div className="section-top"><h2>Меню на сегодня</h2><p className="muted">Выбирайте из всего меню</p></div>
      <div className="catalog-search" aria-label="Поиск и подбор блюд">
        <div className="search-modes" role="tablist" aria-label="Способ поиска">
          <button id="menu-name-tab" role="tab" aria-selected={mode === "name"} aria-controls="menu-name-panel" onClick={() => selectMode("name")}>По названию</button>
          <button id="menu-wishes-tab" role="tab" aria-selected={mode === "wishes"} aria-controls="menu-wishes-panel" onClick={() => selectMode("wishes")}>По пожеланиям</button>
        </div>
        {mode === "name" ? <div id="menu-name-panel" role="tabpanel" aria-labelledby="menu-name-tab" className="search-panel">
          <label htmlFor="menu-name-input" className="search-label">Название или ингредиент</label>
          <div className="search-field-row"><input id="menu-name-input" aria-label="Поиск по названию" placeholder="Например, борщ или творог" value={nameQuery} onChange={event => setNameQuery(event.target.value)} />{nameQuery && <button className="secondary" onClick={() => setNameQuery("")}>Очистить</button>}</div>
          <p className="search-hint">Ищем совпадения в названии, описании и составе. Результат меняется при вводе.</p>
        </div> : <div id="menu-wishes-panel" role="tabpanel" aria-labelledby="menu-wishes-tab" className="search-panel">
          <form onSubmit={event => { event.preventDefault(); if (wishes.trim().length >= 2) void searchByMeaning(); }}>
            <label htmlFor="menu-wishes-input" className="search-label">Какой обед вы хотите?</label>
            <div className="search-field-row"><input id="menu-wishes-input" aria-label="Пожелания к блюду" placeholder="Например, горячий обед без мяса до 250 рублей" maxLength={240} value={wishes} onChange={event => changeWishes(event.target.value)} /><button className="primary" disabled={searching || wishes.trim().length < 2}>{searching ? "Подбираем…" : "Подобрать"}</button>{wishes && <button type="button" className="secondary" onClick={() => changeWishes("")}>Сбросить</button>}</div>
          </form>
          <p className="search-hint">Опишите тип блюда, состав и бюджет. Подбор запускается только по кнопке.</p>
          <div className="search-examples" aria-label="Примеры пожеланий"><span>Например:</span>{examples.map(example => <button key={example} type="button" onClick={() => changeWishes(example)}>{example}</button>)}</div>
        </div>}
        {mode === "name" && <div className="categories" aria-label="Категории меню"><button className={category === null ? "selected" : ""} onClick={() => setCategory(null)}><Utensils size={15} />Всё меню</button>{categories.filter(c => items.some(item => item.category_id === c.id)).map(c => <button key={c.id} className={category === c.id ? "selected" : ""} onClick={() => setCategory(c.id)}>{c.name}</button>)}</div>}
        <div className="search-feedback" role="status" aria-live="polite">
          {searchError && <p className="search-error">{searchError}</p>}
          {searching ? <p>Подбираем блюда. Первый запрос после простоя может занять больше времени.</p> : <p>{mode === "wishes" && !result ? "Пока показано всё меню. Добавьте пожелания и нажмите «Подобрать»." : `${mode === "wishes" && result?.mode === "semantic" ? "Подобрано" : "Найдено"}: ${visible.length}`}</p>}
          {mode === "wishes" && result?.mode === "keyword" && <p className="search-hint">Подбор по смыслу временно недоступен. Ниже — совпадения по словам. <button className="inline-search-button" onClick={() => selectMode("name")}>Перейти к поиску по названию</button></p>}
        </div>
        {mode === "wishes" && result?.mode === "semantic" && <div className="search-explanation">
          {!!result.explanation?.constraints?.length && <div className="search-constraints" aria-label="Учтённые пожелания">{result.explanation.constraints.map(constraint => <span key={constraint}>{constraint}</span>)}</div>}
          <details><summary>Как работает подбор</summary><p>{result.explanation?.ranking || "Сравниваем пожелания с описаниями блюд, затем проверяем тип блюда, состав и бюджет. Подбираются отдельные позиции меню, а не набор из нескольких блюд."}</p></details>
        </div>}
      </div>
      {error ? <ErrorBox text={error} retry={reload} /> : loading || searching ? <div className="cards">{[1, 2, 3, 4].map(i => <div key={i} className="skeleton" />)}</div> : !visible.length ? <Empty icon={<Search />} title="Подходящих блюд не нашлось">{mode === "wishes" ? "Попробуйте убрать одно из ограничений или изменить пожелания." : "Попробуйте другое название или ингредиент."}</Empty> : <div className="cards">{visible.map(item => <FoodCard key={item.id} item={item} category={categories.find(c => c.id === item.category_id)?.name || "Наше меню"} highlighted={selected === item.id} choose={choose} />)}</div>}
    </section>
    <section className="assistant-banner"><div className="banner-icon"><Sparkles size={25} /></div><div><span className="eyebrow">ВАШ ПОМОЩНИК</span><h2>Не можете выбрать?</h2><p>Спросите о меню, заказе или оплате у ассистента.</p></div><Link to="/assistant" className="secondary">Открыть чат <ArrowRight size={17} /></Link></section>
  </>;
}
