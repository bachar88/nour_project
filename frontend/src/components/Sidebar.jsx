import { Icon } from "./Icons.jsx";

const NAV = [
  { key: "chat", label: "اسأل نور", icon: Icon.Chat },
  { key: "library", label: "مكتبتي", icon: Icon.Library },
  { key: "saved", label: "حفظي", icon: Icon.Bookmark },
];

export default function Sidebar({ view, onChange, savedCount, onNewChat }) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <Icon.Lantern className="brand-icon" width={46} height={46} />
        <span className="brand-name">نـور</span>
      </div>

      <nav className="nav">
        {NAV.map(({ key, label, icon: I }) => (
          <button key={key} className={`nav-item ${view === key ? "active" : ""}`}
                  onClick={() => onChange(key)} aria-current={view === key ? "page" : undefined}>
            <I />
            <span>{label}</span>
            {key === "saved" && savedCount > 0 && <span className="nav-count">{savedCount}</span>}
          </button>
        ))}
      </nav>

      <button className="new-chat" onClick={onNewChat}>
        <Icon.Plus width={18} height={18} />
        <span>محادثة جديدة</span>
      </button>

      <div className="sidebar-footer">
        <div className="avatar"><Icon.User /></div>
        <div className="footer-text">
          <span>المذهب المالكي</span>
          <small>كتاب الصلاة</small>
        </div>
      </div>
    </aside>
  );
}
