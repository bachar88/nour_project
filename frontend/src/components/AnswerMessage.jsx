import { useState } from "react";
import { Icon } from "./Icons.jsx";
import { BOOK_STYLE } from "../highlight.jsx";

function GroundingBadge({ found }) {
  return found ? (
    <span className="badge ok" title="الاقتباس موجود حرفيًا في النص المسترجع">
      <Icon.Check width={14} height={14} /> الاقتباس موجود في النص
    </span>
  ) : (
    <span className="badge warn" title="لم يُعثر على هذا الاقتباس في النص: قد يكون من اختلاق النموذج">
      <Icon.Alert width={14} height={14} /> لم يُعثر عليه في النص
    </span>
  );
}

function EvidenceCard({ ev, passage, onOpen }) {
  const bookKey = passage?.book_key;
  return (
    <article className={`source-card ${ev.found ? "" : "unverified"}`}>
      <header className="source-head">
        <span className={`tag ${BOOK_STYLE[bookKey] || "tag-maroon"}`}>{passage?.book || "مصدر"}</span>
        <GroundingBadge found={ev.found} />
      </header>
      <p className="source-text">«{ev.quote}»</p>
      {passage && (
        <p className="source-meta">
          {passage.author} — {passage.bab_title} · رقم {passage.unit_number}
        </p>
      )}
      {ev.found && ev.unit_key && (
        <div className="source-actions">
          <button className="btn btn-primary" onClick={() => onOpen({
            bookKey, babIndex: passage.bab_index, unitKey: ev.unit_key, spans: ev.spans,
          })}>
            <Icon.BookOpen width={16} height={16} /> افتح في الكتاب
          </button>
        </div>
      )}
    </article>
  );
}

export default function AnswerMessage({ result, onOpen, onSave, isSaved, children }) {
  const [showSources, setShowSources] = useState(false);
  const abstained = Boolean(result.abstained);

  return (
    <div className="msg assistant">
      {abstained ? (
        <div className="abstain">
          <Icon.BookOpen />
          <div>
            <strong>{result.answer}</strong>
            <p>
              {result.abstained === "retrieval"
                ? "لم نجد في الرسالة ولا في مختصر الأخضري مقطعًا قريبًا بما يكفي من سؤالك، فلم نُرسل السؤال إلى النموذج."
                : "اطّلع النموذج على أقرب المقاطع ورأى أنها لا تجيب عن السؤال صراحة."}
            </p>
          </div>
        </div>
      ) : (
        <>
          <p className="answer-text">{result.answer}</p>
          {result.grounding === "no_quote" && (
            <p className="note warn"><Icon.Alert width={16} height={16} /> لم يذكر النموذج دليلًا منقولًا من النص، فتحقّق من المقاطع المسترجعة.</p>
          )}
          {result.evidence.map((ev, i) => (
            <EvidenceCard key={i} ev={ev} passage={result.passages[(ev.passage || 1) - 1]} onOpen={onOpen} />
          ))}
        </>
      )}

      <footer className="msg-footer">
        {result.passages.length > 0 && (
          <button className="btn btn-ghost" onClick={() => setShowSources((v) => !v)} aria-expanded={showSources}>
            المقاطع المسترجعة ({result.passages.length})
            <Icon.ChevronDown width={16} height={16} className={showSources ? "flip" : ""} />
          </button>
        )}
        {!abstained && (
          <button className={`btn btn-outline ${isSaved ? "saved" : ""}`} onClick={onSave}>
            {isSaved ? <Icon.BookmarkFilled width={16} height={16} /> : <Icon.Bookmark width={16} height={16} />}
            {isSaved ? "محفوظ" : "حفظ"}
          </button>
        )}
      </footer>

      {children}

      {showSources && (
        <ol className="passages">
          {result.passages.map((p, i) => (
            <li key={p.unit_key + i}>
              <div className="passage-head">
                <span className={`tag small ${BOOK_STYLE[p.book_key] || "tag-maroon"}`}>{p.book}</span>
                <span className="passage-bab">{p.bab_title}</span>
                <span className="score" title="درجة الصلة بالسؤال">{Math.round(p.score * 100)}%</span>
              </div>
              <p>{p.text.length > 320 ? p.text.slice(0, 320) + "…" : p.text}</p>
              <button className="link" onClick={() => onOpen({ bookKey: p.book_key, babIndex: p.bab_index, unitKey: p.unit_key, spans: [] })}>
                افتح في الكتاب
              </button>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
