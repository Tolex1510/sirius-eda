export default function Loading() {
  return (
    <main
      className="container page"
      aria-busy="true"
      aria-label="Загрузка меню"
    >
      <p role="status">Загружаем свежие блюда…</p>
      <div className="skeleton skeleton-title" />
      <div className="cards">
        {Array.from({ length: 6 }, (_, i) => (
          <div className="skeleton skeleton-card" key={i} />
        ))}
      </div>
    </main>
  );
}
