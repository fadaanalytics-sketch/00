// All URLs are relative: the page is served through Colab's port proxy, so never
// assume the app lives at the origin root.

export async function api(path, { method = 'GET', body } = {}) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(path, opts);
  } catch {
    throw new Error('تعذر الاتصال بالسيرفر — تأكد إن نوت بوك كولاب لسه شغال');
  }
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = null; }
  if (!res.ok) {
    const d = data?.detail;
    const msg = typeof d === 'string' ? d : Array.isArray(d) ? d.map(x => x.msg).join('، ') : `خطأ ${res.status}`;
    throw new Error(msg);
  }
  return data;
}

export const TERMINAL = ['done', 'error', 'cancelled'];

/** Poll a job until it finishes. Tolerates brief network blips (the Colab proxy
 * occasionally drops a request) before reporting the connection as lost. */
export function pollJob(jobId, onUpdate, interval = 1000) {
  let stopped = false;
  let failures = 0;
  const tick = async () => {
    if (stopped) return;
    try {
      const job = await api(`api/jobs/${jobId}`);
      failures = 0;
      onUpdate(job);
      if (TERMINAL.includes(job.status)) return;
    } catch (e) {
      failures += 1;
      if (failures >= 6) {
        onUpdate({ id: jobId, status: 'error', progress: 0, message: 'انقطع الاتصال', error: e.message });
        return;
      }
    }
    setTimeout(tick, interval);
  };
  tick();
  return () => { stopped = true; };
}
