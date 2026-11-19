import { Plus } from "lucide-react";
import { rub } from "../../lib/format";
import type { Item } from "../../types";
import { FoodArt } from "./FoodArt";

export function FoodCard({
  item,
  category: cat,
  highlighted,
  choose,
}: {
  item: Item;
  category: string;
  highlighted: boolean;
  choose: (item: Item) => void;
}) {
  return (
    <article
      key={item.id}
      className={"food-card " + (highlighted ? "highlight" : "")}
    >
      <FoodArt imageUrl={item.image_url} name={item.name} category={cat} />
      <div className="food-body">
        <span className="item-category">{cat}</span>
        <h3>{item.name}</h3>
        <p>
          {item.is_available
            ? (item.description || "Приготовим для вашего вкусного перерыва")
            : "Пока нет в наличии"}
        </p>
        {item.portion_value && <p>{item.portion_value} {item.portion_unit === "ml" ? "мл" : "г"}</p>}
        {!!item.ingredients?.length && <details><summary>Состав</summary><p>{item.ingredients.join(", ")}</p></details>}
        {!!item.dietary_tags?.length && <p>{item.dietary_tags.includes("vegan") ? "Растительная рецептура" : "Вегетарианская рецептура"}</p>}
        <div className="food-bottom">
          <strong>{rub(item.price)}</strong>
          <button
            aria-label={"Заказать: " + item.name}
            className="order-button"
            onClick={() => choose(item)}
            disabled={!item.is_available}
          >
            {item.is_available ? (
              <>
                <Plus size={17} /> Заказать
              </>
            ) : (
              "Недоступно"
            )}
          </button>
        </div>
      </div>
    </article>
  );
}
