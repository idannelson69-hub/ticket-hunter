"use client";
import { useEffect, useState } from "react";
import { api, euro, fmtTime, KIND_HE } from "../lib/api";

export function Notifications() {
  const [rows, setRows] = useState(null);
  useEffect(() => { api("/notifications").then(setRows).catch(() => setRows([])); }, []);
  return (
    <div className="card">
      <h2>היסטוריית התראות</h2>
      {!rows ? <div className="muted">טוען…</div> : rows.length === 0 ? <div className="muted">אין התראות עדיין.</div> : (
        <ul className="list">{rows.map((n) => (
          <li key={n.id}>
            <div className="row between">
              <div className="row">
                <span className="badge">{KIND_HE[n.kind] || n.kind}</span>
                {n.is_demo && <span className="badge demo">דמה</span>}
                {n.sent ? <span className="badge ok">נשלח{n.channels_sent?.length ? `: ${n.channels_sent.join(" + ")}` : ""}</span>
                  : n.channels_sent?.length ? <span className="badge warn">נשלח חלקית: {n.channels_sent.join(" + ")}</span>
                  : <span className="badge bad">לא נשלח</span>}
              </div>
              <span className="muted">{fmtTime(n.at)}</span>
            </div>
            {n.error && <div className="muted">⚠️ {n.error}</div>}
            <div className="msg">{n.text}</div>
          </li>
        ))}</ul>
      )}
    </div>
  );
}

export function Errors() {
  const [rows, setRows] = useState(null);
  useEffect(() => { api("/errors").then(setRows).catch(() => setRows([])); }, []);
  return (
    <div className="card">
      <h2>יומן תקלות</h2>
      {!rows ? <div className="muted">טוען…</div> : rows.length === 0 ? <div className="muted">אין תקלות. 👍</div> : (
        <div className="tablewrap"><table>
          <thead><tr><th>זמן</th><th>מקור</th><th>הודעה</th></tr></thead>
          <tbody>{rows.map((e) => <tr key={e.id}><td>{fmtTime(e.at)}</td><td>{e.source || "—"}</td><td>{e.message}</td></tr>)}</tbody>
        </table></div>
      )}
    </div>
  );
}

export function Checklist() {
  const [items, setItems] = useState(null);
  useEffect(() => { api("/checklist").then((d) => setItems(d.items)); }, []);
  const toggle = async (i) => {
    const next = items.map((it, j) => (j === i ? { ...it, done: !it.done } : it));
    setItems(next);
    await api("/checklist", { method: "PUT", body: { items: next } });
  };
  if (!items) return <div className="card muted">טוען…</div>;
  const done = items.filter((i) => i.done).length;
  return (
    <div className="card">
      <h2>הכנה לרכישה ({done}/{items.length})</h2>
      <ul className="list">{items.map((it, i) => (
        <li key={it.id}><label className="chk"><input type="checkbox" checked={it.done} onChange={() => toggle(i)} />{it.text}</label></li>
      ))}</ul>
      <p className="muted">תזכורות נשלחות לטלגרם 24 שעות, שעה ו-15 דקות לפני כל פתיחת מכירה מאומתת.</p>
    </div>
  );
}

export function Settings({ onPurged }) {
  const [s, setS] = useState(null);
  const [budget, setBudget] = useState("");
  const [msg, setMsg] = useState("");
  const [chats, setChats] = useState(null);
  const load = () => api("/settings").then((d) => { setS(d); setBudget(d.global_budget ?? ""); });
  useEffect(() => { load(); }, []);
  if (!s) return <div className="card muted">טוען…</div>;

  const saveBudget = async () => { try { await api("/settings", { method: "PUT", body: { global_budget: Number(budget) } }); setMsg("נשמר ✓"); load(); } catch (e) { setMsg(e.message); } };
  const test = async () => { setMsg("שולח…"); try { const r = await api("/telegram/test", { method: "POST" }); setMsg(r.sent ? `✓ נשלח ל: ${r.channels_sent.join(", ")} — בדוק בטלפון ובמייל` : `נשלח ל: ${r.channels_sent.join(", ") || "אף ערוץ"} · שגיאה: ${r.error}`); } catch (e) { setMsg(e.message); } };
  const discover = async () => { try { setChats((await api("/telegram/discover")).chats); } catch (e) { setMsg(e.message); } };
  const purge = async (scope) => {
    const q = scope === "all" ? "למחוק את כל הנתונים כולל ההופעות וההגדרות? לא ניתן לשחזר." : "למחוק היסטוריית בדיקות, התראות, תקלות והצעות? לא ניתן לשחזר.";
    if (!window.confirm(q)) return;
    await api("/data/purge", { method: "POST", body: { scope } });
    setMsg("הנתונים נמחקו"); onPurged?.();
  };
  const b = s.budget;
  return (
    <>
      <div className="card">
        <h2>תקציב כולל</h2>
        <div className="row">
          <input style={{ maxWidth: 140 }} type="number" value={budget} onChange={(e) => setBudget(e.target.value)} />
          <span>€</span><button className="btn primary" onClick={saveBudget}>שמירה</button>
        </div>
        <p className={b.ok ? "muted" : "note bad"}>
          מוקצה להופעות פעילות: {euro(b.allocated)} מתוך {euro(b.global_budget)} {b.ok ? "✓" : "— חריגה! הקטן תקציב של הופעה או הגדל את הכולל"}
        </p>
      </div>
      <div className="card">
        <h2>ערוצי התראה</h2>
        <ul className="list">
          {(s.channels || []).map((c) => (
            <li key={c.name} className="row between">
              <strong>{c.name === "Telegram" ? "📱 Telegram (טלפון)" : c.name === "מייל" ? `📧 מייל${s.email_to ? ` → ${s.email_to}` : ""}` : c.name}</strong>
              {c.configured ? <span className="badge ok">מחובר</span> : <span className="badge bad">לא מחובר</span>}
            </li>
          ))}
        </ul>
        <p className="muted">הפרטים (טוקן, סיסמת אפליקציה) נקבעים בקובץ ‎.env בשרת בלבד ולא נשמרים בממשק.</p>
        <div className="row">
          <button className="btn primary" onClick={test} disabled={!(s.channels || []).some((c) => c.configured)}>שליחת התראת בדיקה לכל הערוצים</button>
          <button className="btn" onClick={discover} disabled={!s.telegram_token_set}>איתור מזהה הצ'אט שלי</button>
        </div>
        {chats && <div className="msg">{chats.length ? chats.map((c) => `${c.name}: ${c.chat_id}`).join("\n") : "לא נמצאו הודעות. שלח לבוט הודעה כלשהי בטלגרם ונסה שוב."}</div>}
      </div>
      <div className="card">
        <h2>מקורות</h2>
        <p>Ticketmaster Discovery API: {s.ticketmaster_configured ? <span className="badge ok">מפתח מוגדר</span> : <span className="badge bad">חסר מפתח</span>}
          <span className="muted"> · מכסה יומית {s.ticketmaster_daily_quota} קריאות</span></p>
        <p className="muted">מעקב עמודי אינטרנט: לכל היותר פעם ב-{s.min_page_watch_seconds} שניות, בכפוף ל-robots.txt.</p>
        {s.demo_mode && <p className="note">מצב דמה פעיל — קיים אירוע דמה מסומן לבדיקת המערכת.</p>}
      </div>
      <div className="card">
        <h2>מחיקת נתונים</h2>
        <div className="row">
          <button className="btn danger" onClick={() => purge("history")}>מחיקת היסטוריה</button>
          <button className="btn danger" onClick={() => purge("all")}>מחיקת הכול</button>
        </div>
      </div>
      {msg && <div className="note info">{msg}</div>}
    </>
  );
}

export function AddEvent({ onCreated }) {
  const [f, setF] = useState({ artist: "", city: "", venue: "", event_date: "", official_url: "", ticket_count: 2, max_price_per_ticket: 150, max_total: 300, seating: "any", tm_keyword: "", page_url: "" });
  const [err, setErr] = useState("");
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const submit = async (e) => {
    e.preventDefault(); setErr("");
    const sources = [];
    if (f.tm_keyword) sources.push({ type: "ticketmaster_api", label: "Ticketmaster API", keyword: f.tm_keyword, venue_hint: f.venue || null });
    if (f.page_url) sources.push({ type: "page_watch", label: "עמוד רשמי", url: f.page_url });
    try {
      const ev = await api("/events", {
        method: "POST",
        body: { artist: f.artist, city: f.city, venue: f.venue, event_date: f.event_date || null, official_url: f.official_url,
          ticket_count: Number(f.ticket_count), max_price_per_ticket: Number(f.max_price_per_ticket), max_total: Number(f.max_total),
          seating: f.seating, sources, event_date_verified: false, verification_note: "נוסף ידנית — יש לאמת מול מקור רשמי" },
      });
      onCreated(ev);
    } catch (e2) { setErr(e2.message); }
  };
  return (
    <div className="card">
      <h2>הוספת הופעה</h2>
      <form onSubmit={submit} className="form">
        <label className="f">אמן<input required value={f.artist} onChange={set("artist")} /></label>
        <label className="f">עיר<input required value={f.city} onChange={set("city")} /></label>
        <label className="f">מקום<input value={f.venue} onChange={set("venue")} /></label>
        <label className="f">תאריך<input type="date" value={f.event_date} onChange={set("event_date")} /></label>
        <label className="f">קישור רשמי<input value={f.official_url} onChange={set("official_url")} placeholder="https://" /></label>
        <label className="f">כרטיסים<input type="number" min="1" value={f.ticket_count} onChange={set("ticket_count")} /></label>
        <label className="f">מקס' לכרטיס (€)<input type="number" value={f.max_price_per_ticket} onChange={set("max_price_per_ticket")} /></label>
        <label className="f">תקציב (€)<input type="number" value={f.max_total} onChange={set("max_total")} /></label>
        <label className="f">סוג<select value={f.seating} onChange={set("seating")}><option value="any">כל סוג</option><option value="seated">ישיבה</option><option value="standing">עמידה</option></select></label>
        <label className="f">מילת חיפוש ב-Ticketmaster<input value={f.tm_keyword} onChange={set("tm_keyword")} placeholder="שם האמן" /></label>
        <label className="f">עמוד רשמי למעקב<input value={f.page_url} onChange={set("page_url")} placeholder="https://" /></label>
        <div className="row" style={{ alignItems: "end" }}><button className="btn primary">הוספה</button></div>
      </form>
      {err && <div className="note bad" style={{ marginTop: 8 }}>{err}</div>}
      <p className="muted">הופעה חדשה נשמרת כ"לא מאומתת" עד שתאמת את הפרטים מול האתר הרשמי.</p>
    </div>
  );
}
