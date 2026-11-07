import { useEffect, useMemo, useState } from "react";
import { api } from "./api.js";
import { load, save } from "./storage.js";
import Sidebar from "./components/Sidebar.jsx";
import TopBar from "./components/TopBar.jsx";
import ChatPanel from "./components/ChatPanel.jsx";
import ReaderPanel from "./components/ReaderPanel.jsx";
import LibraryView from "./components/LibraryView.jsx";
import SavedView from "./components/SavedView.jsx";

const FALLBACK_MADHAHIB = [{ key: "maliki", label: "مالكي", available: true }];
const uid = () => Math.random().toString(36).slice(2, 10);

export default function App() {
  const [view, setView] = useState("chat");
  const [health, setHealth] = useState(null); // null = loading, false = offline
  const [madhahib, setMadhahib] = useState(FALLBACK_MADHAHIB);
  const [madhhab, setMadhhab] = useState("maliki");
  const [messages, setMessages] = useState(() => load("nour.chat", []));
  const [saved, setSaved] = useState(() => load("nour.saved", []));
  const [loading, setLoading] = useState(false);
  const [reader, setReader] = useState(null); // {bookKey, babIndex, unitKey?, spans?}

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(false));
    api.madhahib().then(setMadhahib).catch(() => {});
  }, []);

  useEffect(() => save("nour.chat", messages.slice(-60)), [messages]);
  useEffect(() => save("nour.saved", saved), [saved]);

  const savedIds = useMemo(() => new Set(saved.map((s) => s.id)), [saved]);

  async function ask(question) {
    setView("chat");
    const now = new Date().toISOString();
    setMessages((m) => [...m, { id: uid(), role: "user", text: question, time: now }]);
    setLoading(true);
    try {
      const result = await api.ask(question, madhhab);
      setMessages((m) => [...m, { id: uid(), role: "assistant", question, result, time: new Date().toISOString() }]);
    } catch (e) {
      setMessages((m) => [...m, { id: uid(), role: "error", text: e.message, time: new Date().toISOString() }]);
    } finally {
      setLoading(false);
    }
  }

  function toggleSave(msg) {
    setSaved((list) => (list.some((s) => s.id === msg.id)
      ? list.filter((s) => s.id !== msg.id)
      : [{ id: msg.id, question: msg.question, result: msg.result, time: msg.time }, ...list]));
  }

  function newChat() {
    setMessages([]);
    setReader(null);
    setView("chat");
  }

  const main = {
    chat: (
      <ChatPanel messages={messages} loading={loading} onAsk={ask}
                 madhahib={madhahib} madhhab={madhhab} onMadhhab={setMadhhab}
                 onOpen={setReader} onSave={toggleSave} savedIds={savedIds} />
    ),
    library: <LibraryView madhhab={madhhab} onOpen={setReader} active={reader} />,
    saved: <SavedView saved={saved} onOpen={setReader} onRemove={(id) => setSaved((l) => l.filter((s) => s.id !== id))} />,
  }[view];

  return (
    <div className="app">
      <Sidebar view={view} onChange={setView} savedCount={saved.length} onNewChat={newChat} />
      <div className="main">
        <TopBar onSearch={ask} health={health} />
        <div className={`content ${reader ? "with-reader" : ""}`}>
          {main}
          {reader && (
            <ReaderPanel target={reader} onClose={() => setReader(null)}
                         onNavigate={(t) => setReader({ ...t, unitKey: null, spans: [] })} />
          )}
        </div>
      </div>
    </div>
  );
}
