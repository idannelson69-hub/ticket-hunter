"use client";
import { useCallback, useEffect, useState } from "react";
import EventPanel from "../components/EventPanel";
import { AddEvent, Checklist, Errors, Notifications, Settings } from "../components/Views";
import { api, ApiError, rel } from "../lib/api";

function Login({ onDone }) {
  const [pw, setPw] = useState("");
  const [err, setErr] = useState("");
  const submit = async (e) => {
    e.preventDefault();
    setErr("");
    try { await api("/login", { method: "POST", body: { password: pw } }); onDone(); }
    catch (e2) { setErr(e2.message); }
  };
  return (
    <div className="wrap">
      <form className="card login" onSubmit={submit}>
        <h2>🎟️ צייד כרטיסים</h2>
        <label className="f">סיסמה<input type="password" autoComplete="current-password" value={pw} onChange={(e) => setPw(e.target.value)} autoFocus /></label>
        <div style={{ marginTop: 12 }}><button className="btn primary">כניסה</button></div>
        {err && <div className="note bad" style={{ marginTop: 10 }}>{err}</div>}
      </form>
    </div>
  );
}

const FIXED_TABS = [
  ["notifications", "🔔 התראות"],
  ["errors", "⚠️ תקלות"],
  ["checklist", "✅ הכנה"],
  ["settings", "⚙️ הגדרות"],
  ["add", "➕ הופעה"],
];

export default function Home() {
  const [authed, setAuthed] = useState(null);
  const [events, setEvents] = useState([]);
  const [tab, setTab] = useState(null);
  const [health, setHealth] = useState(null);

  const load = useCallback(async () => {
    try {
      const evs = await api("/events");
      setEvents(evs);
      setAuthed(true);
      setTab((t) => t ?? (evs[0] ? `ev-${evs[0].id}` : "settings"));
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) setAuthed(false);
    }
    api("/health").then(setHealth).catch(() => setHealth(null));
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, [load]);

  if (authed === null) return <div className="wrap muted">טוען…</div>;
  if (!authed) return <Login onDone={load} />;

  const logout = async () => { await api("/logout", { method: "POST" }); setAuthed(false); };
  const current = tab?.startsWith("ev-") ? events.find((e) => `ev-${e.id}` === tab) : null;
  const ok = health?.ok && health?.scheduler_running;

  return (
    <div className="wrap">
      <header className="top">
        <h1>🎟️ צייד כרטיסים</h1>
        <div className="row">
          <span className="health"><span className={`dot ${ok ? "ok" : "bad"}`} />{ok ? `המנוע פעיל · דופק ${rel(health.last_tick)}` : "המנוע לא פעיל"}</span>
          {health?.login_required !== false && <button className="btn" onClick={logout}>יציאה</button>}
        </div>
      </header>
      <nav className="tabs">
        {events.map((e) => (
          <button key={e.id} className={tab === `ev-${e.id}` ? "active" : ""} onClick={() => setTab(`ev-${e.id}`)}>
            {e.artist} – {e.city} {e.event_date?.slice(0, 4)}
          </button>
        ))}
        {FIXED_TABS.map(([k, label]) => (
          <button key={k} className={tab === k ? "active" : ""} onClick={() => setTab(k)}>{label}</button>
        ))}
      </nav>
      {current && <EventPanel key={current.id} ev={current} reload={load} />}
      {tab === "notifications" && <Notifications />}
      {tab === "errors" && <Errors />}
      {tab === "checklist" && <Checklist />}
      {tab === "settings" && <Settings onPurged={load} />}
      {tab === "add" && <AddEvent onCreated={async (ev) => { await load(); setTab(`ev-${ev.id}`); }} />}
    </div>
  );
}
