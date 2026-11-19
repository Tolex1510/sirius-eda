import type { Metadata } from "next";
import Link from "next/link";
import { cabinetUrl } from "@/lib/api";
import "./globals.css";
export const metadata: Metadata = {
  metadataBase: new URL(process.env.SITE_URL || "http://localhost:8080"),
  title: { default: "Меню столовой · Сириус.Еда", template: "%s · Сириус.Еда" },
  description:
    "Свежие блюда столовой: выбирайте обед, смотрите цены и заказывайте в Сириус.Еде.",
  openGraph: {
    type: "website",
    locale: "ru_RU",
    siteName: "Сириус.Еда",
    images: ["/menu-preview.svg"],
  },
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ru">
      <body>
        <header className="site-header">
          <div className="container header-inner">
            <Link href="/menu" className="brand">
              <span className="brand-mark">✳</span> сириус.еда
            </Link>
            <nav aria-label="Главная навигация">
              <Link href="/menu">Меню</Link>
              <a href={cabinetUrl("/orders")}>Мои заказы</a>
              <a href={cabinetUrl("/assistant")}>Помощник</a>
            </nav>
            <a className="account-button" href={cabinetUrl("/orders")}>
              Личный кабинет ↗
            </a>
          </div>
        </header>
        {children}
        <footer className="container footer-inner">
          <Link className="brand" href="/menu">
            ✳ сириус.еда
          </Link>
          <p>Больше времени на жизнь. Меньше — на выбор обеда.</p>
          <Link href="/menu-csr">Сравнить с CSR</Link>
        </footer>
      </body>
    </html>
  );
}
