import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, Minus, Plus } from "lucide-react";
import { message, rub } from "../../lib/format";
import { post } from "../../lib/api";
import type { Item, Order, Payment, User } from "../../types";
import { ErrorBox } from "../ui/ErrorBox";
import { Modal } from "../ui/Modal";
import { FoodArt } from "../menu/FoodArt";

export function Checkout({
  item,
  close,
  login,
  user,
}: {
  item: Item;
  close: () => void;
  login: () => void;
  user: User | null;
}) {
  const [quantity, setQuantity] = useState(1),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [created, setCreated] = useState<Order | null>(null);
  const navigate = useNavigate();
  async function submit() {
    if (!user) {
      login();
      return;
    }
    setBusy(true);
    setError("");
    try {
      const order =
        created ||
        (await post<Order>("/payments/checkout", {
          item_id: item.id,
          quantity,
        }));
      setCreated(order);
      const payment = await post<Payment>(
        "/payments",
        { order_id: order.id, amount: order.total_cost },
        { "Idempotency-Key": `web-order-${order.id}` },
      );
      if (payment.confirmation_url) {
        if (payment.provider === "demo") {
          close();
          navigate(payment.confirmation_url);
        } else window.location.assign(payment.confirmation_url);
      } else {
        close();
        navigate("/orders");
      }
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal title="Ваш вкусный выбор" close={close}>
      <div className="checkout-item">
        <FoodArt imageUrl={item.image_url} name={item.name} category="" />
        <div>
          <h3>{item.name}</h3>
          <p>{rub(item.price)} за порцию</p>
        </div>
      </div>
      <div className="checkout-line">
        <span>Количество</span>
        <div className="stepper">
          <button
            className="icon"
            disabled={!!created || quantity <= 1 || busy}
            onClick={() => setQuantity(quantity - 1)}
            aria-label="Уменьшить количество"
          >
            <Minus size={16} />
          </button>
          <strong>{quantity}</strong>
          <button
            className="icon"
            disabled={!!created || quantity >= 100 || busy}
            onClick={() => setQuantity(quantity + 1)}
            aria-label="Увеличить количество"
          >
            <Plus size={16} />
          </button>
        </div>
      </div>
      <div className="checkout-total">
        <span>Итого</span>
        <strong>{rub(created?.total_cost ?? item.price * quantity)}</strong>
      </div>
      <p className="small muted">
        Один заказ — одно блюдо в нужном количестве. Оплата работает в тестовом
        режиме.
      </p>
      {error && <ErrorBox text={error} />}
      <button className="primary full" onClick={submit} disabled={busy}>
        {busy
          ? "Создаём заказ…"
          : user
            ? created
              ? "Продолжить оплату"
              : "Перейти к оплате"
            : "Войти и заказать"}
        <ArrowRight size={18} />
      </button>
    </Modal>
  );
}
