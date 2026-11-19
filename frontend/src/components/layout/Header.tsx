import { Link, NavLink } from "react-router-dom";
import { LogOut, Sparkles, UserRound } from "lucide-react";
import type { User } from "../../types";

export function Header({
  user,
  sessionReady,
  login,
  logout,
}: {
  user: User | null;
  sessionReady: boolean;
  login: () => void;
  logout: () => void;
}) {
  return (
    <header className="site-header">
      <div className="header-inner">
        <Link className="brand" to="/" aria-label="Сириус.Еда — главная">
          <span className="brand-mark">✳</span>
          <span>
            сириус<span className="brand-dot">.</span>еда
          </span>
        </Link>
        <nav aria-label="Основная навигация">
          <a href="/menu">Меню</a>
          <NavLink to="/orders">Мои заказы</NavLink>
          <NavLink to="/assistant">
            <Sparkles size={15} /> Ассистент
          </NavLink>
          {user && ["cook", "courier", "admin"].includes(user.role) && (
            <NavLink to="/operations">Работа</NavLink>
          )}
        </nav>
        <div className="header-account">
          <span className="test-tag">Учебный проект</span>
          {user ? (
            <>
              <span className="account-name" title={user.email}>
                <UserRound size={17} />
                {user.email.split("@")[0]}
              </span>
              <button className="icon" aria-label="Выйти" onClick={logout}>
                <LogOut size={18} />
              </button>
            </>
          ) : (
            <button
              className="login-button"
              disabled={!sessionReady}
              onClick={login}
            >
              <UserRound size={17} /> Войти
            </button>
          )}
        </div>
      </div>
    </header>
  );
}
