import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Sparkles } from "lucide-react";
import { rub } from "../../lib/format";
import { trackDelivery } from "../../lib/api";
import type { Delivery, Item, Order, Payment } from "../../types";
import { Badge } from "../ui/Badge";
import { Modal } from "../ui/Modal";
import { FoodArt } from "../menu/FoodArt";

export function OrderDetails({
  order,
  payment,
  delivery,
  item,
  close,
}: {
  order: Order;
  payment?: Payment;
  delivery?: Delivery;
  item?: Item;
  close: () => void;
}) {
  const [status, setStatus] = useState(delivery?.status);
  useEffect(() => {
    if (!delivery) return;
    const controller = new AbortController();
    void trackDelivery(delivery.id, setStatus, controller.signal);
    return () => controller.abort();
  }, [delivery?.id]);
  return (
    <Modal title={`Заказ №${order.id}`} close={close}>
      <div className="checkout-item">
        <FoodArt imageUrl={item?.image_url} name={item?.name || ""} category="" />
        <div>
          <h3>{item?.name || `Блюдо №${order.item_id}`}</h3>
          <p>
            {order.quantity} порц. · {rub(order.total_cost)}
          </p>
        </div>
      </div>
      <div className="detail-line">
        <span>Заказ</span>
        <Badge status={order.status} />
      </div>
      <div className="detail-line">
        <span>Оплата</span>
        {payment ? (
          <Badge status={payment.status} />
        ) : (
          <span className="muted small">Ещё не создана</span>
        )}
      </div>
      {payment?.refund_status && (
        <div className="detail-line">
          <span>Возврат</span>
          <Badge status={payment.refund_status} />
        </div>
      )}
      <div className="detail-line">
        <span>Доставка</span>
        {status ? (
          <Badge status={status} />
        ) : (
          <span className="muted small">Курьер пока не назначен</span>
        )}
      </div>
      {delivery && (
        <p className="small muted">
          Доставка №{delivery.id} · Курьер №{delivery.courier_id}. Изменения
          статуса поступают автоматически.
        </p>
      )}
      <Link className="secondary full" to="/assistant" onClick={close}>
        <Sparkles size={16} /> Спросить помощника
      </Link>
    </Modal>
  );
}
