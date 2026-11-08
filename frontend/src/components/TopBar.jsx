import { useState } from "react";
import { Icon } from "./Icons.jsx";

export default function TopBar({ onSearch, health }) {
  const [q, setQ] = useState("");

  function submit(e) {
    e.preventDefault();
    if (q.trim().length < 2) return;
    onSearch(q.trim());
    setQ("");
  }

  return (
    <header className="topbar">
      <form className="search" onSubmit={submit} role="search">
        <Icon.Search />
        <input value={q} onChange={(e) => setQ(e.target.value)}
               placeholder="ابحث في مسائل الصلاة في الرسالة ومختصر الأخضري..." aria-label="بحث" />
      </form>
      <div className="status">
        {health === null && <span className="pill muted">جارٍ الاتصال…</span>}
        {health === false && <span className="pill danger">الخادم غير متصل</span>}
        {health?.demo && <span className="pill warn" title="نماذج تجريبية: الأجوبة ليست حقيقية">وضع تجريبي</span>}
        {health?.preview && (
          <span className="pill warn" title="البحث بالكلمات المفتاحية بدل BGE-M3، والإجابة من Claude بدل gpt-oss-120b">
            معاينة · بحث بالكلمات + Claude
          </span>
        )}
        {health?.status === "misconfigured" && (
          <span className="pill danger" title={`متغيرات ناقصة: ${(health.missing || []).join(", ")}`}>
            إعداد الخادم ناقص
          </span>
        )}
        {health && !health.demo && !health.preview && health.status === "ok" && (
          <span className="pill ok">متصل · {health.llm.replace(/^openai\//, "")}</span>
        )}
      </div>
    </header>
  );
}
