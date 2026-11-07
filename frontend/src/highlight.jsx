// Render `text` with <mark> around the [start, end) character spans returned by the backend.
export function Highlighted({ text, spans = [] }) {
  if (!spans.length) return text;
  const sorted = [...spans].sort((a, b) => a[0] - b[0]);
  const parts = [];
  let cursor = 0;
  sorted.forEach(([s, e], i) => {
    if (s < cursor) return; // overlapping span: skip
    if (s > cursor) parts.push(text.slice(cursor, s));
    parts.push(<mark key={i}>{text.slice(s, e)}</mark>);
    cursor = e;
  });
  parts.push(text.slice(cursor));
  return parts;
}

export const BOOK_STYLE = {
  risala: "tag-maroon",
  akhdari: "tag-gold",
};
