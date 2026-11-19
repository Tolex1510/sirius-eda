import type { Metadata } from "next";
import { notFound } from "next/navigation";
import MenuSearch from "@/components/MenuSearch";
import { cabinetUrl, getMenuItems } from "@/lib/api";
export const revalidate = 60;
// Генерируем HTML по первому запросу: Docker-сборке не требуется работающий API.
export function generateStaticParams() {
  return [];
}
export const metadata: Metadata = {
  title: "Что сегодня на обед?",
  description:
    "Меню Сириус.Еды: свежие блюда, актуальные цены и ваш вкусный перерыв.",
  alternates: { canonical: "/menu" },
  openGraph: {
    title: "Меню Сириус.Еды",
    description: "Выберите свой вкусный обед.",
    url: "/menu",
  },
};
export default async function MenuPage({
  params,
}: {
  params: Promise<{ listing?: string[] }>;
}) {
  const { listing } = await params;
  if (listing?.length) notFound();
  const items = await getMenuItems();
  return (
    <main className="container page">
      <section className="catalog-hero">
        <div>
          <span className="eyebrow">СИРИУС.ЕДА · СВЕЖЕЕ КАЖДЫЙ ДЕНЬ</span>
          <h1>Обед по вашему вкусу</h1>
          <p>Выберите знакомое блюдо или подберите обед по пожеланиям.</p>
        </div>
        <div className="catalog-hero-note"><strong>{items.length} блюд и напитков</strong><span>Состав, порции и цены — в карточках</span></div>
      </section>
      <section id="dishes">
        <div className="section-head">
          <div>
            <h2>Меню на сегодня</h2>
          </div>
          <p>Выбирайте из всего меню</p>
        </div>
        {items.length ? (
          <MenuSearch items={items} searchUrl={cabinetUrl("/api/menu/search")} />
        ) : (
          <div className="empty">
            <h2>Меню пока пустое</h2>
            <p>Скоро здесь появятся свежие блюда.</p>
          </div>
        )}
      </section>
      <aside className="help-banner">
        <span>✳</span>
        <div>
          <h2>Не знаете, что выбрать?</h2>
          <p>Наш помощник подскажет и поможет собрать обед.</p>
        </div>
        <a href={cabinetUrl("/assistant")} className="secondary">
          Спросить помощника ↗
        </a>
      </aside>
    </main>
  );
}
