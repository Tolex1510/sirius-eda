"use client";
import { useRouter } from "next/navigation";
import { startTransition } from "react";
export default function MenuError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const router = useRouter();
  return (
    <main className="container page">
      <section className="error-state" role="alert">
        <span className="eyebrow">НУЖНО НЕМНОГО ВРЕМЕНИ</span>
        <h1>Не удалось загрузить меню</h1>
        <p>Сервис временно недоступен. Попробуйте ещё раз чуть позже.</p>
        <button
          className="primary"
          onClick={() =>
            startTransition(() => {
              router.refresh();
              reset();
            })
          }
        >
          Попробовать снова
        </button>
      </section>
    </main>
  );
}
