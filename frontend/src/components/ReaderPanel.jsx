import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { Icon } from "./Icons.jsx";
import { Highlighted } from "../highlight.jsx";

// Shows a whole bab as numbered cards; the cited unit is highlighted and scrolled into view.
// Pick mode (`picking`): the user selects the correct sentence in one card and confirms it.
export default function ReaderPanel({ target, onClose, onNavigate, picking = false, onPicked, onCancelPick }) {
  const [bab, setBab] = useState(null);
  const [error, setError] = useState("");
  const [pickError, setPickError] = useState("");

  // Remember the last selection made inside a unit's text: on phones, tapping the button can clear it.
  const lastSel = useRef(null);
  useEffect(() => {
    if (!picking) return;
    const card = (node) => (node?.nodeType === 1 ? node : node?.parentElement)?.closest?.("[data-unit-key]");
    const onChange = () => {
      const sel = window.getSelection();
      const quote = sel ? sel.toString().replace(/\s+/g, " ").trim() : "";
      if (!quote) return;
      const a = card(sel.anchorNode), b = card(sel.focusNode);
      lastSel.current = { quote, unitKey: a && a === b ? a.dataset.unitKey : null };
    };
    document.addEventListener("selectionchange", onChange);
    return () => document.removeEventListener("selectionchange", onChange);
  }, [picking]);

  function confirmPick() {
    const s = lastSel.current;
    if (!s || s.quote.split(" ").length < 3) return setPickError("حدّد جملة كاملة (ثلاث كلمات على الأقل).");
    if (!s.unitKey) return setPickError("حدّد الجملة داخل مقطع واحد.");
    if (s.quote.length > 800) return setPickError("التحديد طويل جدًا: اكتفِ بالجملة التي تجيب عن السؤال.");
    setPickError("");
    window.getSelection()?.removeAllRanges();
    lastSel.current = null;
    onPicked({ unitKey: s.unitKey, quote: s.quote });
  }
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

      {picking && (
        <div className="pick-banner" role="status">
          <p><Icon.Cursor width={16} height={16} /> حدّد بالفأرة (أو بإصبعك) الجملة التي تجيب عن السؤال، ثم اضغط «اعتمد هذه الجملة».</p>
          {pickError && <p className="pick-error">{pickError}</p>}
          <div className="pick-actions">
            <button className="btn btn-primary" onClick={confirmPick}>اعتمد هذه الجملة</button>
            <button className="btn btn-ghost" onClick={onCancelPick}>إلغاء</button>
          </div>
        </div>
      )}

      <div className={`reader-list ${loadingOther ? "fading" : ""} ${picking ? "picking" : ""}`} ref={listRef}>
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
              <p className="unit-text" data-unit-key={u.key}>
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
