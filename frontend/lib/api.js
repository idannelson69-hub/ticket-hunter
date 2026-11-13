export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

export async function api(path, { method = "GET", body } = {}) {
  const res = await fetch(`/api${path}`, {
    method,
    credentials: "same-origin",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  let data = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  if (!res.ok) {
    const detail = data?.detail;
    const msg = typeof detail === "string" ? detail : Array.isArray(detail) ? "נתונים לא תקינים בטופס" : `שגיאה ${res.status}`;
    throw new ApiError(res.status, msg);
  }
  return data;
}

const TZ = "Asia/Jerusalem";
export function fmtTime(iso) {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("he-IL", {
    timeZone: TZ, day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit",
  }).format(new Date(iso));
}
export function fmtDate(d) {
  if (!d) return "לא ידוע";
  const [y, m, day] = d.split("-");
  return `${day}.${m}.${y}`;
}
export function rel(iso, now = Date.now()) {
  if (!iso) return "—";
  const s = Math.round((new Date(iso).getTime() - now) / 1000);
  const a = Math.abs(s);
  if (a < 5) return "עכשיו";
  const txt = a < 60 ? `${a} שניות` : a < 3600 ? `${Math.round(a / 60)} דקות` : a < 86400 ? `${Math.round(a / 3600)} שעות` : `${Math.round(a / 86400)} ימים`;
  return s >= 0 ? `בעוד ${txt}` : `לפני ${txt}`;
}
export function euro(n) {
  return n == null ? "—" : `${Number(n).toFixed(n % 1 ? 2 : 0)}€`;
}

export const STATUS_CLASS = {
  NOT_ANNOUNCED: "", ANNOUNCED: "", PRESALE: "warn", ON_SALE: "ok", AVAILABLE: "ok", SOLD_OUT: "bad", UNKNOWN: "warn",
};
export const KIND_HE = {
  announced: "הופעה פורסמה", sale_date: "מועד מכירה", presale: "מכירה מוקדמת", on_sale: "מכירה נפתחה",
  match: "כרטיסים מתאימים", restock: "חזרת מלאי", sold_out: "אזל", manual: "פעולה ידנית", critical: "תקלה קריטית",
  reminder: "תזכורת", test: "בדיקה",
};
export const SEATING_HE = { seated: "ישיבה בלבד", standing: "עמידה", any: "כל סוג" };
export const SOURCE_TYPE_HE = { ticketmaster_api: "Ticketmaster API (רשמי)", page_watch: "מעקב עמוד", demo: "דמה" };
