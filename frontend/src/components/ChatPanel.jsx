import { useEffect, useRef, useState } from "react";
import { Icon } from "./Icons.jsx";
import AnswerMessage from "./AnswerMessage.jsx";
import FeedbackBar from "./FeedbackBar.jsx";

const SUGGESTIONS = [
  "ما هي فرائض الصلاة؟",
  "متى يكون سجود السهو قبل السلام؟",
  "ما هي مسافة قصر الصلاة للمسافر؟",
  "ما حكم من ضحك في الصلاة؟",
];

const time = (iso) => new Date(iso).toLocaleTimeString("ar-TN", { hour: "2-digit", minute: "2-digit" });

export default function ChatPanel({
  messages, loading, onAsk, madhahib, madhhab, onMadhhab, onOpen, onSave, savedIds,
  picks = {}, onPick, onClearPick, onFeedback,
}) {
  const [draft, setDraft] = useState("");
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length, loading]);

  function submit(e) {
    e?.preventDefault();
    const q = draft.trim();
    if (q.length < 2 || loading) return;
    onAsk(q);
    setDraft("");
  }

  return (
    <section className="panel chat">
      <div className="chips" role="tablist" aria-label="المذهب">
        {madhahib.map((m) => (
          <button key={m.key} role="tab" aria-selected={madhhab === m.key}
                  className={`chip ${madhhab === m.key ? "active" : ""}`}
                  disabled={!m.available} onClick={() => onMadhhab(m.key)}
                  title={m.available ? "" : "قريبًا"}>
            {m.label}{!m.available && <small> · قريبًا</small>}
          </button>
        ))}
      </div>

      <div className="messages">
        {messages.length === 0 && (
          <div className="empty">
            <Icon.Lantern width={56} height={56} className="empty-icon" />
            <h2>اسأل عن أحكام الصلاة</h2>
            <p>الأجوبة مستخرجة من <b>الرسالة</b> لابن أبي زيد القيرواني و<b>مختصر الأخضري</b> فقط، مع نقل الدليل من النص.</p>
            <div className="suggestions">
              {SUGGESTIONS.map((s) => (
                <button key={s} className="suggestion" onClick={() => onAsk(s)}>{s}</button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m) => {
          if (m.role === "user") {
            return (
              <div key={m.id} className="msg user">
                <div className="bubble">{m.text}</div>
                <time>{time(m.time)}</time>
              </div>
            );
          }
          if (m.role === "error") {
            return (
              <div key={m.id} className="msg error"><Icon.Alert /> {m.text}</div>
            );
          }
          return (
            <AnswerMessage key={m.id} result={m.result} onOpen={onOpen}
                           onSave={() => onSave(m)} isSaved={savedIds.has(m.id)}>
              <FeedbackBar msg={m} picked={picks[m.id]} onPick={() => onPick(m)}
                           onClearPick={() => onClearPick(m.id)}
                           onSend={(rating, extra) => onFeedback(m, rating, extra)} />
            </AnswerMessage>
          );
        })}

        {loading && (
          <div className="msg assistant typing" aria-live="polite">
            <span className="dots"><i /><i /><i /></span> جارٍ البحث في المصادر…
          </div>
        )}
        <div ref={endRef} />
      </div>

      <form className="composer" onSubmit={submit}>
        <textarea rows={1} value={draft} placeholder="اسأل عن مسألة في الصلاة..."
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) submit(e); }}
                  aria-label="سؤالك" />
        <button className="send" type="submit" disabled={loading || draft.trim().length < 2} aria-label="إرسال">
          <Icon.Send />
        </button>
      </form>
    </section>
  );
}
