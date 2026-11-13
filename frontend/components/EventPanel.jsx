"use client";
import { useCallback, useEffect, useState } from "react";
import { api, euro, fmtDate, fmtTime, rel, SEATING_HE, SOURCE_TYPE_HE, STATUS_CLASS } from "../lib/api";

function Countdown({ target }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  let s = Math.max(0, Math.floor((new Date(target).getTime() - now) / 1000));
  const d = Math.floor(s / 86400); s -= d * 86400;
  const h = Math.floor(s / 3600); s -= h * 3600;
  const m = Math.floor(s / 60); s -= m * 60;
  const p = (n) => String(n).padStart(2, "0");
  return (
    <div className="countdown">
      {d} ימים · <span dir="ltr" style={{ unicodeBidi: "isolate" }}>{p(h)}:{p(m)}:{p(s)}</span>
    </div>
  );
}

function OfferCard({ o, best, onDelete }) {
  return (
    <div className={`offer ${best ? "best" : ""}`}>
      <div className="row between">
        <strong>
          גוש {o.section || "—"} · שורה {o.row || "—"} · מושבים {o.seats || "—"}
          {o.is_demo && <span className="badge demo" style={{ marginInlineStart: 6 }}>דמה</span>}
        </strong>
        <span className="badge ok">ציון {o.score}</span>
      </div>
      <div className="muted">
        {euro(o.price_per_ticket)} לכרטיס · סה"כ {euro(o.total)} · כמות זמינה {o.quantity} · מקור: {o.source}
        {o.basis?.length ? ` · דורג לפי: ${o.basis.join(", ")}` : " · אין מספיק מידע לדירוג"}
      </div>
      {o.warnings?.map((w, i) => <div key={i} className="muted">⚠️ {w}</div>)}
      {o.reasons?.map((w, i) => <div key={i} className="muted">✖ {w}</div>)}
      <div className="row" style={{ marginTop: 6 }}>
        {o.url && <a className="btn" href={o.url} target="_blank" rel="noreferrer">לעמוד ההצעה</a>}
        {o.id && onDelete && <button className="btn" onClick={() => onDelete(o.id)}>הסר</button>}
      </div>
    </div>
  );
}

const EMPTY_OFFER = { section: "", row: "", seats: "", quantity: 4, price_per_ticket: "", fees_included: "true", seated: "true", adjacent: "true", view_score: "", restricted_view: "false", url: "" };
const tri = (v) => (v === "true" ? true : v === "false" ? false : null);

function AddOffer({ ev, onAdded }) {
  const [f, setF] = useState({ ...EMPTY_OFFER, quantity: ev.ticket_count });
  const [err, setErr] = useState("");
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const submit = async (e) => {
    e.preventDefault();
    setErr("");
    try {
      await api(`/events/${ev.id}/offers`, {
        method: "POST",
        body: {
          source: "ידני", url: f.url, section: f.section, row: f.row, seats: f.seats, quantity: Number(f.quantity),
          price_per_ticket: Number(f.price_per_ticket), fees_included: tri(f.fees_included), seated: tri(f.seated),
          adjacent: tri(f.adjacent), restricted_view: tri(f.restricted_view), view_score: f.view_score ? Number(f.view_score) : null,
        },
      });
      setF({ ...EMPTY_OFFER, quantity: ev.ticket_count });
      onAdded();
    } catch (e2) { setErr(e2.message); }
  };
  const TriSel = ({ k }) => (
    <select value={f[k]} onChange={set(k)}><option value="true">כן</option><option value="false">לא</option><option value="">לא ידוע</option></select>
  );
  return (
    <details>
      <summary>הוספת הצעה שראיתי באתר (להשוואה ודירוג)</summary>
      <form onSubmit={submit} className="form" style={{ marginTop: 10 }}>
        <label className="f">גוש<input value={f.section} onChange={set("section")} /></label>
        <label className="f">שורה<input value={f.row} onChange={set("row")} /></label>
        <label className="f">מושבים<input value={f.seats} onChange={set("seats")} placeholder="למשל 11-14" /></label>
        <label className="f">כמות<input type="number" min="1" value={f.quantity} onChange={set("quantity")} /></label>
        <label className="f">מחיר לכרטיס (€)<input type="number" step="0.01" required value={f.price_per_ticket} onChange={set("price_per_ticket")} /></label>
        <label className="f">כולל עמלות?<TriSel k="fees_included" /></label>
        <label className="f">ישיבה?<TriSel k="seated" /></label>
        <label className="f">צמודים?<TriSel k="adjacent" /></label>
        <label className="f">ראות מוגבלת?<TriSel k="restricted_view" /></label>
        <label className="f">ראות לבמה (1–5)<input type="number" min="1" max="5" value={f.view_score} onChange={set("view_score")} /></label>
        <label className="f">קישור<input value={f.url} onChange={set("url")} placeholder="https://" /></label>
        <div className="row" style={{ alignItems: "end" }}><button className="btn primary">הוסף</button></div>
        {err && <div className="note bad">{err}</div>}
      </form>
    </details>
  );
}

function Prefs({ ev, onSaved }) {
  const [f, setF] = useState(ev);
  const [msg, setMsg] = useState("");
  useEffect(() => setF(ev), [ev.id]);
  const set = (k, num) => (e) => setF({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : num ? Number(e.target.value) : e.target.value });
  const save = async (e) => {
    e.preventDefault();
    try {
      await api(`/events/${ev.id}`, {
        method: "PATCH",
        body: {
          ticket_count: f.ticket_count, max_price_per_ticket: f.max_price_per_ticket, max_total: f.max_total,
          seating: f.seating, require_adjacent: f.require_adjacent, allow_split: f.allow_split,
          allow_restricted_view: f.allow_restricted_view, interval_seconds: f.interval_seconds,
        },
      });
      setMsg("נשמר ✓");
      onSaved();
    } catch (e2) { setMsg(e2.message); }
  };
  return (
    <details>
      <summary>העדפות והגדרות ניטור להופעה זו</summary>
      <form onSubmit={save} className="form" style={{ marginTop: 10 }}>
        <label className="f">מספר כרטיסים<input type="number" min="1" max="10" value={f.ticket_count} onChange={set("ticket_count", 1)} /></label>
        <label className="f">מקסימום לכרטיס (€, כולל עמלות)<input type="number" value={f.max_price_per_ticket} onChange={set("max_price_per_ticket", 1)} /></label>
        <label className="f">תקציב להופעה (€)<input type="number" value={f.max_total} onChange={set("max_total", 1)} /></label>
        <label className="f">סוג כרטיס
          <select value={f.seating} onChange={set("seating")}><option value="seated">ישיבה בלבד</option><option value="standing">עמידה</option><option value="any">כל סוג</option></select>
        </label>
        <label className="f">תדירות בדיקה רצויה (שניות)<input type="number" min="10" value={f.interval_seconds} onChange={set("interval_seconds", 1)} /></label>
        <label className="chk"><input type="checkbox" checked={f.require_adjacent} onChange={set("require_adjacent")} />מושבים צמודים</label>
        <label className="chk"><input type="checkbox" checked={f.allow_split} onChange={set("allow_split")} />להציע חלופת 2+2 (לאישור)</label>
        <label className="chk"><input type="checkbox" checked={f.allow_restricted_view} onChange={set("allow_restricted_view")} />לאשר ראות מוגבלת</label>
        <div className="row"><button className="btn primary">שמירה</button><span className="muted">{msg}</span></div>
      </form>
      <p className="muted">התדירות בפועל לא תהיה מהירה ממה שהמקור מתיר (מכסת ה-API / מגבלת אתר). כרגע: כל {ev.effective_interval} שניות.</p>
    </details>
  );
}

export default function EventPanel({ ev, reload }) {
  const [offers, setOffers] = useState(null);
  const [plan, setPlan] = useState(null);
  const [hist, setHist] = useState([]);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");

  const loadDetails = useCallback(async () => {
    try {
      const [o, p, h] = await Promise.all([
        api(`/events/${ev.id}/offers`), api(`/events/${ev.id}/purchase-plan`), api(`/events/${ev.id}/history?limit=15`),
      ]);
      setOffers(o); setPlan(p); setHist(h);
    } catch (e) { setErr(e.message); }
  }, [ev.id]);
  useEffect(() => { loadDetails(); }, [loadDetails, ev.last_check_at]);

  const toggle = async () => {
    setBusy("toggle");
    try { await api(`/events/${ev.id}`, { method: "PATCH", body: { monitoring_enabled: !ev.monitoring_enabled } }); await reload(); }
    catch (e) { setErr(e.message); } finally { setBusy(""); }
  };
  const checkNow = async () => {
    setBusy("check"); setErr("");
    try { await api(`/events/${ev.id}/check`, { method: "POST" }); await reload(); await loadDetails(); }
    catch (e) { setErr(e.message); } finally { setBusy(""); }
  };
  const delOffer = async (id) => { await api(`/offers/${id}`, { method: "DELETE" }); loadDetails(); };

  const year = ev.event_date ? ev.event_date.slice(0, 4) : "";
  const unverified = (ev.sale_dates || []).filter((d) => !d.verified);
  const verified = (ev.sale_dates || []).filter((d) => d.verified);

  return (
    <>
      <div className="card">
        <div className="row between">
          <h2 style={{ margin: 0 }}>{ev.artist} – {ev.city} {year}</h2>
          <div className="row">
            {ev.is_demo && <span className="badge demo">דמה — לא נתונים אמיתיים</span>}
            <span className={`badge ${STATUS_CLASS[ev.status]}`}>{ev.status_he}</span>
          </div>
        </div>
        <div className="muted" style={{ marginTop: 4 }}>
          {ev.venue} · {fmtDate(ev.event_date)}{" "}
          {ev.event_date_verified ? <span className="badge ok">תאריך מאומת</span> : <span className="badge warn">תאריך לא אומת</span>}
        </div>

        <div className="grid" style={{ marginTop: 12 }}>
          <div className="stat"><div className="k">כרטיסים</div><div className="v">{ev.ticket_count} · {SEATING_HE[ev.seating]}</div></div>
          <div className="stat"><div className="k">תקציב (כולל עמלות)</div><div className="v">{euro(ev.max_total)} · עד {euro(ev.max_price_per_ticket)} לכרטיס</div></div>
          <div className="stat"><div className="k">בדיקה אחרונה</div><div className="v">{rel(ev.last_check_at)}</div><div className="k">{fmtTime(ev.last_check_at)}</div></div>
          <div className="stat"><div className="k">בדיקה הבאה</div><div className="v">{ev.monitoring_enabled ? rel(ev.next_check_at) : "ניטור כבוי"}</div><div className="k">כל {ev.effective_interval} שניות</div></div>
        </div>

        <h3>ספירה לאחור למכירה מאומתת</h3>
        {ev.next_verified_sale ? (
          <>
            <Countdown target={ev.next_verified_sale.start_utc} />
            <div className="muted">{ev.next_verified_sale.name} · {fmtTime(ev.next_verified_sale.start_utc)} (שעון ישראל) · מקור: {ev.next_verified_sale.source}</div>
          </>
        ) : <div className="muted">אין מועד מכירה עתידי מאומת.</div>}
        {verified.length > 1 && (
          <ul className="list">{verified.map((d, i) => <li key={i} className="muted">✓ {d.name}: {fmtTime(d.start_utc)} · {d.source}</li>)}</ul>
        )}
        {unverified.length > 0 && (
          <div className="note" style={{ marginTop: 8 }}>
            <strong>מועדים שדווחו אך לא אומתו רשמית</strong> (ללא ספירה לאחור ותזכורות):
            <ul style={{ margin: "4px 0 0", paddingInlineStart: 18 }}>
              {unverified.map((d, i) => <li key={i}>{d.name}: {fmtTime(d.start_utc)} · {d.source}</li>)}
            </ul>
          </div>
        )}

        <div className="row" style={{ marginTop: 14 }}>
          <button className={`btn ${ev.monitoring_enabled ? "danger" : "primary"}`} onClick={toggle} disabled={busy === "toggle"}>
            {ev.monitoring_enabled ? "⏸ עצירת ניטור" : "▶ הפעלת ניטור"}
          </button>
          <button className="btn" onClick={checkNow} disabled={busy === "check"}>{busy === "check" ? "בודק…" : "🔄 בדיקה עכשיו"}</button>
          {ev.official_url && <a className="btn primary" href={ev.official_url} target="_blank" rel="noreferrer">🎟️ לעמוד הרשמי / רכישה</a>}
        </div>
        {err && <div className="note bad" style={{ marginTop: 8 }}>{err}</div>}
        {ev.consecutive_failures > 0 && <div className="note bad" style={{ marginTop: 8 }}>{ev.consecutive_failures} בדיקות רצופות נכשלו — ראה יומן תקלות.</div>}

        <details style={{ marginTop: 12 }}>
          <summary>מקור האימות</summary>
          <p className="muted">{ev.verification_note || "—"}</p>
        </details>
      </div>

      <div className="card">
        <h2>תוצאות חיפוש</h2>
        {!offers ? <div className="muted">טוען…</div> : (
          <>
            {offers.matches.length === 0 && offers.split_options.length === 0 && (
              <div className="muted">אין כרגע הצעות שעומדות בתנאים. Ticketmaster לא מפרסם מלאי מושבים בממשק הציבורי, לכן הצעות מגיעות מהזנה ידנית שלך (או מנתוני דמה במצב בדיקה).</div>
            )}
            {offers.matches.map((o, i) => <OfferCard key={o.id ?? i} o={o} best={i === 0} onDelete={delOffer} />)}
            {offers.split_options.length > 0 && (
              <>
                <h3>חלופות מפוצלות — דורשות אישורך</h3>
                {offers.split_options.map((s, i) => (
                  <div className="offer" key={i}>
                    <strong>{s.label}</strong> · סה"כ {euro(s.total)} · ציון {s.score}
                    <div className="muted">{s.parts.map((p) => `גוש ${p.section} שורה ${p.row} (${euro(p.price_per_ticket)})`).join(" + ")}</div>
                  </div>
                ))}
              </>
            )}
            {offers.needs_approval.length > 0 && (
              <>
                <h3>דורשות אישור (ראות מוגבלת)</h3>
                {offers.needs_approval.map((o, i) => <OfferCard key={o.id ?? i} o={o} onDelete={delOffer} />)}
              </>
            )}
            {offers.excluded.length > 0 && (
              <details><summary>{offers.excluded.length} הצעות נפסלו</summary>
                {offers.excluded.map((o, i) => <OfferCard key={o.id ?? i} o={o} onDelete={delOffer} />)}
              </details>
            )}
            <div className="muted" style={{ margin: "8px 0" }}>תקרת תקציב בפועל להופעה זו: {euro(offers.budget_cap)}</div>
            <AddOffer ev={ev} onAdded={loadDetails} />
          </>
        )}
      </div>

      {plan && (
        <div className="card">
          <h2>מסייע רכישה — מצב ידני מודרך</h2>
          <div className="note info">המערכת לא לוחצת, לא עוקפת תור/CAPTCHA/SMS ולא משלמת. היא מכינה הכול ואתה מבצע ומאשר.</div>
          <ol className="steps">{plan.steps.map((s, i) => <li key={i}>{s}</li>)}</ol>
          <div className="row">{plan.links.map((l, i) => <a key={i} className="btn" href={l.url} target="_blank" rel="noreferrer">{l.label} ↗</a>)}</div>
        </div>
      )}

      <div className="card">
        <h2>מקורות ניטור</h2>
        <div className="tablewrap"><table>
          <thead><tr><th>מקור</th><th>סוג</th><th>סטטוס אחרון</th><th>כשלונות</th><th>מרווח מינימלי</th></tr></thead>
          <tbody>{ev.sources.map((s) => (
            <tr key={s.key}>
              <td>{s.event_url || s.url ? <a href={s.event_url || s.url} target="_blank" rel="noreferrer">{s.label}</a> : s.label}</td>
              <td>{SOURCE_TYPE_HE[s.type] || s.type}{s.enabled === false ? " (כבוי)" : ""}</td>
              <td>{s.last_status || "—"}</td>
              <td>{s.failures}</td>
              <td>{s.min_interval} שנ'</td>
            </tr>
          ))}</tbody>
        </table></div>
        <h3>היסטוריית בדיקות אחרונות</h3>
        <div className="tablewrap"><table>
          <thead><tr><th>זמן</th><th>מקור</th><th>תוצאה</th><th>פירוט</th></tr></thead>
          <tbody>{hist.map((h, i) => (
            <tr key={i}>
              <td>{fmtTime(h.at)}</td><td>{h.source}</td>
              <td>{h.ok ? <span className="badge ok">{h.status}</span> : <span className="badge bad">תקלה</span>}</td>
              <td className="muted">{h.summary}</td>
            </tr>
          ))}{hist.length === 0 && <tr><td colSpan="4" className="muted">עדיין לא בוצעו בדיקות.</td></tr>}</tbody>
        </table></div>
      </div>

      <div className="card"><Prefs ev={ev} onSaved={reload} /></div>
    </>
  );
}
