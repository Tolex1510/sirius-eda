import { Coffee } from "lucide-react";

export function FoodArt({
  name,
  category,
  large = false,
  imageUrl,
}: {
  name: string;
  category: string;
  large?: boolean;
  imageUrl?: string | null;
}) {
  if (imageUrl) return <div className={"food-art food-photo " + (large ? "large" : "")}><img src={imageUrl} alt={name} loading="lazy" decoding="async" /></div>;
  const isDrink = /напит|кофе|чай|сок/i.test(category + name),
    isSweet = /десерт|сырник|завтрак|выпеч|каша/i.test(category + name),
    isSoup = /суп|борщ/i.test(category + name);
  return (
    <div
      className={
        "food-art " +
        (large ? "large " : "") +
        (isDrink
          ? "drink-art"
          : isSweet
            ? "sweet-art"
            : isSoup
              ? "soup-art"
              : "meal-art")
      }
      aria-hidden="true"
    >
      <div className="art-leaf one" />
      <div className="art-leaf two" />
      <div className="plate">
        {isDrink ? (
          <Coffee />
        ) : (
          <>
            <i />
            <i />
            <i />
            <span />
            <span />
            <span />
          </>
        )}
      </div>
      <div className="art-dot" />
    </div>
  );
}
