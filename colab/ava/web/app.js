import { api, pollJob, TERMINAL } from './api.js';
import {
  $, $$, esc, fmtTime, parseTime, fmtBytes, fmtDate, debounce, toast, modal, confirmDialog, downloadText,
} from './util.js';
import { renderTemplatesView, templateAssetUrl } from './template-editor.js';
import { drawTemplateThumb, renderOverlays } from './template-render.js';

const STAGE_LABELS = { new: 'جديد', transcribed: 'تم التفريغ', analyzed: 'تم التحليل', exported: 'تم التصدير' };
const MODE_LABELS = { social_clips: 'مقاطع قصيرة للسوشيال ميديا', lecture_sections: 'تقسيم المحاضرات الطويلة' };
const DONE_MESSAGES = {
  transcribe: 'اكتمل التفريغ الصوتي ✓',
  analyze: 'اكتمل التحليل واقتراح المقاطع ✓',
  preview: 'المعاينة جاهزة ✓',
  export: 'تم التصدير وحفظ الملفات على الدرايف ✓',
};

const state = {
  status: null, settings: null, projects: [], templates: [],
  project: null, view: 'projects', tab: 'transcript',
  jobs: {}, playUntil: null, dirty: false,
  exportTemplateId: storageGet('ava:exportTemplate') || '',
};
const pollers = {};
const app = { state, reloadTemplates };

function storageGet(key) { try { return localStorage.getItem(key); } catch { return null; } }
function storageSet(key, value) { try { localStorage.setItem(key, value); } catch { /* private mode */ } }

// ============================================================ bootstrap

async function init() {
  $('#nav-projects').addEventListener('click', () => setView('projects'));
  $('#nav-templates').addEventListener('click', () => setView('templates'));
  $('#nav-settings').addEventListener('click', openSettings);
  $('#btn-new-project').addEventListener('click', openDriveBrowser);
  window.addEventListener('beforeunload', e => { if (state.dirty) { e.preventDefault(); e.returnValue = ''; } });
  try {
    [state.status, state.settings, state.projects, state.templates] = await Promise.all([
      api('api/status'), api('api/settings'), api('api/projects'), api('api/templates'),
    ]);
  } catch (e) {
    $('#main').innerHTML = `<div class="card empty"><div class="big">⚠️</div><h2>تعذر الاتصال بالسيرفر</h2><p>${esc(e.message)}</p></div>`;
    return;
  }
  renderChips();
  renderSidebar();
  const last = storageGet('ava:lastProject');
  if (last && state.projects.some(p => p.id === last)) await selectProject(last);
  else setView('projects');
}

async function reloadTemplates() {
  state.templates = await api('api/templates');
}

function renderChips() {
  const s = state.status;
  const chips = [
    s.cuda
      ? `<span class="chip ok" title="التفريغ بـ Whisper على كارت الشاشة">⚡ ${esc(s.gpu || 'GPU')}</span>`
      : '<span class="chip warn" title="من كولاب: Runtime ‹ Change runtime type ‹ T4 GPU">⚠ بدون GPU</span>',
    s.nvenc
      ? '<span class="chip ok" title="التصدير على كارت الشاشة (NVENC)">🎞 تصدير بكارت الشاشة</span>'
      : '<span class="chip" title="التصدير على المعالج">🎞 تصدير بالمعالج</span>',
    s.gemini_key ? '<span class="chip ok">Gemini ✓</span>' : '<span class="chip bad" title="أضف GEMINI_API_KEY في Colab Secrets">Gemini ✗</span>',
  ];
  if (s.openrouter_key) chips.push('<span class="chip ok">OpenRouter ✓</span>');
  $('#status-chips').innerHTML = chips.join('');
}

function renderSidebar() {
  const list = $('#project-list');
  if (!state.projects.length) {
    list.innerHTML = '<li class="sidebar-empty">لا توجد مشاريع بعد.</li>';
    return;
  }
  list.innerHTML = state.projects.map(p => `
    <li><button class="project-item ${state.project?.id === p.id ? 'active' : ''}" data-id="${esc(p.id)}">
      <span class="name" title="${esc(p.name)}">${esc(p.name)}</span>
      <span class="meta"><span class="stage-badge ${p.stage}">${STAGE_LABELS[p.stage] || ''}</span><span>${esc(fmtDate(p.created_at))}</span></span>
    </button></li>`).join('');
  for (const b of $$('.project-item', list)) b.addEventListener('click', () => selectProject(b.dataset.id));
}

function setView(view) {
  state.view = view;
  document.body.classList.toggle('view-templates', view === 'templates');
  $('#nav-projects').classList.toggle('active', view === 'projects');
  $('#nav-templates').classList.toggle('active', view === 'templates');
  if (view === 'templates') renderTemplatesView($('#main'), app);
  else if (state.project) renderProjectView();
  else renderWelcome();
}

function renderWelcome() {
  $('#main').innerHTML = `
    <div class="card empty">
      <div class="big">🎬</div>
      <h2>أهلًا بيك في AI Video Analyzer</h2>
      <p>كل الشغل التقيل (التفريغ والقص والتصدير) بيحصل على كولاب، وجهازك بيعرض الواجهة بس.</p>
      <ol class="steps">
        <li>ارفع الفيديو على جوجل درايف — مثلًا في فولدر <b class="ltr">${esc(state.status.videos_dir)}</b></li>
        <li>اعمل مشروع جديد واختار الفيديو</li>
        <li>فرّغ الصوت، وحلّله بالذكاء الاصطناعي، وراجع المقاطع المقترحة</li>
        <li>صدّر المقاطع بقالب أو من غيره — هتتحفظ على الدرايف مباشرة</li>
      </ol>
      <button class="btn primary lg" id="welcome-new">+ مشروع جديد</button>
    </div>`;
  $('#welcome-new').addEventListener('click', openDriveBrowser);
}

// ============================================================ projects

function stopAllPollers() {
  for (const k of Object.keys(pollers)) { pollers[k](); delete pollers[k]; }
}

async function selectProject(id) {
  if (state.dirty) await flushTopicSave();
  let project;
  try { project = await api(`api/projects/${encodeURIComponent(id)}`); }
  catch (e) { toast(e.message, 'error'); return; }
  stopAllPollers();
  state.jobs = {};
  state.project = project;
  state.playUntil = null;
  storageSet('ava:lastProject', id);
  state.tab = project.stage === 'new' ? 'transcript' : 'clips';
  setView('projects');
  renderSidebar();
  try {
    const active = await api(`api/jobs?project_id=${encodeURIComponent(id)}&active=true`);
    active.forEach(trackJob);
  } catch { /* jobs list is best-effort */ }
}

async function refreshProject() {
  if (!state.project) return;
  [state.project, state.projects] = await Promise.all([
    api(`api/projects/${encodeURIComponent(state.project.id)}`), api('api/projects'),
  ]);
  renderSidebar();
}

function renderProjectView() {
  const p = state.project;
  const m = p.media || {};
  const tabs = [
    ['transcript', 'التفريغ الصوتي', !!p.transcript?.segments?.length],
    ['clips', 'المقاطع', (p.topics || []).length > 0],
    ['export', 'التصدير', (p.exports || []).length > 0],
  ];
  $('#main').innerHTML = `
    <div class="card">
      <div class="project-head">
        <div style="flex:1;min-width:0">
          <h1>${esc(p.name)}</h1>
          <div class="info">
            <span>📁 <span class="ltr">${esc(p.video)}</span></span>
            <span>⏱ <span class="ltr">${fmtTime(m.duration || 0, 0)}</span></span>
            <span class="ltr">${m.width || '?'}×${m.height || '?'}</span>
            ${m.has_audio === false ? '<span class="hint warn">⚠ الفيديو ده بدون صوت</span>' : ''}
          </div>
        </div>
        <button class="btn danger sm" id="btn-delete-project">حذف المشروع</button>
      </div>
    </div>
    <div class="tabs">
      ${tabs.map(([k, label, done], i) => `<button class="tab ${state.tab === k ? 'active' : ''} ${done ? 'done' : ''}" data-tab="${k}"><span class="num">${done ? '✓' : i + 1}</span>${label}</button>`).join('')}
    </div>
    <div id="tab-body"></div>`;
  for (const b of $$('[data-tab]')) {
    b.addEventListener('click', async () => {
      if (state.dirty) await flushTopicSave();
      state.tab = b.dataset.tab;
      renderProjectView();
    });
  }
  $('#btn-delete-project').addEventListener('click', deleteProject);
  const body = $('#tab-body');
  if (state.tab === 'transcript') renderTranscriptTab(body);
  else if (state.tab === 'clips') renderClipsTab(body);
  else renderExportTab(body);
  for (const kind of Object.keys(state.jobs)) updateJobUI(kind);
}

async function deleteProject() {
  const p = state.project;
  const ok = await confirmDialog('حذف المشروع',
    `هتحذف المشروع "${p.name}" (التفريغ والمقاطع). الفيديو الأصلي والملفات المصدّرة على الدرايف مش هتتمسح.`,
    { okText: 'حذف', danger: true });
  if (!ok) return;
  try {
    await api(`api/projects/${encodeURIComponent(p.id)}`, { method: 'DELETE' });
    stopAllPollers();
    state.project = null;
    state.dirty = false;
    state.projects = await api('api/projects');
    renderSidebar();
    setView('projects');
    toast('تم حذف المشروع', 'success');
  } catch (e) { toast(e.message, 'error'); }
}

// ============================================================ jobs

function jobBoxHtml(job) {
  if (!job) return '';
  const active = ['queued', 'running'].includes(job.status);
  const pct = Math.round((job.progress || 0) * 100);
  const icon = { error: '⚠ ', cancelled: '⏹ ', done: '✓ ' }[job.status] || '';
  const details = job.status === 'error' && job.error && job.error !== job.message ? `<pre>${esc(job.error)}</pre>` : '';
  return `
    <div class="jobbox ${job.status}">
      <div class="row">
        <span class="msg">${icon}${esc(job.message || '')}</span>
        ${active ? `<span class="pct ltr">${pct}%</span><button class="btn sm" data-cancel>إلغاء</button>` : ''}
      </div>
      ${active ? `<div class="progress"><span style="width:${pct}%"></span></div>` : ''}
      ${details}
    </div>`;
}

function updateJobUI(kind) {
  const job = state.jobs[kind];
  for (const box of $$(`[data-jobbox="${kind}"]`)) {
    box.innerHTML = jobBoxHtml(job);
    box.querySelector('[data-cancel]')?.addEventListener('click', () => cancelJob(job.id));
  }
  const active = !!job && ['queued', 'running'].includes(job.status);
  for (const b of $$(`[data-job-trigger="${kind}"]`)) b.disabled = active || b.dataset.blocked === '1';
}

async function startJob(kind, url, body = {}) {
  try {
    const job = await api(url, { method: 'POST', body });
    trackJob(job);
    return job;
  } catch (e) {
    toast(e.message, 'error');
    return null;
  }
}

function trackJob(job) {
  const kind = job.kind;
  const pid = state.project?.id;
  state.jobs[kind] = job;
  updateJobUI(kind);
  pollers[kind]?.();
  pollers[kind] = pollJob(job.id, async j => {
    if (state.project?.id !== pid) return;
    state.jobs[kind] = { ...j, kind };
    updateJobUI(kind);
    if (TERMINAL.includes(j.status)) {
      delete pollers[kind];
      await onJobFinished(kind, j);
    }
  });
}

async function onJobFinished(kind, job) {
  if (job.status === 'done') {
    toast(DONE_MESSAGES[kind], 'success');
    delete state.jobs[kind];
    await refreshProject();
    if (kind === 'analyze') state.tab = 'clips';
    if (kind === 'export') state.tab = 'export';
    if (state.view === 'projects') renderProjectView();
  } else if (job.status === 'error') {
    toast(job.message || 'حدث خطأ', 'error');
  } else {
    toast('تم الإلغاء');
    delete state.jobs[kind];
    updateJobUI(kind);
  }
}

async function cancelJob(id) {
  try { await api(`api/jobs/${id}/cancel`, { method: 'POST' }); }
  catch (e) { toast(e.message, 'error'); }
}

// ============================================================ player

function playerHtml() {
  const p = state.project;
  if (p.has_preview) {
    return `<video class="player" id="player" controls preload="metadata" src="api/projects/${encodeURIComponent(p.id)}/preview?v=${p.preview_version || 0}"></video>`;
  }
  return `
    <div class="player-empty">
      <div class="big">🎞️</div>
      <p>المعاينة اختيارية: نسخة خفيفة (360p) من الفيديو عشان تشوف المقاطع وتظبط بدايتها ونهايتها بدقة.</p>
      <button class="btn" id="btn-preview" data-job-trigger="preview">تجهيز المعاينة</button>
      <div data-jobbox="preview"></div>
    </div>`;
}

function bindPlayer() {
  $('#btn-preview')?.addEventListener('click', () => startJob('preview', `api/projects/${encodeURIComponent(state.project.id)}/preview`));
  const v = $('#player');
  if (!v) return;
  v.addEventListener('timeupdate', () => {
    if (state.playUntil != null && v.currentTime >= state.playUntil) {
      v.pause();
      state.playUntil = null;
      markPlaying(null);
    }
  });
}

function playRange(start, end = null) {
  const v = $('#player');
  if (!v) return;
  v.currentTime = start;
  state.playUntil = end;
  v.play().catch(() => {});
}

function markPlaying(id) {
  for (const tr of $$('#clips-body tr')) tr.classList.toggle('playing', tr.dataset.id === id);
}

// ============================================================ transcript tab

function transcriptInfo(tr) {
  const lang = state.status.languages[tr.language] || tr.language || '';
  const engine = tr.engine === 'gemini' ? `Gemini (${tr.model})` : `Whisper ${tr.model}`;
  const device = tr.device === 'cuda' ? ' · على كارت الشاشة' : tr.device === 'cpu' ? ' · على المعالج' : '';
  return `${engine}${device}${lang ? ` · ${lang}` : ''}`;
}

function srtTime(t) {
  const ms = Math.round(t * 1000);
  const p2 = n => String(n).padStart(2, '0');
  return `${p2(Math.floor(ms / 3600000))}:${p2(Math.floor(ms % 3600000 / 60000))}:${p2(Math.floor(ms % 60000 / 1000))},${String(ms % 1000).padStart(3, '0')}`;
}

function renderTranscriptTab(body) {
  const p = state.project, s = state.status, st = state.settings;
  const tr = p.transcript;
  const segs = tr?.segments || [];
  const autoLabel = s.cuda ? 'تلقائي — Whisper على كارت الشاشة' : s.gemini_key ? 'تلقائي — Gemini (مفيش GPU)' : 'تلقائي — Whisper على المعالج';
  body.innerHTML = `
    <div class="card">
      <div class="card-head"><h3>التفريغ الصوتي</h3>${tr ? `<span class="muted">${esc(transcriptInfo(tr))}</span>` : ''}</div>
      <div class="form-row">
        <label class="field"><span>المحرك</span>
          <select id="tr-engine">
            <option value="auto">${autoLabel}</option>
            <option value="whisper">Whisper (على كولاب)</option>
            <option value="gemini" ${s.gemini_key ? '' : 'disabled'}>Gemini (سحابي)</option>
          </select></label>
        <label class="field"><span>نموذج Whisper</span>
          <select id="tr-model">
            <option value="auto" ${st.whisper_model === 'auto' ? 'selected' : ''}>تلقائي (${esc(s.whisper_default)})</option>
            ${s.whisper_models.map(m => `<option value="${m}" ${st.whisper_model === m ? 'selected' : ''}>${m}</option>`).join('')}
          </select></label>
        <label class="field"><span>لغة الفيديو</span>
          <select id="tr-lang">${Object.entries(s.languages).map(([k, v]) => `<option value="${k}" ${st.language === k ? 'selected' : ''}>${v}</option>`).join('')}</select></label>
        <button class="btn primary" id="tr-start" data-job-trigger="transcribe">${tr ? '↻ إعادة التفريغ' : '▶ بدء التفريغ'}</button>
      </div>
      ${s.cuda ? '' : '<p class="hint warn">⚠ الجلسة دي من غير GPU، فالتفريغ بـ Whisper هيبقى بطيء. للأسرع: من كولاب اختار Runtime ‹ Change runtime type ‹ T4 GPU وشغّل النوت بوك من جديد.</p>'}
      <div data-jobbox="transcribe"></div>
    </div>
    <div class="grid-2">
      <div class="card">
        <div class="card-head">
          <h3>النص المفرغ</h3>
          ${segs.length ? `<span class="muted">${segs.length} جملة</span>
            <div class="actions"><button class="btn sm" id="tr-srt">⬇ ترجمة SRT</button><button class="btn sm" id="tr-txt">⬇ نص TXT</button></div>` : ''}
        </div>
        ${segs.length
          ? `<div class="transcript">${segs.map((sg, i) => `<div class="seg ${p.has_preview ? 'clickable' : ''}" data-i="${i}"><span class="t ltr">${fmtTime(sg.start)}</span><span class="txt">${esc(sg.text)}</span></div>`).join('')}</div>`
          : '<div class="empty"><div class="big">📝</div><p>لسه مفيش نص. اختار الإعدادات واضغط "بدء التفريغ".</p></div>'}
      </div>
      <div class="card sticky-card"><div class="card-head"><h3>المعاينة</h3></div>${playerHtml()}</div>
    </div>`;

  $('#tr-start').addEventListener('click', () => startJob('transcribe', `api/projects/${encodeURIComponent(p.id)}/transcribe`, {
    engine: $('#tr-engine').value, model: $('#tr-model').value, language: $('#tr-lang').value,
  }));
  $('#tr-srt')?.addEventListener('click', () => downloadText(`${p.name}.srt`,
    segs.map((sg, i) => `${i + 1}\n${srtTime(sg.start)} --> ${srtTime(sg.end)}\n${sg.text}\n`).join('\n')));
  $('#tr-txt')?.addEventListener('click', () => downloadText(`${p.name}.txt`, segs.map(sg => sg.text).join('\n')));
  if (p.has_preview) {
    $('.transcript')?.addEventListener('click', e => {
      const seg = e.target.closest('.seg');
      if (seg) playRange(segs[Number(seg.dataset.i)].start);
    });
  }
  bindPlayer();
}

// ============================================================ clips tab

const scheduleTopicSave = debounce(() => saveTopics(), 700);

async function saveTopics() {
  const p = state.project;
  const el = $('#save-state');
  if (el) el.textContent = 'جارٍ الحفظ...';
  try {
    await api(`api/projects/${encodeURIComponent(p.id)}/topics`, { method: 'PUT', body: { topics: p.topics } });
    state.dirty = false;
    if (el) el.textContent = 'تم حفظ التعديلات ✓';
  } catch (e) {
    if (el) el.textContent = '';
    toast(`لم يتم حفظ التعديلات: ${e.message}`, 'error');
  }
}

async function flushTopicSave() {
  if (state.dirty) await scheduleTopicSave.flush();
}

function markDirty() {
  state.dirty = true;
  const el = $('#save-state');
  if (el) el.textContent = 'تعديلات غير محفوظة...';
  scheduleTopicSave();
}

function clipRowHtml(t) {
  const hasPlayer = !!state.project.has_preview;
  const dis = hasPlayer ? '' : 'disabled';
  return `
    <tr data-id="${esc(t.id)}" class="${t.selected ? '' : 'unselected'}">
      <td><input type="checkbox" data-f="selected" ${t.selected ? 'checked' : ''} title="تضمين في التصدير"></td>
      <td class="title-cell"><input type="text" class="title-input" data-f="name" value="${esc(t.name)}" placeholder="عنوان المقطع">
        ${t.text ? `<div class="clip-text" title="${esc(t.text)}">${esc(t.text)}</div>` : ''}</td>
      <td><input type="text" class="time-input" data-f="start" value="${fmtTime(t.start)}"></td>
      <td><input type="text" class="time-input" data-f="end" value="${fmtTime(t.end)}"></td>
      <td class="dur ltr">${fmtTime(t.end - t.start)}</td>
      <td class="row-actions">
        <button class="btn sm icon" data-a="play" title="تشغيل المقطع" ${dis}>▶</button>
        <button class="btn sm icon" data-a="set-start" title="البداية = مكان المشغّل الحالي" ${dis}>⇥</button>
        <button class="btn sm icon" data-a="set-end" title="النهاية = مكان المشغّل الحالي" ${dis}>⇤</button>
        <button class="btn sm icon danger" data-a="delete" title="حذف المقطع">✕</button>
      </td>
    </tr>`;
}

function updateClipsSummary() {
  const topics = state.project.topics || [];
  const sel = topics.filter(t => t.selected);
  const total = sel.reduce((a, t) => a + Math.max(0, t.end - t.start), 0);
  const el = $('#clips-summary');
  if (el) el.textContent = topics.length ? `${sel.length} محدد من ${topics.length} · الإجمالي ${fmtTime(total, 0)}` : '';
  $('#clips-empty')?.classList.toggle('hidden', topics.length > 0);
  $('#clips-table')?.classList.toggle('hidden', topics.length === 0);
}

function renderClipRows() {
  $('#clips-body').innerHTML = (state.project.topics || []).map(clipRowHtml).join('');
  updateClipsSummary();
}

function renderClipsTab(body) {
  const p = state.project, s = state.status, st = state.settings;
  p.topics = p.topics || [];
  const hasTranscript = !!p.transcript?.segments?.length;
  const providers = [['gemini', 'Gemini', s.gemini_key], ['openrouter', 'OpenRouter', s.openrouter_key]];
  body.innerHTML = `
    <div class="card">
      <div class="card-head"><h3>التحليل بالذكاء الاصطناعي</h3>
        ${p.analysis ? `<span class="muted">آخر تحليل: ${esc(MODE_LABELS[p.analysis.mode] || '')} · ${esc(p.analysis.model)}</span>` : ''}</div>
      <div class="form-row">
        <label class="field"><span>نمط التحليل</span>
          <select id="an-mode">${Object.entries(MODE_LABELS).map(([k, v]) => `<option value="${k}" ${(p.analysis?.mode || st.analysis_mode) === k ? 'selected' : ''}>${v}</option>`).join('')}</select></label>
        <label class="field"><span>مزود الذكاء الاصطناعي</span>
          <select id="an-provider">${providers.map(([v, l, ok]) => `<option value="${v}" ${st.analysis_provider === v ? 'selected' : ''} ${ok ? '' : 'disabled'}>${l}${ok ? '' : ' (بدون مفتاح)'}</option>`).join('')}</select></label>
        <button class="btn primary" id="an-start" data-job-trigger="analyze" ${hasTranscript ? '' : 'disabled data-blocked="1"'}>✨ ${p.topics.length ? 'إعادة التحليل' : 'تحليل واقتراح مقاطع'}</button>
      </div>
      ${!hasTranscript ? '<p class="hint warn">لازم تعمل تفريغ صوتي الأول (تبويب "التفريغ الصوتي").</p>'
        : p.topics.length ? '<p class="hint">إعادة التحليل هتستبدل كل المقاطع الحالية بمقترحات جديدة.</p>' : ''}
      <div data-jobbox="analyze"></div>
    </div>
    <div class="grid-2 wide-first">
      <div class="card">
        <div class="card-head">
          <h3>المقاطع</h3><span class="muted" id="clips-summary"></span>
          <div class="actions">
            <button class="btn sm" id="cl-add">+ مقطع يدوي</button>
            <button class="btn sm" id="cl-all">تحديد الكل</button>
            <button class="btn sm" id="cl-none">إلغاء التحديد</button>
          </div>
        </div>
        <div class="table-wrap" id="clips-table">
          <table class="clips">
            <thead><tr><th></th><th>العنوان</th><th>البداية</th><th>النهاية</th><th>المدة</th><th></th></tr></thead>
            <tbody id="clips-body"></tbody>
          </table>
        </div>
        <div class="empty hidden" id="clips-empty"><div class="big">✂️</div><p>لسه مفيش مقاطع. حلّل النص بالذكاء الاصطناعي أو أضف مقطع يدوي.</p></div>
        <div class="save-state" id="save-state"></div>
      </div>
      <div class="card sticky-card">
        <div class="card-head"><h3>المعاينة</h3></div>
        ${playerHtml()}
        <p class="hint">▶ يشغّل المقطع لوحده • ⇥ يخلي البداية = مكان المشغّل • ⇤ يخلي النهاية = مكان المشغّل</p>
      </div>
    </div>`;

  renderClipRows();
  bindPlayer();

  $('#an-start').addEventListener('click', async () => {
    if (p.topics.length && !(await confirmDialog('إعادة التحليل', 'المقاطع الحالية (وأي تعديلات عليها) هتتستبدل بمقترحات جديدة. تكمل؟', { okText: 'حلّل من جديد' }))) return;
    startJob('analyze', `api/projects/${encodeURIComponent(p.id)}/analyze`, {
      mode: $('#an-mode').value, provider: $('#an-provider').value,
    });
  });

  $('#cl-add').addEventListener('click', () => {
    const duration = p.media?.duration || 0;
    const player = $('#player');
    const last = p.topics[p.topics.length - 1];
    let start = player ? player.currentTime : (last ? last.end : 0);
    if (duration) start = Math.min(start, Math.max(0, duration - 1));
    const end = duration ? Math.min(duration, start + 30) : start + 30;
    const id = `t_${Math.random().toString(16).slice(2, 10)}`;
    p.topics.push({ id, name: 'مقطع جديد', text: '', start: Math.round(start * 10) / 10, end: Math.round(end * 10) / 10, selected: true });
    renderClipRows();
    markDirty();
    const input = $(`tr[data-id="${id}"] .title-input`);
    input?.focus();
    input?.select();
  });
  $('#cl-all').addEventListener('click', () => { p.topics.forEach(t => { t.selected = true; }); renderClipRows(); markDirty(); });
  $('#cl-none').addEventListener('click', () => { p.topics.forEach(t => { t.selected = false; }); renderClipRows(); markDirty(); });

  const tbody = $('#clips-body');
  const topicOf = el => p.topics.find(t => t.id === el.closest('tr').dataset.id);

  tbody.addEventListener('input', e => {
    if (e.target.dataset.f === 'name') { topicOf(e.target).name = e.target.value; markDirty(); }
  });
  tbody.addEventListener('change', e => {
    const el = e.target, f = el.dataset.f;
    if (!f) return;
    const t = topicOf(el);
    const row = el.closest('tr');
    if (f === 'selected') {
      t.selected = el.checked;
      row.classList.toggle('unselected', !el.checked);
      updateClipsSummary();
      markDirty();
      return;
    }
    if (f !== 'start' && f !== 'end') return;
    const value = parseTime(el.value);
    const duration = p.media?.duration || Infinity;
    const next = { start: t.start, end: t.end, [f]: value };
    let error = '';
    if (Number.isNaN(value)) error = 'صيغة الوقت غير صحيحة — اكتبها زي 1:23.4 أو 83.4';
    else if (value > duration) error = 'الوقت أكبر من مدة الفيديو';
    else if (next.end - next.start < 0.5) error = 'النهاية لازم تكون بعد البداية بنص ثانية على الأقل';
    if (error) {
      el.classList.add('invalid');
      toast(error, 'error');
      return;
    }
    $$('.time-input', row).forEach(i => i.classList.remove('invalid'));
    t[f] = Math.round(value * 100) / 100;
    el.value = fmtTime(t[f]);
    $('.dur', row).textContent = fmtTime(t.end - t.start);
    updateClipsSummary();
    markDirty();
  });
  tbody.addEventListener('click', async e => {
    const btn = e.target.closest('[data-a]');
    if (!btn) return;
    const t = topicOf(btn);
    const row = btn.closest('tr');
    const player = $('#player');
    if (btn.dataset.a === 'play') {
      markPlaying(t.id);
      playRange(t.start, t.end);
    } else if (btn.dataset.a === 'set-start' || btn.dataset.a === 'set-end') {
      if (!player) return;
      const f = btn.dataset.a === 'set-start' ? 'start' : 'end';
      const value = Math.round(player.currentTime * 10) / 10;
      const next = { start: t.start, end: t.end, [f]: value };
      if (next.end - next.start < 0.5) { toast('النهاية لازم تكون بعد البداية', 'error'); return; }
      t[f] = value;
      $(`[data-f="${f}"]`, row).value = fmtTime(value);
      $(`[data-f="${f}"]`, row).classList.remove('invalid');
      $('.dur', row).textContent = fmtTime(t.end - t.start);
      updateClipsSummary();
      markDirty();
    } else if (btn.dataset.a === 'delete') {
      p.topics = p.topics.filter(x => x.id !== t.id);
      row.remove();
      updateClipsSummary();
      markDirty();
    }
  });
}

// ============================================================ export tab

function exportsHtml(p) {
  const exports = (p.exports || []).slice().reverse();
  if (!exports.length) return '<div class="empty"><div class="big">📦</div><p>لسه مفيش تصدير للمشروع ده.</p></div>';
  return `<p class="hint" style="margin:0 0 12px">الملفات محفوظة على جوجل درايف في الفولدرات دي — التحميل على جهازك اختياري.</p>` +
    exports.map(ex => `
      <div class="export-item">
        <div class="inline"><b>${esc(fmtDate(ex.at))}</b><span class="muted">📁 <span class="ltr">${esc(ex.folder)}</span></span></div>
        ${ex.files.map(f => `
          <div class="file-row"><span>🎬</span><span class="fname" title="${esc(f)}">${esc(f.split('/').pop().replace(/\.mp4$/i, ''))}</span>
            <a class="btn sm" href="api/files?path=${encodeURIComponent(f)}" download>تحميل</a></div>`).join('')}
      </div>`).join('');
}

function renderExportTab(body) {
  const p = state.project;
  const topics = p.topics || [];
  const selected = topics.filter(t => t.selected);
  const total = selected.reduce((a, t) => a + Math.max(0, t.end - t.start), 0);
  if (!state.templates.some(t => t.id === state.exportTemplateId)) state.exportTemplateId = '';
  body.innerHTML = `
    <div class="grid-2">
      <div class="card">
        <div class="card-head"><h3>إعدادات التصدير</h3></div>
        <div class="stack">
          <label class="field"><span>القالب</span>
            <select id="ex-template">
              <option value="">بدون قالب — قص المقاطع زي ما هي</option>
              ${state.templates.map(t => `<option value="${esc(t.id)}" ${state.exportTemplateId === t.id ? 'selected' : ''}>${esc(t.name)} (${t.canvas_w}×${t.canvas_h})</option>`).join('')}
            </select>
            <span class="hint" style="margin:0">تقدر تعمل أو تعدّل القوالب من <a href="#" id="ex-go-templates">صفحة القوالب</a>.</span></label>
          <div class="ex-thumb hidden" id="ex-thumb"><canvas></canvas></div>
          <div class="field" id="ex-cut"><span>طريقة القص</span>
            <label class="radio"><input type="radio" name="cutmode" value="accurate" checked><div><b>دقيق</b><small>بيقص على التوقيت بالظبط (بيعيد ترميز الفيديو)</small></div></label>
            <label class="radio"><input type="radio" name="cutmode" value="fast"><div><b>سريع جدًا</b><small>من غير إعادة ترميز — لكن البداية ممكن تبقى قبل التوقيت بثانية أو اتنين</small></div></label>
          </div>
          <p class="hint hidden" id="ex-tpl-note" style="margin:0">مع القالب لازم إعادة ترميز، فالقص هيبقى دقيق دايمًا.</p>
          <label class="field"><span>اسم فولدر الحفظ على الدرايف</span>
            <input type="text" id="ex-folder" value="${esc(p.name)}">
            <span class="hint" style="margin:0">هيتحفظ في: <span class="ltr" id="ex-path"></span></span></label>
        </div>
        <div class="summary"><span>🎬 ${selected.length} مقطع محدد</span><span>⏱ الإجمالي ${fmtTime(total, 0)}</span></div>
        ${selected.length ? '' : '<p class="hint warn" style="margin:0 0 12px">مفيش مقاطع محددة — حدد المقاطع من تبويب "المقاطع".</p>'}
        <button class="btn primary lg block" id="ex-start" data-job-trigger="export" ${selected.length ? '' : 'disabled data-blocked="1"'}>⬇ تصدير ${selected.length} مقطع</button>
        <div data-jobbox="export"></div>
      </div>
      <div class="card">
        <div class="card-head"><h3>الملفات المصدّرة</h3></div>
        ${exportsHtml(p)}
      </div>
    </div>`;

  const updatePath = () => { $('#ex-path').textContent = `${state.status.data_root}/outputs/${$('#ex-folder').value.trim() || p.name}`; };
  const updateTemplateUI = () => {
    const tpl = state.templates.find(t => t.id === $('#ex-template').value);
    $('#ex-cut').classList.toggle('hidden', !!tpl);
    $('#ex-tpl-note').classList.toggle('hidden', !tpl);
    $('#ex-thumb').classList.toggle('hidden', !tpl);
    if (tpl) {
      drawTemplateThumb($('#ex-thumb canvas'), tpl, { title: selected[0]?.name || 'عنوان المقطع', n: 1 },
        { maxW: 360, backgroundUrl: templateAssetUrl(tpl, 'background') });
    }
  };
  $('#ex-template').addEventListener('change', e => {
    state.exportTemplateId = e.target.value;
    storageSet('ava:exportTemplate', e.target.value);
    updateTemplateUI();
  });
  $('#ex-folder').addEventListener('input', updatePath);
  $('#ex-go-templates').addEventListener('click', e => { e.preventDefault(); setView('templates'); });
  $('#ex-start').addEventListener('click', startExport);
  updatePath();
  updateTemplateUI();
}

async function startExport() {
  await flushTopicSave();
  const p = state.project;
  const selected = (p.topics || []).filter(t => t.selected);
  const tplId = $('#ex-template').value || null;
  const btn = $('#ex-start');
  let overlays = {};
  if (tplId) {
    btn.disabled = true;
    btn.textContent = 'جارٍ تجهيز نصوص القالب...';
    try {
      overlays = await renderOverlays(state.templates.find(t => t.id === tplId), selected);
    } catch (e) {
      toast(`تعذر تجهيز نصوص القالب: ${e.message}`, 'error');
      btn.disabled = false;
      btn.textContent = `⬇ تصدير ${selected.length} مقطع`;
      return;
    }
  }
  await startJob('export', `api/projects/${encodeURIComponent(p.id)}/export`, {
    topic_ids: selected.map(t => t.id),
    template_id: tplId,
    overlays,
    cut_mode: tplId ? 'accurate' : $('input[name=cutmode]:checked').value,
    folder: $('#ex-folder').value.trim() || p.name,
  });
  btn.textContent = `⬇ تصدير ${selected.length} مقطع`;
  updateJobUI('export');
}

// ============================================================ drive browser

function openDriveBrowser() {
  const m = modal({
    title: 'اختار فيديو من جوجل درايف',
    body: `
      <div class="crumbs" id="fs-crumbs"></div>
      <div class="fs-list" id="fs-list"><div class="fs-empty">جارٍ التحميل...</div></div>
      <p class="hint">💡 الفيديوهات اللي "اتشاركت معاك" بتظهر هنا لو عملت لها "Add shortcut to Drive" من موقع جوجل درايف.</p>`,
  });
  const list = $('#fs-list', m.el);

  const load = async path => {
    list.innerHTML = '<div class="fs-empty">جارٍ التحميل...</div>';
    let data;
    try { data = await api(`api/browse?path=${encodeURIComponent(path)}`); }
    catch (e) {
      if (path) { load(''); return; }
      list.innerHTML = `<div class="fs-empty">${esc(e.message)}</div>`;
      return;
    }
    const parts = data.path ? data.path.split('/') : [];
    $('#fs-crumbs', m.el).innerHTML = `<button data-path="">My Drive</button>` + parts.map((part, i) =>
      `<span class="sep">‹</span><button data-path="${esc(parts.slice(0, i + 1).join('/'))}">${esc(part)}</button>`).join('');
    const rows = [];
    if (data.parent !== null) rows.push(`<button class="fs-item" data-dir="${esc(data.parent)}"><span class="ico">⬆</span><span class="nm">للأعلى</span></button>`);
    rows.push(...data.dirs.map(d => `<button class="fs-item" data-dir="${esc(d.path)}"><span class="ico">📁</span><span class="nm">${esc(d.name)}</span></button>`));
    rows.push(...data.files.map(f => `<button class="fs-item" data-file="${esc(f.path)}"><span class="ico">🎬</span><span class="nm">${esc(f.name)}</span><span class="sz ltr">${fmtBytes(f.size)}</span></button>`));
    if (!data.dirs.length && !data.files.length) rows.push('<div class="fs-empty">الفولدر ده مفيهوش فيديوهات ولا فولدرات.</div>');
    list.innerHTML = rows.join('');
  };

  m.el.addEventListener('click', async e => {
    const crumb = e.target.closest('#fs-crumbs [data-path]');
    if (crumb) { load(crumb.dataset.path); return; }
    const dir = e.target.closest('[data-dir]');
    if (dir) { load(dir.dataset.dir); return; }
    const file = e.target.closest('[data-file]');
    if (!file) return;
    $$('.fs-item', list).forEach(b => { b.disabled = true; });
    $('.sz', file).textContent = 'جارٍ إنشاء المشروع...';
    try {
      const project = await api('api/projects', { method: 'POST', body: { video: file.dataset.file } });
      m.close();
      state.projects = await api('api/projects');
      await selectProject(project.id);
      toast('تم إنشاء المشروع ✓', 'success');
    } catch (err) {
      toast(err.message, 'error');
      $$('.fs-item', list).forEach(b => { b.disabled = false; });
      $('.sz', file).textContent = '';
    }
  });

  load(state.status.videos_dir);
}

// ============================================================ settings

function openSettings() {
  const s = state.settings, st = state.status;
  const opt = (v, l, cur) => `<option value="${esc(v)}" ${cur === v ? 'selected' : ''}>${esc(l)}</option>`;
  const m = modal({
    title: 'الإعدادات',
    body: `
      <div class="field-grid">
        <label class="field full"><span>مزود التحليل الافتراضي</span>
          <select id="set-provider">${opt('gemini', 'Gemini', s.analysis_provider)}${opt('openrouter', 'OpenRouter', s.analysis_provider)}</select></label>
        <label class="field full"><span>نموذج Gemini</span><input type="text" id="set-gemini" class="ltr" value="${esc(s.gemini_model)}">
          <span class="hint" style="margin:0">بيُستخدم للتحليل وللتفريغ السحابي.</span></label>
        <label class="field full"><span>نموذج OpenRouter</span><input type="text" id="set-openrouter" class="ltr" value="${esc(s.openrouter_model)}"></label>
        <label class="field"><span>نموذج Whisper الافتراضي</span>
          <select id="set-whisper">${opt('auto', `تلقائي (${st.whisper_default})`, s.whisper_model)}${st.whisper_models.map(x => opt(x, x, s.whisper_model)).join('')}</select></label>
        <label class="field"><span>اللغة الافتراضية</span>
          <select id="set-lang">${Object.entries(st.languages).map(([k, v]) => opt(k, v, s.language)).join('')}</select></label>
        <label class="field full"><span>نمط التحليل الافتراضي</span>
          <select id="set-mode">${Object.entries(MODE_LABELS).map(([k, v]) => opt(k, v, s.analysis_mode)).join('')}</select></label>
        <label class="check full"><input type="checkbox" id="set-snap" ${s.snap_to_words ? 'checked' : ''}> ضبط بداية ونهاية المقاطع المقترحة على حدود الكلمات (مع Whisper)</label>
      </div>
      <div class="card" style="margin-top:16px;background:var(--surface-2);box-shadow:none">
        <h4>مفاتيح API</h4>
        <p class="muted">المفاتيح بتتحفظ في <b>Colab Secrets</b> (أيقونة 🔑 في شريط كولاب الجانبي) بالأسماء
          <b class="ltr">GEMINI_API_KEY</b> و <b class="ltr">OPENROUTER_API_KEY</b>، وبعدها شغّل خلية التشغيل في النوت بوك من جديد.</p>
        <div class="chips" style="margin-top:8px">
          <span class="chip ${st.gemini_key ? 'ok' : 'bad'}">Gemini ${st.gemini_key ? '✓' : '✗'}</span>
          <span class="chip ${st.openrouter_key ? 'ok' : ''}">OpenRouter ${st.openrouter_key ? '✓' : '—'}</span>
        </div>
      </div>`,
    footer: '<button class="btn" data-cancel>إلغاء</button><button class="btn primary" data-save>حفظ</button>',
  });
  $('[data-cancel]', m.el).addEventListener('click', m.close);
  $('[data-save]', m.el).addEventListener('click', async () => {
    try {
      state.settings = await api('api/settings', {
        method: 'PUT',
        body: {
          settings: {
            analysis_provider: $('#set-provider', m.el).value,
            gemini_model: $('#set-gemini', m.el).value.trim() || s.gemini_model,
            openrouter_model: $('#set-openrouter', m.el).value.trim() || s.openrouter_model,
            whisper_model: $('#set-whisper', m.el).value,
            language: $('#set-lang', m.el).value,
            analysis_mode: $('#set-mode', m.el).value,
            snap_to_words: $('#set-snap', m.el).checked,
          },
        },
      });
      m.close();
      toast('تم حفظ الإعدادات ✓', 'success');
      if (state.view === 'projects' && state.project) renderProjectView();
    } catch (e) { toast(e.message, 'error'); }
  });
}

init();
