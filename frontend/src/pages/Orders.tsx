import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, ShoppingBag } from "lucide-react";
import { api, post } from "../lib/api";
import { message } from "../lib/format";
import type { Delivery, Item, Order, Payment, User } from "../types";
import { ErrorBox } from "../components/ui/ErrorBox";
import { Empty } from "../components/ui/Empty";
import { OrderDetails } from "../components/orders/OrderDetails";
import { OrderCard } from "../components/orders/OrderCard";

export function Orders({
  user,
  login,
  items,
}: {
  user: User | null;
  login: () => void;
  items: Item[];
}) {
  const [orders, setOrders] = useState<Order[]>([]),
    [payments, setPayments] = useState<Payment[]>([]),
    [deliveries, setDeliveries] = useState<Delivery[]>([]),
    [error, setError] = useState(""),
    [busy, setBusy] = useState<number | null>(null),
    [loading, setLoading] = useState(true),
    [detailsId, setDetailsId] = useState<number | null>(null),
    [deliveryError, setDeliveryError] = useState("");
  const navigate = useNavigate();
  async function load() {
    try {
      const [o, p, d] = await Promise.all([
        api<Order[]>("/orders/my"),
        api<Payment[]>("/payments"),
        api<Delivery[]>("/delivery/my").catch(() => {
          setDeliveryError(
            "Статусы доставки временно недоступны. Заказы и оплата продолжают работать.",
          );
          return null;
        }),
      ]);
      setOrders(o.reverse());
      setPayments(p);
      if (d) {
        setDeliveries(d);
        setDeliveryError("");
      }
      setError("");
    } catch (err) {
      setError(message(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!user) return;
    void load();
    const interval = setInterval(() => void load(), 10000);
    return () => clearInterval(interval);
  }, [user?.id]);
  async function action(order: Order, cancel = false) {
    setBusy(order.id);
    setError("");
    try {
      if (cancel) await post(`/payments/orders/${order.id}/cancel`);
      else {
        const payment =
          payments.find((p) => p.order_id === order.id) ||
          (await post<Payment>(
            "/payments",
            { order_id: order.id, amount: order.total_cost },
            { "Idempotency-Key": `web-order-${order.id}` },
          ));
        if (payment.confirmation_url) {
          if (payment.provider === "demo") navigate(payment.confirmation_url);
          else window.location.assign(payment.confirmation_url);
        } else await post(`/payments/${payment.id}/refresh`);
      }
      await load();
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(null);
    }
  }
  if (!user)
    return (
      <Empty icon={<ShoppingBag />} title="Ваши заказы будут здесь">
        Войдите, чтобы увидеть историю.
        <button className="primary" onClick={login}>
          Войти в аккаунт <ArrowRight size={17} />
        </button>
      </Empty>
    );
  return (
    <section className="page">
      <div className="section-top">
        <div>
          <span className="eyebrow">ЛИЧНЫЙ КАБИНЕТ</span>
          <h1>Мои заказы</h1>
          <p className="muted">Всё о вашем обеде — в одном месте.</p>
        </div>
        <button className="secondary" onClick={() => void load()}>
          Обновить
        </button>
      </div>
      {error && <ErrorBox text={error} retry={() => void load()} />}{" "}
      {deliveryError && <p className="small muted">{deliveryError}</p>}{" "}
      {loading ? (
        <p className="muted">Загружаем заказы…</p>
      ) : !orders.length ? (
        <Empty icon={<ShoppingBag />} title="Самое вкусное впереди">
          Вы ещё ничего не заказывали.
          <Link to="/" className="primary">
            Посмотреть меню <ArrowRight size={17} />
          </Link>
        </Empty>
      ) : (
        <div className="order-list">
          {orders.map((o) => {
            const p = payments.find((p) => p.order_id === o.id),
              d = deliveries.find((d) => d.order_id === o.id),
              item = items.find((i) => i.id === o.item_id);
            return (
              <OrderCard
                key={o.id}
                order={o}
                payment={p}
                delivery={d}
                item={item}
                busy={busy}
                onDetails={setDetailsId}
                onAction={action}
              />
            );
          })}
        </div>
      )}
      {detailsId !== null && orders.find((o) => o.id === detailsId) && (
        <OrderDetails
          order={orders.find((o) => o.id === detailsId)!}
          payment={payments.find((p) => p.order_id === detailsId)}
          delivery={deliveries.find((d) => d.order_id === detailsId)}
          item={items.find(
            (i) => i.id === orders.find((o) => o.id === detailsId)?.item_id,
          )}
          close={() => setDetailsId(null)}
        />
      )}
    </section>
  );
}
