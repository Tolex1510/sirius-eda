import Link from "next/link";
import { formatPrice, type MenuItem } from "@/lib/menu";

export function FoodArt({ name, imageUrl }: { name: string; imageUrl?: string | null }) {
  if (imageUrl) return <div className="food-art food-photo"><img src={imageUrl} alt={name} loading="lazy" decoding="async" /></div>;
  const drink = /кофе|чай|морс|сок/i.test(name);
  const sweet = /сырник|каша|запеканка|десерт/i.test(name);
  return (
    <div
      aria-hidden="true"
      className={`food-art ${drink ? "drink-art" : sweet ? "sweet-art" : ""}`}
    >
      <span className="leaf leaf-one" />
      <span className="leaf leaf-two" />
      <div className="plate">
        {drink ? (
          <span className="cup">☕</span>
        ) : (
          <>
            <i />
            <i />
            <i />
            <b />
            <b />
            <b />
          </>
        )}
      </div>
      <span className="art-dot" />
    </div>
  );
}
export default function FoodCard({ item }: { item: MenuItem }) {
  return (
    <article className="food-card" data-dish-id={item.id}>
      <Link
        href={`/menu/${item.id}`}
        prefetch={false}
        aria-label={`Подробнее: ${item.name}`}
      >
        <FoodArt imageUrl={item.image_url} name={item.name} />
      </Link>
      <div className="food-body">
        <span className="eyebrow">МЕНЮ СТОЛОВОЙ</span>
        <h2>
          <Link href={`/menu/${item.id}`} prefetch={false}>
            {item.name}
          </Link>
        </h2>
        <p>
          {item.is_available
            ? (item.description || "Приготовим для вашего вкусного перерыва")
            : "Временно нет в наличии"}
        </p>
        {item.portion_value && <p>{item.portion_value} {item.portion_unit === "ml" ? "мл" : "г"}</p>}
        {!!item.ingredients?.length && <details><summary>Состав</summary><p>{item.ingredients.join(", ")}</p></details>}
        {!!item.dietary_tags?.length && <p>{item.dietary_tags.includes("vegan") ? "Растительная рецептура" : "Вегетарианская рецептура"}</p>}
        <div className="food-bottom">
          <strong data-price>{formatPrice(item.price)}</strong>
          <Link
            className="round-button"
            href={`/menu/${item.id}`}
            prefetch={false}
            aria-label={`Открыть ${item.name}`}
          >
            ↗
          </Link>
        </div>
      </div>
    </article>
  );
}
