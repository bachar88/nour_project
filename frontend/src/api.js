// All calls to the FastAPI backend. In dev, Vite proxies /api → http://localhost:8000.
// In production set VITE_API_URL (e.g. https://nour-api.example.com).
const BASE = import.meta.env.VITE_API_URL || "";

async function request(path, options = {}) {
  let res;
  try {
    res = await fetch(BASE + path, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
  } catch {
    throw new Error("تعذّر الاتصال بالخادم. تأكد من تشغيل الـ backend.");
  }
  if (!res.ok) {
    let detail = "";
    try {
      detail = (await res.json()).detail;
    } catch {
      /* not JSON */
    }
    throw new Error(typeof detail === "string" && detail ? detail : `خطأ من الخادم (${res.status})`);
  }
  return res.json();
}

export const api = {
  health: () => request("/api/health"),
  madhahib: () => request("/api/madhahib"),
  books: (madhhab) => request(`/api/books?madhhab=${encodeURIComponent(madhhab)}`),
  bab: (bookKey, babIndex) => request(`/api/books/${bookKey}/babs/${babIndex}`),
  ask: (question, madhhab) =>
    request("/api/ask", { method: "POST", body: JSON.stringify({ question, madhhab }) }),
};
