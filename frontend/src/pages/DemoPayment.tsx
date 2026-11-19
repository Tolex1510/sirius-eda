import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Check, ShoppingBag } from "lucide-react";
import { api, post } from "../lib/api";
import { message, rub } from "../lib/format";
import type { Payment, User } from "../types";
import { ErrorBox } from "../components/ui/ErrorBox";
import { Badge } from "../components/ui/Badge";

export function DemoPayment({
  user,
  login,
}: {
  user: User | null;
  login: () => void;
}) {
  const { id } = useParams(),
    [payment, setPayment] = useState<Payment | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  useEffect(() => {
    if (user && id)
      api<Payment>(`/payments/${id}`)
        .then(setPayment)
        .catch((err) => setError(message(err)));
  }, [id, user?.id]);
  async function finish(status: "succeeded" | "canceled") {
    setBusy(true);
    try {
      await post(`/payments/${id}/demo`, { status });
      navigate("/orders", { replace: true });
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="payment-page">
      <Link to="/orders" className="back">
        <ArrowLeft size={17} /> К заказам
      </Link>
      <div className="payment-panel">
        <div className="payment-icon">
          <ShoppingBag size={30} />
        </div>
        <span className="eyebrow">БЕЗ СПИСАНИЯ ДЕНЕГ</span>
        <h1>Проверим оплату?</h1>
        <p className="muted">
          Это демонстрационный шлюз учебного проекта.
          <br />
          Данные банковской карты не нужны.
        </p>
        {error && <ErrorBox text={error} />}{" "}
        {!user ? (
          <button className="primary full" onClick={login}>
            Войти в аккаунт
          </button>
        ) : !payment ? (
          !error && <p>Загружаем платёж…</p>
        ) : payment.provider !== "demo" ? (
          <ErrorBox text="Для этого платежа используется внешний шлюз." />
        ) : (
          <>
            <div className="payment-amount">{rub(payment.amount)}</div>
            <p className="small muted">Заказ №{payment.order_id}</p>
            {["succeeded", "canceled"].includes(payment.status) ? (
              <>
                <Badge status={payment.status} />
                <Link className="primary full" to="/orders">
                  К моим заказам
                </Link>
              </>
            ) : (
              <>
                <button
                  className="primary full"
                  disabled={busy}
                  onClick={() => void finish("succeeded")}
                >
                  <Check size={18} /> Подтвердить тестовую оплату
                </button>
                <button
                  className="text-button full"
                  disabled={busy}
                  onClick={() => void finish("canceled")}
                >
                  Проверить отказ оплаты
                </button>
              </>
            )}
          </>
        )}
      </div>
    </section>
  );
}
