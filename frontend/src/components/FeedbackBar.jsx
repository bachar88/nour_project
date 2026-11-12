import { useState } from "react";
import { Icon } from "./Icons.jsx";

// 👍 / 👎 under an answer. 👎 opens a small form: what was wrong + "pick the correct sentence"
// in the reader. Reports are stored for review; answers only change after a reviewer accepts them.
export default function FeedbackBar({ msg, picked, onPick, onClearPick, onSend }) {
  const [open, setOpen] = useState(false);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const state = msg.feedback; // undefined | "up" | "down"
  const canPick = msg.result.passages.length > 0;

  async function send(rating) {
    setBusy(true);
    setError("");
    try {
      await onSend(rating, rating === -1 ? { comment: comment.trim() || null, picked } : {});
      setOpen(false);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  if (state) {
    return (
      <p className="feedback-done">
        <Icon.Check width={14} height={14} />
        {state === "up" ? "شكرًا على تقييمك." : "شكرًا، وصلت ملاحظتك وستُراجَع لتحسين الأجوبة."}
      </p>
    );
  }

  return (
    <div className="feedback">
      <div className="feedback-row">
        <span className="muted">هل كان الجواب صحيحًا؟</span>
        <button className="icon-btn" disabled={busy} onClick={() => send(1)} aria-label="جواب صحيح" title="جواب صحيح">
          <Icon.ThumbUp width={18} height={18} />
        </button>
        <button className={`icon-btn ${open ? "active" : ""}`} disabled={busy} onClick={() => setOpen((v) => !v)}
                aria-label="جواب خاطئ" title="جواب خاطئ" aria-expanded={open}>
          <Icon.ThumbDown width={18} height={18} />
        </button>
      </div>

      {open && (
        <div className="feedback-form">
          <textarea rows={2} value={comment} maxLength={1000} onChange={(e) => setComment(e.target.value)}
                    placeholder="ما الخطأ في الجواب؟ (اختياري)" aria-label="ملاحظتك" />
          {picked ? (
            <div className="picked">
              <span className="muted">الجملة الصحيحة:</span>
              <p className="source-text">«{picked.quote}»</p>
              <button className="link" onClick={onClearPick}>إزالة</button>
            </div>
          ) : canPick ? (
            <button className="btn btn-outline" onClick={onPick}>
              <Icon.Cursor width={16} height={16} /> اختر الجملة الصحيحة من الكتاب
            </button>
          ) : null}
          {error && <p className="note warn"><Icon.Alert width={16} height={16} /> {error}</p>}
          <div className="feedback-actions">
            <button className="btn btn-primary" disabled={busy} onClick={() => send(-1)}>
              {busy ? "جارٍ الإرسال…" : "إرسال الملاحظة"}
            </button>
            <button className="btn btn-ghost" onClick={() => setOpen(false)}>إلغاء</button>
          </div>
        </div>
      )}
    </div>
  );
}
