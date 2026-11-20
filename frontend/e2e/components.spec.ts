import { test, expect, type Page } from "@playwright/test";
import type { Delivery, Order, Payment, User } from "../src/types";

// Проверяем связность компонентов без Docker и обращений к платёжному провайдеру.
async function fixtureApi(page: Page) {
  const items = [
    {
      id: 1,
      name: "Сырники со сметаной",
      price: 190,
      is_available: true,
      category_id: 1,
    },
    { id: 2, name: "Кофе", price: 110, is_available: true, category_id: 2 },
  ];
  let user: User | null = null;
  let order: Order | null = null;
  let payment: Payment | null = null;
  let delivery: Delivery | null = null;
  let failMenu = false;
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname.replace(/^\/api/, "");
    const body = request.postDataJSON();
    const reply = (json: unknown, status = 200) =>
      route.fulfill({ status, json });
    if (path === "/menu/items")
      return failMenu
        ? reply({ detail: "Меню недоступно" }, 503)
        : reply(items);
    if (path === "/menu/search")
      return reply({items: [items[0]], mode: "semantic", explanation: {constraints: ["Без мяса"], ranking: "Сначала ограничения, затем близость описаний"}});
    if (path === "/menu/categories")
      return reply([
        { id: 1, name: "Завтраки" },
        { id: 2, name: "Напитки" },
      ]);
    if (path === "/auth/session/refresh")
      return user ? reply({ access_token: "fixture-token" }) : reply({}, 401);
    if (path === "/users/register") return reply({ status: "success" });
    if (path === "/auth/session/login") {
      const courier = body.email.startsWith("courier");
      user = {
        id: courier ? 2 : 1,
        email: body.email,
        role: courier ? "courier" : "student",
        balance: 0,
      };
      if (courier)
        delivery = {
          id: 20,
          order_id: 99,
          courier_id: 2,
          status: "in_progress",
        };
      return reply({ access_token: "fixture-token" });
    }
    if (path === "/auth/session/logout") {
      user = null;
      return reply({});
    }
    if (path === "/users/me") return reply(user);
    if (path === "/payments/checkout") {
      order = {
        id: 1,
        item_id: body.item_id,
        quantity: body.quantity,
        total_cost: 190 * body.quantity,
        payment_source: "gateway",
        status: "processing",
        created_at: "2026-11-10T12:00:00Z",
      };
      return reply(order, 201);
    }
    if (path === "/payments" && request.method() === "POST") {
      payment = {
        id: "fixture-payment",
        order_id: 1,
        amount: String(order!.total_cost),
        provider: "demo",
        status: "pending",
        confirmation_url: "/payment/demo/fixture-payment",
        refund_status: null,
        review_required: false,
        cancellation_reason: null,
      };
      return reply(payment);
    }
    if (path === "/payments/fixture-payment/demo") {
      payment!.status = body.status;
      if (body.status === "succeeded") {
        order!.status = "paid";
        delivery = {
          id: 10,
          order_id: 1,
          courier_id: 2,
          status: "in_progress",
        };
      }
      return reply(payment);
    }
    if (path === "/payments/fixture-payment") return reply(payment);
    if (path === "/payments") return reply(payment ? [payment] : []);
    if (path === "/orders/my") return reply(order ? [order] : []);
    if (path === "/delivery/my") return reply(delivery ? [delivery] : []);
    if (path.endsWith("/track"))
      return route.fulfill({
        contentType: "text/event-stream",
        body: `event: status\ndata: ${JSON.stringify({ status: delivery?.status })}\n\n`,
      });
    if (path === "/payments/orders/1/cancel") {
      order!.status = "cancelled";
      payment!.refund_status = "succeeded";
      delivery!.status = "cancelled";
      return reply({ status: "success" });
    }
    if (path === "/assistant/messages")
      return reply({
        conversation_id: "fixture-chat",
        answer: "Ваш заказ отменён, возврат подтверждён.",
        available: true,
        sources: [{ id: "order-1", text: "Заказ №1", url: "/orders" }],
        latency_ms: 1,
      });
    if (path === "/delivery/20/pickup") {
      delivery!.status = "on_the_way";
      return reply({});
    }
    if (path === "/delivery/20/complete") {
      delivery!.status = "completed";
      return reply({});
    }
    throw new Error(
      `Unexpected fixture API request: ${request.method()} ${path}`,
    );
  });
  return {
    setMenuFailure: (failed: boolean) => {
      failMenu = failed;
    },
  };
}

async function login(page: Page, email: string) {
  await page.getByLabel("Электронная почта").fill(email);
  await page.getByLabel("Пароль", { exact: true }).fill("fixture-password");
  await page.getByRole("button", { name: "Войти", exact: true }).last().click();
}

test("components keep registration, checkout, orders, chat and courier operations connected", async ({
  page,
}) => {
  await fixtureApi(page);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await expect(page.locator(".food-card")).toHaveCount(2);
  await page.getByLabel("Поиск по названию").fill("Кофе");
  await expect(page.locator(".food-card")).toHaveCount(1);
  await page.getByRole("button", { name: "Очистить", exact: true }).click();
  await page.getByRole("button", { name: "Напитки", exact: true }).click();
  await expect(page.locator(".food-card")).toHaveCount(1);
  await page.getByRole("button", { name: "Всё меню" }).click();
  await page
    .getByRole("button", { name: "Заказать: Сырники со сметаной" })
    .click();
  await page.getByRole("button", { name: "Увеличить количество" }).click();
  await expect(page.locator(".checkout-total")).toContainText("380");
  await page.getByRole("button", { name: "Войти и заказать" }).click();
  await page
    .getByRole("button", { name: "Первый раз здесь? Зарегистрироваться" })
    .click();
  await page.getByLabel("Электронная почта").fill("student@example.ru");
  await page.getByLabel("Пароль", { exact: true }).fill("fixture-password");
  await page.getByRole("button", { name: "Создать аккаунт" }).click();
  await page.getByRole("button", { name: "Перейти к оплате" }).click();
  await page
    .getByRole("button", { name: "Подтвердить тестовую оплату" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Мои заказы", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".order-card .badge.paid")).toBeVisible();
  await page.reload();
  await expect(page.locator(".order-card .badge.paid")).toBeVisible();
  await page.getByRole("button", { name: "Подробнее", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("Курьер №2");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Отменить", exact: true }).click();
  await expect(page.locator(".order-card")).toContainText(
    "Возврат: подтверждён",
  );
  await page.getByRole("link", { name: "Ассистент", exact: true }).click();
  await page
    .getByRole("button", { name: "Что с моим последним заказом?" })
    .click();
  await expect(page.locator(".chat-bubble.assistant")).toContainText(
    "возврат подтверждён",
  );
  await page.getByRole("button", { name: "Выйти", exact: true }).click();
  await page.getByRole("button", { name: "Войти", exact: true }).click();
  await login(page, "courier@example.ru");
  await page.getByRole("link", { name: "Работа", exact: true }).click();
  await page.getByRole("button", { name: "Забрал на кухне" }).click();
  await page.getByRole("button", { name: "Передал заказ" }).click();
  await expect(page.locator(".order-card .badge.completed")).toBeVisible();
  await page.getByRole("link", { name: "Как это работает" }).click();
  await expect(
    page.getByRole("heading", { name: "Простой путь к обеду" }),
  ).toBeVisible();
  await page.goto("/missing-page");
  await expect(
    page.getByRole("heading", { name: "Страница не найдена" }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});

test("menu error retry and checkout modal still work on a mobile screen", async ({
  page,
}) => {
  const api = await fixtureApi(page);
  api.setMenuFailure(true);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.getByRole("alert")).toContainText("Меню недоступно");
  api.setMenuFailure(false);
  await page.getByRole("button", { name: "Попробовать снова" }).click();
  await expect(page.locator(".food-card")).toHaveCount(2);
  await page.getByRole("button", { name: "Заказать: Кофе" }).click();
  await expect(page.getByRole("dialog")).toContainText("Кофе");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.getByRole("button", { name: "Закрыть", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
});


test("name search and wish selection stay separate", async ({ page }) => {
  await fixtureApi(page);
  let semanticCalls = 0;
  page.on("request", request => {
    if (new URL(request.url()).pathname === "/api/menu/search") semanticCalls++;
  });
  await page.goto("/");
  await expect(page.locator(".food-card")).toHaveCount(2);
  await page.getByLabel("Поиск по названию").fill("Кофе");
  await page.getByLabel("Поиск по названию").press("Enter");
  await expect(page.locator(".food-card")).toHaveCount(1);
  expect(semanticCalls).toBe(0);
  await page.getByRole("tab", { name: "По пожеланиям" }).click();
  await expect(page.getByLabel("Пожелания к блюду", { exact: true })).toHaveValue("");
  await page.getByLabel("Пожелания к блюду", { exact: true }).fill("Обед без мяса");
  await page.getByRole("button", { name: "Подобрать", exact: true }).click();
  await expect(page.getByText("Подобрано: 1", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Учтённые пожелания")).toContainText("Без мяса");
  expect(semanticCalls).toBe(1);
  await page.getByRole("tab", { name: "По названию" }).click();
  await expect(page.getByLabel("Поиск по названию")).toHaveValue("Кофе");
});
