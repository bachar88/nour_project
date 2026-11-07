// Inline SVG icons (no icon library needed). All use currentColor.
const base = { width: 20, height: 20, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor",
  strokeWidth: 1.8, strokeLinecap: "round", strokeLinejoin: "round", "aria-hidden": true };

export const Icon = {
  Lantern: (p) => (
    <svg {...base} viewBox="0 0 48 48" strokeWidth={2.2} {...p}>
      <path d="M24 3l4 5h-8z" />
      <path d="M18 8h12M16 13h16l3 5v15c0 4-5 9-11 9s-11-5-11-9V18z" />
      <path d="M16 18h16M14 33h20" />
      <path d="M24 21c2.5 2.5 3.4 5 0 9-3.4-4-2.5-6.5 0-9z" fill="currentColor" stroke="none" />
    </svg>
  ),
  Chat: (p) => (<svg {...base} {...p}><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1.1-4.4A8 8 0 1 1 21 12z" /><path d="M8.5 11h7M8.5 14h4" /></svg>),
  Library: (p) => (<svg {...base} {...p}><path d="M4 19V5a1 1 0 0 1 1-1h3v16H5a1 1 0 0 1-1-1z" /><path d="M8 4h4v16H8z" /><path d="M14.5 5.2l3-.8 3.2 14.7-3 .8z" /></svg>),
  Bookmark: (p) => (<svg {...base} {...p}><path d="M6 4h12v17l-6-4-6 4z" /></svg>),
  BookmarkFilled: (p) => (<svg {...base} {...p}><path d="M6 4h12v17l-6-4-6 4z" fill="currentColor" /></svg>),
  Search: (p) => (<svg {...base} {...p}><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" /></svg>),
  Send: (p) => (<svg {...base} {...p}><path d="M20 4L3 11l7 2 2 7z" /><path d="M10 13l10-9" /></svg>),
  BookOpen: (p) => (<svg {...base} {...p}><path d="M12 7c-2-1.6-4.7-2-8-2v13c3.3 0 6 .4 8 2 2-1.6 4.7-2 8-2V5c-3.3 0-6 .4-8 2z" /><path d="M12 7v13" /></svg>),
  ArrowBack: (p) => (<svg {...base} {...p}><path d="M5 12h14M13 6l6 6-6 6" /></svg>),
  ChevronLeft: (p) => (<svg {...base} {...p}><path d="M15 6l-6 6 6 6" /></svg>),
  ChevronRight: (p) => (<svg {...base} {...p}><path d="M9 6l6 6-6 6" /></svg>),
  ChevronDown: (p) => (<svg {...base} {...p}><path d="M6 9l6 6 6-6" /></svg>),
  Check: (p) => (<svg {...base} {...p}><path d="M5 12.5l4.5 4.5L19 7.5" /></svg>),
  Alert: (p) => (<svg {...base} {...p}><path d="M12 3l9.5 17h-19z" /><path d="M12 10v4.5M12 17.5v.2" /></svg>),
  Plus: (p) => (<svg {...base} {...p}><path d="M12 5v14M5 12h14" /></svg>),
  User: (p) => (<svg {...base} {...p}><circle cx="12" cy="8.5" r="3.5" /><path d="M5 20c1.2-3.6 4-5.5 7-5.5s5.8 1.9 7 5.5" /></svg>),
  Copy: (p) => (<svg {...base} {...p}><rect x="8" y="8" width="12" height="12" rx="2" /><path d="M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3" /></svg>),
  Trash: (p) => (<svg {...base} {...p}><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13" /></svg>),
  Close: (p) => (<svg {...base} {...p}><path d="M6 6l12 12M18 6L6 18" /></svg>),
  Sparkle: (p) => (<svg {...base} {...p}><path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z" /></svg>),
};
