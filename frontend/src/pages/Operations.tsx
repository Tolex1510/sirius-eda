import { useEffect, useState } from "react";
import { Check, ChefHat } from "lucide-react";
import { api } from "../lib/api";
import { message } from "../lib/format";
import type { Delivery, Item, Order, User } from "../types";
import { ErrorBox } from "../components/ui/ErrorBox";
import { Empty } from "../components/ui/Empty";
import { Badge } from "../components/ui/Badge";

export function Operations({
  user,
  items,
}: {
  user: User | null;
  items: Item[];
}) {
  const [orders, setOrders] = useState<Order[]>([]),
    [deliveries, setDeliveries] = useState<Delivery[]>([]),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  async function load() {
    try {
      if (user?.role === "cook" || user?.role === "admin")
        setOrders(
          (await api<Order[]>("/kitchen/orders")).filter(
            (order) =>
              order.payment_source !== "gateway" || order.status === "paid",
          ),
        );
      if (user?.role === "courier") setDeliveries(await api("/delivery/my"));
      setError("");
    } catch (err) {
      setError(message(err));
    }
  }
  useEffect(() => {
    void load();
  }, [user?.id]);
  async function update(d: Delivery) {
    setBusy(true);
    try {
      await api(
        `/delivery/${d.id}/${d.status === "in_progress" ? "pickup" : "complete"}`,
        { method: "PATCH" },
      );
      await load();
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  }
  if (!user || !["cook", "courier", "admin"].includes(user.role))
    return (
      <Empty icon={<ChefHat />} title="Страница сотрудников">
        Доступна после входа с соответствующей ролью.
      </Empty>
    );
  return (
    <section className="page">
      <div className="section-top">
        <div>
          <span className="eyebrow">РАБОЧЕЕ МЕСТО</span>
          <h1>{user.role === "courier" ? "Мои доставки" : "Кухня"}</h1>
        </div>
        <button className="secondary" onClick={() => void load()}>
          Обновить
        </button>
      </div>
      {error && <ErrorBox text={error} />}
      <div className="order-list">
        {orders.map((o) => (
          <div className="order-card" key={o.id}>
            <div className="order-head">
              Заказ №{o.id}
              <Badge status={o.status} />
            </div>
            <h3>
              {items.find((i) => i.id === o.item_id)?.name ||
                `Блюдо №${o.item_id}`}{" "}
              × {o.quantity}
            </h3>
          </div>
        ))}
        {deliveries.map((d) => (
          <div className="order-card" key={d.id}>
            <div className="order-head">
              Заказ №{d.order_id}
              <Badge status={d.status} />
            </div>
            {["in_progress", "on_the_way"].includes(d.status) && (
              <button
                className="primary"
                disabled={busy}
                onClick={() => void update(d)}
              >
                {d.status === "in_progress"
                  ? "Забрал на кухне"
                  : "Передал заказ"}
              </button>
            )}
          </div>
        ))}
        {!orders.length && !deliveries.length && !error && (
          <Empty icon={<Check />} title="Пока нет активных задач">
            Нажмите «Обновить», чтобы проверить новые заказы.
          </Empty>
        )}
      </div>
    </section>
  );
}
