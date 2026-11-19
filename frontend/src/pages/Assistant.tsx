import { useEffect, useState, useRef } from "react";
import {
  ArrowRight,
  Plus,
  Send,
  ShoppingBag,
  Sparkles,
  Utensils,
} from "lucide-react";
import { message } from "../lib/format";
import { post } from "../lib/api";
import type { Reply, Source, User } from "../types";
import { ErrorBox } from "../components/ui/ErrorBox";

export function Assistant({
  user,
  login,
}: {
  user: User | null;
  login: () => void;
}) {
  const [messages, setMessages] = useState<
      { role: string; text: string; sources?: Source[] }[]
    >([]),
    [input, setInput] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [conversation, setConversation] = useState<string | undefined>(),
    bottom = useRef<HTMLDivElement>(null);
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);
  useEffect(() => {
    setMessages([]);
    setConversation(undefined);
    setError("");
  }, [user?.id]);
  async function send(text: string) {
    if (!user) {
      login();
      return;
    }
    if (!text.trim() || busy) return;
    setInput("");
    setError("");
    setBusy(true);
    setMessages((prev) => [...prev, { role: "user", text }]);
    try {
      const r = await post<Reply>("/assistant/messages", {
        message: text,
        conversation_id: conversation,
      });
      setConversation(r.conversation_id);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: r.answer, sources: r.sources },
      ]);
    } catch (err) {
      setError(message(err));
      setInput(text);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="chat-page">
      <aside className="chat-aside">
        <div className="banner-icon">
          <Sparkles size={28} />
        </div>
        <span className="eyebrow">СИРИУС.ПОМОЩНИК</span>
        <h1>
          Чем помочь
          <br />
          сегодня?
        </h1>
        <p>Подскажу по меню и помогу разобраться с вашим заказом.</p>
        <div className="assistant-feature">
          <Utensils size={18} />
          <div>
            <strong>Меню и цены</strong>
            <p>Найдём что-нибудь вкусное</p>
          </div>
        </div>
        <div className="assistant-feature">
          <ShoppingBag size={18} />
          <div>
            <strong>Ваши заказы</strong>
            <p>Оплата, доставка и возврат</p>
          </div>
        </div>
        <p className="small muted">
          Ответы создаёт локальная модель. Проверяйте важные сведения по
          источникам и в карточке заказа.
        </p>
        <button
          className="text-button"
          onClick={() => {
            setMessages([]);
            setConversation(undefined);
            setError("");
          }}
        >
          Начать новый разговор <Plus size={16} />
        </button>
      </aside>
      <div className="chat-panel">
        <div className="chat-title">
          <span className="online-dot" />
          <strong>Помощник по вашему обеду</strong>
          <span className="small muted">AI</span>
        </div>
        <div className="chat-messages" aria-live="polite">
          {!messages.length && (
            <div className="chat-welcome">
              <Sparkles size={34} />
              <h2>Привет! Давайте выберем обед.</h2>
              <p>Или разберёмся, что происходит с заказом.</p>
              <div className="suggestions">
                {[
                  "Что есть в меню?",
                  "Как проходит оплата?",
                  "Что с моим последним заказом?",
                  "Как работает возврат?",
                ].map((q) => (
                  <button key={q} onClick={() => void send(q)}>
                    {q}
                    <ArrowRight size={15} />
                  </button>
                ))}
              </div>
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} className={"chat-bubble " + m.role}>
              {m.role === "assistant" && (
                <span className="bubble-name">
                  <Sparkles size={13} /> Сириус.Помощник
                </span>
              )}
              <p>{m.text}</p>
              {!!m.sources?.length && (
                <details>
                  <summary>Источники · {m.sources.length}</summary>
                  {m.sources.map((s) => (
                    <a key={s.id} href={s.url} className="source">
                      {s.text.slice(0, 140)}
                    </a>
                  ))}
                </details>
              )}
            </div>
          ))}
          {busy && (
            <div className="thinking">
              <span />
              <span />
              <span /> Ищу ответ. Первый запуск модели может занять больше
              времени.
            </div>
          )}
          <div ref={bottom} />
        </div>
        {error && <ErrorBox text={error} />}
        <form
          className="chat-compose"
          onSubmit={(e) => {
            e.preventDefault();
            void send(input);
          }}
        >
          <input
            aria-label="Сообщение ассистенту"
            value={input}
            maxLength={2000}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Спросите о меню или своём заказе…"
            disabled={busy}
          />
          <button
            aria-label="Отправить сообщение"
            className="primary"
            disabled={busy || !input.trim()}
          >
            <Send size={18} />
          </button>
        </form>
        <p className="chat-caption">
          Ассистент не проводит оплату и не отменяет заказы за вас.
        </p>
      </div>
    </section>
  );
}
