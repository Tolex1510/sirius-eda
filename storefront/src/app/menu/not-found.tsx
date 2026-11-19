import Link from "next/link";
export default function NotFound() {
  return (
    <main className="container page">
      <section className="empty">
        <h1>Блюдо не найдено</h1>
        <p>Возможно, оно больше не входит в меню.</p>
        <Link href="/menu" className="primary">
          Вернуться к меню
        </Link>
      </section>
    </main>
  );
}
