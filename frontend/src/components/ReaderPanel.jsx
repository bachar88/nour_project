import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { Icon } from "./Icons.jsx";
import { Highlighted } from "../highlight.jsx";

// Shows a whole bab as numbered cards; the cited unit is highlighted and scrolled into view.
export default function ReaderPanel({ target, onClose, onNavigate }) {
  const [bab, setBab] = useState(null);
  const [error, setError] = useState("");
  const focusRef = useRef(null);
  const listRef = useRef(null);

  useEffect(() => {
    let cancelled = false;
    setError("");
    api.bab(target.bookKey, target.babIndex)
      .then((data) => { if (!cancelled) setBab(data); })
      .catch((e) => { if (!cancelled) setError(e.message); });
    return () => { cancelled = true; };
  }, [target.bookKey, target.babIndex]);

  useEffect(() => {
    if (!bab) return;
    // Scroll to the highlighted quote itself (Al-Risala babs are one long card), else to the card.
    const mark = focusRef.current?.querySelector("mark");
    const el = mark || focusRef.current;
    if (el) el.scrollIntoView({ behavior: "smooth", block: mark ? "center" : "start" });
    else listRef.current?.scrollTo({ top: 0 });
  }, [bab, target.unitKey]);

  const loadingOther = bab && (bab.book_key !== target.bookKey || bab.bab_index !== target.babIndex);

  return (
    <section className="panel reader" aria-label="قارئ المصدر">
      <header className="reader-head">
        <div className="crumbs">
          <Icon.BookOpen />
          {bab ? (
            <>
              <span>{bab.book}</span>
              <Icon.ChevronLeft width={14} height={14} />
              <span className="current">{bab.bab_title}</span>
            </>
          ) : <span>…</span>}
        </div>
        <button className="btn btn-ghost" onClick={onClose}>
          رجوع <Icon.ArrowBack width={16} height={16} style={{ transform: "scaleX(-1)" }} />
        </button>
      </header>

      <div className={`reader-list ${loadingOther ? "fading" : ""}`} ref={listRef}>
        {error && <p className="msg error"><Icon.Alert /> {error}</p>}
        {!bab && !error && <p className="muted center">جارٍ التحميل…</p>}
        {bab?.units.map((u) => {
          const focused = u.key === target.unitKey;
          return (
            <article key={u.key} ref={focused ? focusRef : null} className={`unit-card ${focused ? "focused" : ""}`}>
              <div className="unit-top">
                <span className="unit-number">{u.number}</span>
                {u.section !== bab.bab_title && <span className="unit-section">{u.section}</span>}
              </div>
              <p className="unit-text">
                {focused ? <Highlighted text={u.text} spans={target.spans || []} /> : u.text}
              </p>
              <footer className="unit-foot">{bab.book} — رقم {u.number}</footer>
              {focused && target.spans?.length > 0 && (
                <span className="unit-note"><Icon.Sparkle width={14} height={14} /> موضع الدليل المقتبس</span>
              )}
            </article>
          );
        })}
      </div>

      {bab && (
        <footer className="pager">
          <button className="btn btn-outline" disabled={bab.prev === null}
                  onClick={() => onNavigate({ bookKey: bab.book_key, babIndex: bab.prev })}>
            <Icon.ChevronRight width={16} height={16} /> الباب السابق
          </button>
          <button className="btn btn-outline" disabled={bab.next === null}
                  onClick={() => onNavigate({ bookKey: bab.book_key, babIndex: bab.next })}>
            الباب التالي <Icon.ChevronLeft width={16} height={16} />
          </button>
        </footer>
      )}
    </section>
  );
}
