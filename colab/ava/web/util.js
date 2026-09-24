export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

export function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

export function fmtTime(sec, decimals = 1) {
  if (!Number.isFinite(sec)) return '';
  const f = 10 ** decimals;
  const total = Math.round(Math.max(0, sec) * f) / f;
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = (total - h * 3600 - m * 60).toFixed(decimals).padStart(decimals ? 3 + decimals : 2, '0');
  return h ? `${h}:${String(m).padStart(2, '0')}:${s}` : `${m}:${s}`;
}

/** Accepts "83.4", "1:23.4", "1:02:03", Arabic-Indic digits and "٫" as the decimal mark. */
export function parseTime(input) {
  const str = String(input ?? '').trim()
    .replace(/[٠-٩]/g, d => String('٠١٢٣٤٥٦٧٨٩'.indexOf(d)))
    .replace(/[٫,]/g, '.');
  if (!str) return NaN;
  const parts = str.split(':');
  if (parts.length > 3 || parts.some(p => p === '' || Number.isNaN(Number(p)) || Number(p) < 0)) return NaN;
  return parts.reduce((acc, p) => acc * 60 + Number(p), 0);
}

export function fmtBytes(n) {
  if (!n) return '';
  const units = ['B', 'KB', 'MB', 'GB'];
  let i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(i ? 1 : 0)} ${units[i]}`;
}

export function fmtDate(iso) {
  try {
    return new Date(iso).toLocaleString('ar-EG', { dateStyle: 'medium', timeStyle: 'short' });
  } catch { return iso; }
}

export function debounce(fn, ms) {
  let t;
  const wrapped = (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
  wrapped.flush = () => { clearTimeout(t); return fn(); };
  return wrapped;
}

export function toast(message, type = 'info', ms) {
  const root = $('#toast-root');
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = message.length > 300 ? `${message.slice(0, 300)}…` : message;
  root.appendChild(el);
  const life = ms ?? (type === 'error' ? 7000 : 3500);
  setTimeout(() => el.classList.add('hide'), life);
  setTimeout(() => el.remove(), life + 400);
}

export function modal({ title, body, footer = '', size = '' }) {
  const root = $('#modal-root');
  const wrap = document.createElement('div');
  wrap.className = 'modal-backdrop';
  wrap.innerHTML = `
    <div class="modal ${size}" role="dialog" aria-modal="true">
      <div class="modal-head"><h3>${esc(title)}</h3><button class="btn ghost icon" data-close aria-label="إغلاق">✕</button></div>
      <div class="modal-body">${body}</div>
      ${footer ? `<div class="modal-foot">${footer}</div>` : ''}
    </div>`;
  const close = () => { wrap.remove(); document.removeEventListener('keydown', onKey); };
  const onKey = e => { if (e.key === 'Escape') close(); };
  wrap.addEventListener('mousedown', e => { if (e.target === wrap) close(); });
  wrap.querySelector('[data-close]').addEventListener('click', close);
  document.addEventListener('keydown', onKey);
  root.appendChild(wrap);
  return { el: wrap, close };
}

export function confirmDialog(title, message, { okText = 'تأكيد', danger = false } = {}) {
  return new Promise(resolve => {
    const m = modal({
      title, size: 'sm',
      body: `<p>${esc(message)}</p>`,
      footer: `<button class="btn" data-no>إلغاء</button><button class="btn ${danger ? 'danger' : 'primary'}" data-yes>${esc(okText)}</button>`,
    });
    const done = v => { m.close(); resolve(v); };
    m.el.querySelector('[data-yes]').addEventListener('click', () => done(true));
    m.el.querySelector('[data-no]').addEventListener('click', () => done(false));
    m.el.querySelector('[data-close]').addEventListener('click', () => resolve(false));
  });
}

export function downloadText(filename, text) {
  const url = URL.createObjectURL(new Blob([text], { type: 'text/plain;charset=utf-8' }));
  const a = Object.assign(document.createElement('a'), { href: url, download: filename });
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function readFileAsDataURL(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(r.result);
    r.onerror = () => reject(new Error('تعذر قراءة الملف'));
    r.readAsDataURL(file);
  });
}
