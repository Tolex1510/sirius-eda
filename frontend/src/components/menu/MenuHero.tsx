import { ArrowDown, ChefHat, Leaf, ShoppingBag } from "lucide-react";
import { FoodArt } from "./FoodArt";

export function MenuHero() {
  return (
    <section className="hero">
      <div className="hero-copy">
        <span className="eyebrow">
          <span /> СТОЛОВАЯ, КОТОРАЯ РЯДОМ
        </span>
        <h1>
          Хороший день
          <br />
          начинается
          <br />с <em>вкусного обеда.</em>
        </h1>
        <p>
          Любимые блюда, простой заказ и чуть больше
          <br className="desktop" /> времени на то, что вам нравится.
        </p>
        <a className="primary" href="#menu">
          Выбрать что-нибудь вкусное <ArrowDown size={18} />
        </a>
        <div className="hero-notes">
          <span>
            <ChefHat size={16} /> Готовит наша кухня
          </span>
          <span>
            <ShoppingBag size={16} /> Удобно заказать
          </span>
        </div>
      </div>
      <div className="hero-visual">
        <span className="orbit orbit-one" />
        <span className="orbit orbit-two" />
        <span className="visual-caption">ВАШ ВКУСНЫЙ ПЕРЕРЫВ</span>
        <FoodArt name="Обед" category="Горячее" large />
        <div className="floating-note">
          <Leaf size={20} />
          <span>
            Просто. Свежо.
            <br />
            <strong>По-домашнему.</strong>
          </span>
        </div>
        <div className="visual-spark">✳</div>
      </div>
    </section>
  );
}
