import { useEffect, useState } from "react";
import { api } from "../api.js";
import { Icon } from "./Icons.jsx";
import { BOOK_STYLE } from "../highlight.jsx";

export default function LibraryView({ madhhab, onOpen, active }) {
  const [books, setBooks] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.books(madhhab).then(setBooks).catch((e) => setError(e.message));
  }, [madhhab]);

  return (
    <section className="panel library">
      <h2 className="panel-title"><Icon.Library /> مكتبتي</h2>
      {error && <p className="msg error"><Icon.Alert /> {error}</p>}
      {!books && !error && <p className="muted center">جارٍ التحميل…</p>}
      <div className="books">
        {books?.map((b) => (
          <div key={b.key} className="book">
            <div className="book-head">
              <span className={`tag ${BOOK_STYLE[b.key] || "tag-maroon"}`}>{b.title}</span>
              <small>{b.author}</small>
            </div>
            <ul>
              {b.babs.map((bab) => {
                const isActive = active?.bookKey === b.key && active?.babIndex === bab.index;
                return (
                  <li key={bab.index}>
                    <button className={`bab-link ${isActive ? "active" : ""}`}
                            onClick={() => onOpen({ bookKey: b.key, babIndex: bab.index })}>
                      <span>{bab.title}</span>
                      <small>{bab.units}</small>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </div>
    </section>
  );
}
