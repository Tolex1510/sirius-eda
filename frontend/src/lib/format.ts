export const rub = (value: number | string) =>
  new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency: "RUB",
    maximumFractionDigits: 2,
  }).format(Number(value));
export const message = (error: unknown) =>
  error instanceof Error
    ? error.message
    : "Что-то пошло не так. Попробуйте ещё раз.";
export const labels: Record<string, string> = {
  processing: "Ожидает оплаты",
  paid: "Оплачен",
  delivered: "Доставлен",
  cancelled: "Отменён",
  canceled: "Оплата отклонена",
  creating: "Проверяем оплату",
  pending: "Ожидание",
  waiting_for_capture: "Подтверждение",
  succeeded: "Подтверждено",
  in_progress: "Курьер назначен",
  on_the_way: "В пути",
  completed: "Доставлен",
};
