import { useState } from "react";
import type { FormEvent } from "react";
import { ArrowRight } from "lucide-react";
import { message } from "../../lib/format";
import { post, signIn } from "../../lib/api";
import type { User } from "../../types";
import { ErrorBox } from "../ui/ErrorBox";
import { Modal } from "../ui/Modal";

export function Login({
  done,
  close,
}: {
  done: (u: User) => void;
  close: () => void;
}) {
  const [register, setRegister] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const values = new FormData(e.currentTarget),
      email = String(values.get("email")),
      password = String(values.get("password"));
    try {
      if (register) await post("/users/register", { email, password });
      done(await signIn(email, password));
      close();
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      title={register ? "Давайте знакомиться" : "С возвращением"}
      close={close}
    >
      <p className="muted">
        {register
          ? "Создайте аккаунт, чтобы заказать обед."
          : "Войдите, чтобы ваши заказы были под рукой."}
      </p>
      <form onSubmit={submit} className="form">
        <label>
          Электронная почта
          <input
            name="email"
            type="email"
            required
            autoComplete="email"
            placeholder="you@example.ru"
          />
        </label>
        <label>
          Пароль
          <input
            name="password"
            type="password"
            minLength={8}
            maxLength={72}
            required
            autoComplete={register ? "new-password" : "current-password"}
            placeholder="Не менее 8 символов"
          />
        </label>
        {error && <ErrorBox text={error} />}
        <button className="primary" disabled={busy}>
          {busy ? "Подождите…" : register ? "Создать аккаунт" : "Войти"}
          <ArrowRight size={18} />
        </button>
      </form>
      <button
        className="text-button full"
        onClick={() => {
          setRegister(!register);
          setError("");
        }}
      >
        {register
          ? "Уже есть аккаунт? Войти"
          : "Первый раз здесь? Зарегистрироваться"}
      </button>
    </Modal>
  );
}
