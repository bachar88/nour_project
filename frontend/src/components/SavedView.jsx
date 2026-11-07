import { Icon } from "./Icons.jsx";
import { BOOK_STYLE } from "../highlight.jsx";

export default function SavedView({ saved, onOpen, onRemove }) {
  return (
    <section className="panel saved">
      <h2 className="panel-title"><Icon.Bookmark /> حفظي</h2>
      {saved.length === 0 && (
        <div className="empty small">
          <p>لا توجد أجوبة محفوظة بعد. اضغط «حفظ» تحت أي جواب لتجده هنا.</p>
        </div>
      )}
      <div className="saved-list">
        {saved.map((item) => (
          <article key={item.id} className="saved-card">
            <header>
              <h3>{item.question}</h3>
              <button className="icon-btn" onClick={() => onRemove(item.id)} aria-label="حذف من المحفوظات">
                <Icon.Trash width={18} height={18} />
              </button>
            </header>
            <p className="answer-text">{item.result.answer}</p>
            {item.result.evidence.filter((e) => e.found).map((ev, i) => {
              const p = item.result.passages[(ev.passage || 1) - 1];
              return (
                <div key={i} className="saved-ev">
                  <span className={`tag small ${BOOK_STYLE[p?.book_key] || "tag-maroon"}`}>{p?.book}</span>
                  <p className="source-text">«{ev.quote}»</p>
                  <button className="link" onClick={() => onOpen({
                    bookKey: p.book_key, babIndex: p.bab_index, unitKey: ev.unit_key, spans: ev.spans,
                  })}>افتح في الكتاب</button>
                </div>
              );
            })}
            <time>{new Date(item.time).toLocaleDateString("ar-TN")}</time>
          </article>
        ))}
      </div>
    </section>
  );
}
