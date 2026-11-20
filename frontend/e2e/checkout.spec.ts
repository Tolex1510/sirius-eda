import { test, expect, request } from "@playwright/test";

test("menu, registration, demo payment, refund, assistant fallback and responsive layout", async ({
  page,
}, testInfo) => {
  test.setTimeout(90000);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Обед по вашему вкусу" }),
  ).toBeVisible();
  await expect(page.locator(".food-card").first()).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("menu-desktop.png"),
    fullPage: true,
  });
  await page.getByLabel("Поиск по названию").fill("НетТакогоБлюда");
  await expect(
    page.getByRole("heading", { name: "Подходящих блюд не нашлось" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Очистить", exact: true }).click();
  await page
    .getByRole("button", { name: /^Заказать:/ })
    .first()
    .click();
  await page.getByRole("button", { name: "Войти и заказать" }).click();
  await page
    .getByRole("button", { name: "Первый раз здесь? Зарегистрироваться" })
    .click();
  const email = `browser-${Date.now()}@example.ru`;
  await page.getByLabel("Электронная почта").fill(email);
  await page
    .getByLabel("Пароль", { exact: true })
    .fill("browser-test-password");
  await page.getByRole("button", { name: "Создать аккаунт" }).click();
  await expect(
    page.getByRole("heading", { name: "Ваш вкусный выбор" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Перейти к оплате" }).click();
  await expect(
    page.getByRole("heading", { name: "Проверим оплату?" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Подтвердить тестовую оплату" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Мои заказы", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".badge.paid")).toBeVisible();
  // Session survives a full page reload without storing the refresh token in JS.
  await page.reload();
  await expect(page.locator(".badge.paid")).toBeVisible();
  if (process.env.DEMO_PASSWORD) {
    const origin = new URL(page.url()).origin;
    const courier = await request.newContext({ baseURL: origin });
    try {
      const login = await courier.post("/api/auth/login", {
        data: {
          email: "courier@demo.sirius.ru",
          password: process.env.DEMO_PASSWORD,
        },
      });
      expect(login.ok()).toBe(true);
      const headers = {
        Authorization: "Bearer " + (await login.json()).access_token,
      };
      const orderId = Number(
        (await page.locator(".order-head").innerText()).match(
          /Заказ №(\d+)/,
        )?.[1],
      );
      let delivery: { id: number } | undefined;
      await expect
        .poll(async () => {
          const response = await courier.get("/api/delivery/my", { headers });
          delivery = (await response.json()).find(
            (d: { order_id: number; status: string }) =>
              d.order_id === orderId && d.status === "in_progress",
          );
          return !!delivery;
        })
        .toBe(true);
      await page.getByRole("button", { name: "Подробнее" }).click();
      const pickup = await courier.patch(
        `/api/delivery/${delivery!.id}/pickup`,
        { headers },
      );
      expect(pickup.ok()).toBe(true);
      await expect(page.locator(".modal .badge.on_the_way")).toBeVisible({
        timeout: 15000,
      });
      const complete = await courier.patch(
        `/api/delivery/${delivery!.id}/complete`,
        { headers },
      );
      expect(complete.ok()).toBe(true);
      await expect(page.locator(".modal .badge.completed")).toBeVisible({
        timeout: 15000,
      });
      await page.getByRole("button", { name: "Закрыть", exact: true }).click();
      // A second order exercises cancellation/refund independently from the delivered one.
      // Continue the SPA checkout flow; header menu links to the separate SSR storefront.
      await page.goto("/");
      await page
        .getByRole("button", { name: /^Заказать:/ })
        .first()
        .click();
      await page.getByRole("button", { name: "Перейти к оплате" }).click();
      await page
        .getByRole("button", { name: "Подтвердить тестовую оплату" })
        .click();
      await expect(page.locator(".badge.paid")).toBeVisible();
    } finally {
      await courier.dispose();
    }
  }
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Отменить", exact: true }).click();
  await expect(page.locator(".badge.cancelled")).toBeVisible();
  await expect(page.getByText(/Возврат: подтверждён/)).toBeVisible({
    timeout: 45000,
  });
  await page.getByRole("link", { name: "Ассистент", exact: true }).click();
  await page.getByRole("button", { name: "Как проходит оплата?" }).click();
  await expect(
    page.getByText(/Локальная AI-модель пока недоступна/),
  ).toBeVisible({ timeout: 20000 });
  await page.screenshot({
    path: testInfo.outputPath("assistant-desktop.png"),
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  // Continue the SPA checkout flow; header menu links to the separate SSR storefront.
      await page.goto("/");
  await page.screenshot({
    path: testInfo.outputPath("menu-mobile.png"),
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  expect(await page.evaluate(() => Object.keys(localStorage))).toEqual([]);
  expect(errors).toEqual([]);
});
