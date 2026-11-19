import { ArrowRight, Truck } from "lucide-react";
import { labels, rub } from "../../lib/format";
import type { Delivery, Item, Order, Payment } from "../../types";
import { Badge } from "../ui/Badge";
import { FoodArt } from "../menu/FoodArt";

export function OrderCard({
  order: o,
  payment: p,
  delivery: d,
  item,
  busy,
  onDetails,
  onAction,
}: {
  order: Order;
  payment?: Payment;
  delivery?: Delivery;
  item?: Item;
  busy: number | null;
  onDetails: (id: number) => void;
  onAction: (order: Order, cancel?: boolean) => Promise<void>;
}) {
  return (
    <article className="order-card" key={o.id}>
      <div className="order-head">
        <span>
          Заказ №{o.id}{" "}
          <small>
            {o.created_at
              ? new Date(o.created_at).toLocaleString("ru-RU", {
                  day: "numeric",
                  month: "long",
                  hour: "2-digit",
                  minute: "2-digit",
                })
              : ""}
          </small>
        </span>
        <Badge status={o.status} />
      </div>
      <div className="order-content">
        <FoodArt imageUrl={item?.image_url} name={item?.name || ""} category="" />
        <div>
          <h3>{item?.name || `Блюдо №${o.item_id}`}</h3>
          <p>
            {o.quantity} {o.quantity === 1 ? "порция" : "порц."}
          </p>
          {d && (
            <p className="delivery-status">
              <Truck size={15} />
              {labels[d.status] || d.status}
            </p>
          )}
        </div>
        <strong>{rub(o.total_cost)}</strong>
      </div>
      <div className="order-foot">
        <div>
          {p ? (
            <span className="small">
              {p.provider === "demo" ? "Демо-оплата" : "ЮKassa"}:{" "}
              {labels[p.status] || p.status}
              {p.review_required && " · Требуется ручная сверка"}
              {p.cancellation_reason &&
                ` · ${p.cancellation_reason === "insufficient_funds" ? "Недостаточно средств на карте" : "Причина: " + p.cancellation_reason}`}
              {p.refund_status && (
                <>
                  {" "}
                  · Возврат:{" "}
                  {p.refund_status === "succeeded"
                    ? "подтверждён"
                    : p.refund_status === "pending"
                      ? "ожидает подтверждения"
                      : p.refund_status}
                </>
              )}
            </span>
          ) : (
            <span className="small muted">
              {o.payment_source === "gateway"
                ? "Оплата ещё не создана"
                : "Внутренний баланс"}
            </span>
          )}
        </div>
        <div className="actions">
          <button className="text-button" onClick={() => onDetails(o.id)}>
            Подробнее
          </button>
          {o.payment_source === "gateway" &&
            o.status === "processing" &&
            p?.status !== "canceled" && (
              <button
                className="primary small-button"
                disabled={busy === o.id}
                onClick={() => void onAction(o)}
              >
                Оплатить <ArrowRight size={15} />
              </button>
            )}
          {o.payment_source === "gateway" &&
            ["processing", "paid"].includes(o.status) &&
            !["on_the_way", "completed"].includes(d?.status || "") && (
              <button
                className="text-button"
                disabled={busy === o.id}
                onClick={() => {
                  if (
                    window.confirm(
                      `Отменить заказ №${o.id}? Подтверждённая оплата будет возвращена.`,
                    )
                  )
                    void onAction(o, true);
                }}
              >
                Отменить
              </button>
            )}
        </div>
      </div>
    </article>
  );
}
