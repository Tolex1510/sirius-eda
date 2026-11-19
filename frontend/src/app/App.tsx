import { useEffect, useState } from "react";
import { Link, Route, Routes, useSearchParams } from "react-router-dom";
import { Search } from "lucide-react";
import type { Item } from "../types";
import { useSession } from "../hooks/useSession";
import { useMenu } from "../hooks/useMenu";
import { Header } from "../components/layout/Header";
import { Footer } from "../components/layout/Footer";
import { ErrorBox } from "../components/ui/ErrorBox";
import { Empty } from "../components/ui/Empty";
import { Checkout } from "../components/checkout/Checkout";
import { Login } from "../components/auth/Login";
import { Menu } from "../pages/Menu";
import { Orders } from "../pages/Orders";
import { Assistant } from "../pages/Assistant";
import { DemoPayment } from "../pages/DemoPayment";
import { Operations } from "../pages/Operations";
import { Help } from "../pages/Help";

export function App() {
  const { user, setUser, sessionReady, logoutError, logout } = useSession();
  const { items, categories, loading, error, load } = useMenu();
  const [loginOpen, setLoginOpen] = useState(false);
  const [selected, setSelected] = useState<Item | null>(null);
  const [query, setQuery] = useSearchParams();
  const requestedItem = Number(query.get("item"));

  useEffect(() => {
    if (!requestedItem || !items.length) return;
    const item = items.find((value) => value.id === requestedItem);
    if (item?.is_available) setSelected(item);
    setQuery(
      (previous) => {
        const next = new URLSearchParams(previous);
        next.delete("item");
        return next;
      },
      { replace: true },
    );
  }, [requestedItem, items, setQuery]);

  const login = () => setLoginOpen(true);
  const handleLogout = () => {
    void logout().then((ok) => {
      if (ok) setSelected(null);
    });
  };
  return (
    <>
      <Header
        user={user}
        sessionReady={sessionReady}
        login={login}
        logout={handleLogout}
      />
      <main className="container">
        {logoutError && <ErrorBox text={logoutError} />}
        <Routes>
          <Route
            path="/"
            element={
              <Menu
                {...{ items, categories, loading, error }}
                reload={() => void load()}
                choose={setSelected}
              />
            }
          />
          <Route
            path="/orders"
            element={
              sessionReady ? (
                <Orders {...{ user, login, items }} />
              ) : (
                <p className="muted page">Проверяем сессию…</p>
              )
            }
          />
          <Route
            path="/assistant"
            element={<Assistant {...{ user, login }} />}
          />
          <Route
            path="/payment/demo/:id"
            element={<DemoPayment {...{ user, login }} />}
          />
          <Route
            path="/operations"
            element={<Operations {...{ user, items }} />}
          />
          <Route path="/help" element={<Help />} />
          <Route
            path="*"
            element={
              <Empty icon={<Search />} title="Страница не найдена">
                <Link to="/">Вернуться к меню</Link>
              </Empty>
            }
          />
        </Routes>
      </main>
      <Footer />
      {selected && !loginOpen && (
        <Checkout
          item={selected}
          close={() => setSelected(null)}
          user={user}
          login={login}
        />
      )}
      {loginOpen && <Login done={setUser} close={() => setLoginOpen(false)} />}
    </>
  );
}
