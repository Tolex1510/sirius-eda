import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { cabinetUrl, getMenuItem } from "@/lib/api";
import { formatPrice } from "@/lib/menu";
import { FoodArt } from "@/components/FoodCard";
export const revalidate = 60;
export function generateStaticParams() {
  return [];
}
type Props = { params: Promise<{ id: string }> };
export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { id } = await params;
  const item = await getMenuItem(id);
  if (!item) return { title: "Блюдо не найдено", robots: { index: false } };
  const description = `${item.name} — ${formatPrice(item.price)}. ${item.description || ""} ${item.is_available ? "Выберите блюдо и оформите заказ в Сириус.Еде." : "Временно нет в наличии."}`;
  return {
    title: item.name,
    description,
    alternates: { canonical: `/menu/${item.id}` },
    openGraph: {
      title: item.name,
      description,
      url: `/menu/${item.id}`,
      images: ["/menu-preview.svg"],
    },
  };
}
export default async function DishPage({ params }: Props) {
  const { id } = await params;
  const item = await getMenuItem(id);
  if (!item) notFound();
  return (
    <main className="container page detail-page">
      <Link href="/menu" className="back-link">
        ← Всё меню
      </Link>
      <article className="dish-detail" data-dish-id={item.id}>
        <FoodArt imageUrl={item.image_url} name={item.name} />
        <div className="dish-copy">
          <span className="eyebrow">ВАШ ВКУСНЫЙ ВЫБОР</span>
          <h1>{item.name}</h1>
          <p>
            {item.description || "Подробности заказа и количество порций можно выбрать в кабинете."}
          </p>
          {item.portion_value && <p>Порция: {item.portion_value} {item.portion_unit === "ml" ? "мл" : "г"}</p>}
          {!!item.ingredients?.length && <p>Состав: {item.ingredients.join(", ")}.</p>}
          {!!item.dietary_tags?.length && <p>{item.dietary_tags.includes("vegan") ? "Растительная рецептура" : "Вегетарианская рецептура"}</p>}
          <strong className="dish-price" data-price>
            {formatPrice(item.price)}
          </strong>
          <p className="availability">
            {item.is_available
              ? "● Доступно для заказа"
              : "Временно нет в наличии"}
          </p>
          {item.is_available ? (
            <a className="primary" href={cabinetUrl(`/?item=${item.id}`)}>
              Выбрать порции и заказать ↗
            </a>
          ) : (
            <Link href="/menu" className="secondary">
              Выбрать другое блюдо
            </Link>
          )}
        </div>
      </article>
    </main>
  );
}
