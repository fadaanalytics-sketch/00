import { api } from './api.js';
import { $, $$, esc, toast, confirmDialog, readFileAsDataURL } from './util.js';
import {
  FONTS, SAMPLE_VARS, even, ensureFonts, loadImage, drawBackground, drawVideoPlaceholder, drawTexts,
  drawSelection, hitTest, textBounds, drawTemplateThumb,
} from './template-render.js';

const PRESETS = [
  { key: '9x16', label: '9:16 — ريلز / شورتس / تيك توك', w: 1080, h: 1920 },
  { key: '1x1', label: '1:1 — منشور مربع', w: 1080, h: 1080 },
  { key: '4x5', label: '4:5 — إنستجرام', w: 1080, h: 1350 },
  { key: '16x9', label: '16:9 — يوتيوب', w: 1920, h: 1080 },
];
const MAX_SIDE = 4096;
const rid = () => `x${Math.random().toString(36).slice(2, 9)}`;
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

export const templateAssetUrl = (tpl, kind) =>
  `api/templates/${encodeURIComponent(tpl.id)}/${kind}?v=${encodeURIComponent(tpl.updated_at || '')}`;

function newText(tpl, overrides = {}) {
  return {
    id: rid(), text: '{title}', x: Math.round(tpl.canvas_w / 2), y: Math.round(tpl.canvas_h * 0.08),
    size: Math.round(tpl.canvas_w / 15), font: 'Cairo', weight: 800, color: '#ffffff',
    stroke_color: '#000000', stroke_width: 0, box_color: '', align: 'center',
    max_width: Math.round(tpl.canvas_w * 0.88), line_height: 1.3, ...overrides,
  };
}

export function newTemplate() {
  const tpl = {
    id: null, name: 'قالب جديد', canvas_w: 1080, canvas_h: 1920, bg_color: '#111827', bg_fit: 'cover',
    video: { x: 0, y: 420, w: 1080, h: 1080, fit: 'cover' }, texts: [],
  };
  tpl.texts.push(newText(tpl, { y: 170 }));
  return tpl;
}

// ---------------------------------------------------------------- list view

export async function renderTemplatesView(main, app) {
  main.innerHTML = `
    <div class="page-head">
      <h1>القوالب</h1>
      <div class="spacer"></div>
      <button class="btn primary" id="tpl-new">+ قالب جديد</button>
      <p class="desc">القالب = خلفية (لون أو صورة) + مكان الفيديو + نصوص. اكتب <b class="ltr">{title}</b> في أي نص عشان يتبدل تلقائيًا بعنوان كل مقطع عند التصدير.</p>
    </div>
    <div class="tpl-grid" id="tpl-grid"></div>`;
  $('#tpl-new').addEventListener('click', () => openEditor(main, app, newTemplate()));
  const grid = $('#tpl-grid');
  const templates = app.state.templates;
  grid.innerHTML = templates.map(t => `
    <div class="tpl-card" data-id="${esc(t.id)}">
      <div class="thumb-wrap"><canvas></canvas></div>
      <div class="foot">
        <span class="name" title="${esc(t.name)}">${esc(t.name)}</span>
        <span class="muted ltr">${t.canvas_w}×${t.canvas_h}</span>
        <button class="btn sm" data-edit>تعديل</button>
        <button class="btn sm danger icon" data-del title="حذف">✕</button>
      </div>
    </div>`).join('') + '<button class="tpl-new" id="tpl-new-card">+ قالب جديد</button>';
  $('#tpl-new-card').addEventListener('click', () => openEditor(main, app, newTemplate()));
  for (const card of $$('.tpl-card', grid)) {
    const tpl = templates.find(t => t.id === card.dataset.id);
    drawTemplateThumb($('canvas', card), tpl, SAMPLE_VARS, { backgroundUrl: templateAssetUrl(tpl, 'background') });
    $('[data-edit]', card).addEventListener('click', () => openEditor(main, app, structuredClone(tpl)));
    $('[data-del]', card).addEventListener('click', async () => {
      if (!(await confirmDialog('حذف القالب', `هتحذف القالب "${tpl.name}" نهائيًا؟`, { okText: 'حذف', danger: true }))) return;
      try {
        await api(`api/templates/${encodeURIComponent(tpl.id)}`, { method: 'DELETE' });
        await app.reloadTemplates();
        renderTemplatesView(main, app);
        toast('تم حذف القالب', 'success');
      } catch (e) { toast(e.message, 'error'); }
    });
  }
}

// ---------------------------------------------------------------- editor

async function openEditor(main, app, tpl) {
  const E = { tpl, srcImg: null, srcDataUrl: null, srcChanged: false, clearSource: false, sel: null, drag: null, guides: {} };
  if (tpl.id && tpl.source_file) {
    E.srcImg = await loadImage(templateAssetUrl(tpl, 'source')).catch(() => null);
  }

  main.innerHTML = `
    <div class="page-head">
      <button class="btn ghost" id="te-back">→ رجوع للقوالب</button>
      <h1>${tpl.id ? 'تعديل القالب' : 'قالب جديد'}</h1>
      <div class="spacer"></div>
      ${tpl.id ? '<button class="btn danger" id="te-delete">حذف</button>' : ''}
      <button class="btn primary" id="te-save">💾 حفظ القالب</button>
    </div>
    <div class="tpl-editor">
      <div class="stage">
        <canvas id="te-canvas"></canvas>
        <div class="stage-hint">اسحب الفيديو أو النصوص لتحريكها • اسحب أركان الفيديو لتغيير حجمه (Shift للحفاظ على النسبة)</div>
      </div>
      <div class="props stack" id="te-props"></div>
    </div>`;

  const canvas = $('#te-canvas');
  const ctx = canvas.getContext('2d');
  E.canvas = canvas;
  E.ctx = ctx;

  const render = () => {
    const W = even(E.tpl.canvas_w), H = even(E.tpl.canvas_h);
    if (canvas.width !== W || canvas.height !== H) { canvas.width = W; canvas.height = H; }
    drawBackground(ctx, E.tpl, E.srcImg);
    drawVideoPlaceholder(ctx, E.tpl, E.sel?.type === 'video');
    drawTexts(ctx, E.tpl, SAMPLE_VARS);
    drawSelection(ctx, E.tpl, E.sel, SAMPLE_VARS, E.guides);
  };
  const renderWithFonts = () => { render(); ensureFonts(E.tpl).then(render); };
  E.render = render;

  const selectedText = () => (E.sel?.type === 'text' ? E.tpl.texts.find(t => t.id === E.sel.id) : null);

  // ---- properties panel ----
  const renderProps = () => {
    const t = E.tpl, v = t.video, st = selectedText();
    const preset = PRESETS.find(p => p.w === t.canvas_w && p.h === t.canvas_h)?.key || 'custom';
    $('#te-props').innerHTML = `
      <section class="card">
        <h4>عام</h4>
        <div class="field-grid">
          <label class="field full"><span>اسم القالب</span><input type="text" data-bind="name" value="${esc(t.name)}"></label>
          <label class="field full"><span>المقاس</span>
            <select id="te-preset">
              ${PRESETS.map(p => `<option value="${p.key}" ${p.key === preset ? 'selected' : ''}>${p.label}</option>`).join('')}
              <option value="custom" ${preset === 'custom' ? 'selected' : ''}>مخصص</option>
              ${E.srcImg ? '<option value="image">نفس مقاس صورة الخلفية</option>' : ''}
            </select></label>
          <label class="field"><span>العرض</span><input type="number" step="2" min="64" max="${MAX_SIDE}" id="te-w" value="${t.canvas_w}"></label>
          <label class="field"><span>الارتفاع</span><input type="number" step="2" min="64" max="${MAX_SIDE}" id="te-h" value="${t.canvas_h}"></label>
          <label class="field"><span>لون الخلفية</span><input type="color" data-bind="bg_color" value="${esc(t.bg_color)}"></label>
          <label class="field"><span>ملاءمة الصورة</span>
            <select data-bind="bg_fit">
              <option value="cover" ${t.bg_fit === 'cover' ? 'selected' : ''}>تغطية</option>
              <option value="contain" ${t.bg_fit === 'contain' ? 'selected' : ''}>احتواء</option>
              <option value="stretch" ${t.bg_fit === 'stretch' ? 'selected' : ''}>تمديد</option>
            </select></label>
          <div class="field full">
            <span>صورة الخلفية</span>
            <div class="inline">
              <label class="btn sm">🖼 ${E.srcImg ? 'تغيير الصورة' : 'اختيار صورة'}<input type="file" id="te-image" accept="image/png,image/jpeg,image/webp" hidden></label>
              ${E.srcImg ? '<button class="btn sm danger" id="te-image-clear">إزالة الصورة</button>' : ''}
            </div>
          </div>
        </div>
      </section>
      <section class="card">
        <h4>الفيديو</h4>
        <div class="field-grid">
          <label class="field"><span>X</span><input type="number" data-bind="video.x" data-num value="${v.x}"></label>
          <label class="field"><span>Y</span><input type="number" data-bind="video.y" data-num value="${v.y}"></label>
          <label class="field"><span>العرض</span><input type="number" min="16" data-bind="video.w" data-num value="${v.w}"></label>
          <label class="field"><span>الارتفاع</span><input type="number" min="16" data-bind="video.h" data-num value="${v.h}"></label>
          <label class="field full"><span>طريقة وضع الفيديو في مساحته</span>
            <select data-bind="video.fit">
              <option value="cover" ${v.fit === 'cover' ? 'selected' : ''}>تغطية — يملأ المساحة ويقص الزيادة</option>
              <option value="contain" ${v.fit === 'contain' ? 'selected' : ''}>احتواء — يظهر كامل بدون قص</option>
              <option value="stretch" ${v.fit === 'stretch' ? 'selected' : ''}>تمديد — يملأ المساحة ويشوّه النسبة</option>
            </select></label>
          <div class="full inline">
            <button class="btn sm" id="te-v-fullw">ملء العرض</button>
            <button class="btn sm" id="te-v-center">توسيط أفقي</button>
            <button class="btn sm" id="te-v-middle">توسيط رأسي</button>
          </div>
        </div>
      </section>
      <section class="card">
        <h4>النصوص</h4>
        <div class="text-list">
          ${t.texts.map(x => `<button data-select-text="${x.id}" class="${st?.id === x.id ? 'active' : ''}">${esc(x.text || '(نص فارغ)')}</button>`).join('')}
        </div>
        <button class="btn sm" id="te-add-text">+ إضافة نص</button>
        ${st ? textPropsHtml(st) : '<p class="hint">اختار نص من القائمة أو من على القالب لتعديله.</p>'}
      </section>`;
    bindProps();
  };

  const textPropsHtml = st => `
    <div class="field-grid" style="margin-top:12px">
      <label class="field full"><span>النص</span><textarea data-bind="text.text" rows="2">${esc(st.text)}</textarea>
        <span class="muted" style="font-size:12px">متغيرات: <span class="chip-hint" data-insert="{title}">{title}</span> عنوان المقطع
          <span class="chip-hint" data-insert="{n}">{n}</span> رقم المقطع</span></label>
      <label class="field full"><span>الخط</span>
        <select data-bind="text.font">${FONTS.map(f => `<option value="${f}" ${st.font === f ? 'selected' : ''} style="font-family:'${f}'">${f}</option>`).join('')}</select></label>
      <label class="field"><span>الحجم</span><input type="number" min="6" max="600" data-bind="text.size" data-num value="${st.size}"></label>
      <label class="field"><span>السُمك</span>
        <select data-bind="text.weight" data-num>
          ${[[400, 'عادي'], [700, 'عريض'], [900, 'عريض جدًا']].map(([w, l]) => `<option value="${w}" ${Number(st.weight) === w ? 'selected' : ''}>${l}</option>`).join('')}
        </select></label>
      <label class="field"><span>اللون</span><input type="color" data-bind="text.color" value="${esc(st.color)}"></label>
      <label class="field"><span>المحاذاة</span>
        <div class="segmented">
          ${[['right', 'يمين'], ['center', 'وسط'], ['left', 'يسار']].map(([a, l]) => `<button type="button" data-align="${a}" class="${st.align === a ? 'active' : ''}">${l}</button>`).join('')}
        </div></label>
      <label class="field"><span>لون الحدود</span><input type="color" data-bind="text.stroke_color" value="${esc(st.stroke_color || '#000000')}"></label>
      <label class="field"><span>سُمك الحدود</span><input type="number" min="0" max="60" data-bind="text.stroke_width" data-num value="${st.stroke_width || 0}"></label>
      <label class="field"><span>أقصى عرض للسطر</span><input type="number" min="0" data-bind="text.max_width" data-num value="${st.max_width || 0}"></label>
      <label class="field"><span>تباعد الأسطر</span><input type="number" min="0.8" max="3" step="0.1" data-bind="text.line_height" data-num value="${st.line_height || 1.3}"></label>
      <div class="field full">
        <label class="check"><input type="checkbox" id="te-box" ${st.box_color ? 'checked' : ''}> خلفية خلف النص</label>
        ${st.box_color ? `<input type="color" data-bind="text.box_color" value="${esc(st.box_color)}">` : ''}
      </div>
      <div class="full inline">
        <button class="btn sm" id="te-t-center">توسيط أفقي</button>
        <button class="btn sm danger" id="te-t-delete">حذف النص</button>
      </div>
    </div>`;

  const setPath = (path, value) => {
    const [head, key] = path.split('.');
    if (!key) { E.tpl[head] = value; return; }
    if (head === 'video') E.tpl.video[key] = value;
    else if (head === 'text' && selectedText()) selectedText()[key] = value;
  };

  const bindProps = () => {
    for (const el of $$('[data-bind]', $('#te-props'))) {
      el.addEventListener('input', () => {
        let value = el.value;
        if ('num' in el.dataset) {
          value = Number(value);
          if (!Number.isFinite(value)) return;
        }
        setPath(el.dataset.bind, value);
        if (el.dataset.bind === 'text.text') {
          const btn = $(`[data-select-text="${E.sel.id}"]`);
          if (btn) btn.textContent = value || '(نص فارغ)';
        }
        if (el.dataset.bind === 'text.font' || el.dataset.bind === 'text.weight') renderWithFonts();
        else render();
      });
    }
    $('#te-preset').addEventListener('change', e => {
      const val = e.target.value;
      if (val === 'custom') return;
      if (val === 'image' && E.srcImg) {
        const s = Math.min(1, MAX_SIDE / Math.max(E.srcImg.naturalWidth, E.srcImg.naturalHeight));
        resizeCanvas(E.srcImg.naturalWidth * s, E.srcImg.naturalHeight * s);
      } else {
        const p = PRESETS.find(x => x.key === val);
        resizeCanvas(p.w, p.h);
      }
      renderProps();
      render();
    });
    for (const id of ['#te-w', '#te-h']) {
      $(id).addEventListener('change', () => {
        resizeCanvas(Number($('#te-w').value) || E.tpl.canvas_w, Number($('#te-h').value) || E.tpl.canvas_h);
        renderProps();
        render();
      });
    }
    $('#te-image').addEventListener('change', async e => {
      const file = e.target.files[0];
      if (!file) return;
      try {
        let dataUrl = await readFileAsDataURL(file);
        let img = await loadImage(dataUrl);
        // Huge photos would make the upload slow for no visible gain.
        const s = Math.min(1, MAX_SIDE / Math.max(img.naturalWidth, img.naturalHeight));
        if (s < 1) {
          const c = document.createElement('canvas');
          c.width = Math.round(img.naturalWidth * s);
          c.height = Math.round(img.naturalHeight * s);
          c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
          dataUrl = c.toDataURL('image/jpeg', 0.92);
          img = await loadImage(dataUrl);
        }
        Object.assign(E, { srcImg: img, srcDataUrl: dataUrl, srcChanged: true, clearSource: false });
        renderProps();
        render();
      } catch (err) { toast(err.message, 'error'); }
    });
    $('#te-image-clear')?.addEventListener('click', () => {
      Object.assign(E, { srcImg: null, srcDataUrl: null, srcChanged: false, clearSource: true });
      renderProps();
      render();
    });
    $('#te-v-fullw').addEventListener('click', () => {
      const v = E.tpl.video;
      const ratio = v.h / v.w;
      v.x = 0; v.w = E.tpl.canvas_w; v.h = Math.round(v.w * ratio);
      afterChange();
    });
    $('#te-v-center').addEventListener('click', () => { E.tpl.video.x = Math.round((E.tpl.canvas_w - E.tpl.video.w) / 2); afterChange(); });
    $('#te-v-middle').addEventListener('click', () => { E.tpl.video.y = Math.round((E.tpl.canvas_h - E.tpl.video.h) / 2); afterChange(); });
    $('#te-add-text').addEventListener('click', () => {
      const t = newText(E.tpl, { text: 'نص جديد', y: Math.round(E.tpl.canvas_h * 0.85), weight: 700, size: Math.round(E.tpl.canvas_w / 20) });
      E.tpl.texts.push(t);
      E.sel = { type: 'text', id: t.id };
      renderProps();
      renderWithFonts();
    });
    for (const b of $$('[data-select-text]')) {
      b.addEventListener('click', () => { E.sel = { type: 'text', id: b.dataset.selectText }; renderProps(); render(); });
    }
    for (const chip of $$('[data-insert]')) {
      chip.addEventListener('click', () => {
        const ta = $('[data-bind="text.text"]');
        const pos = ta.selectionStart ?? ta.value.length;
        ta.value = ta.value.slice(0, pos) + chip.dataset.insert + ta.value.slice(ta.selectionEnd ?? pos);
        ta.dispatchEvent(new Event('input'));
        ta.focus();
      });
    }
    for (const b of $$('[data-align]')) {
      b.addEventListener('click', () => {
        const st = selectedText();
        const bounds = textBounds(ctx, st, SAMPLE_VARS);
        st.align = b.dataset.align;
        // Keep the text visually in place: move the anchor to the matching edge.
        st.x = Math.round(st.align === 'center' ? bounds.x + bounds.w / 2 : st.align === 'right' ? bounds.x + bounds.w : bounds.x);
        if (st.box_color) st.x += st.align === 'right' ? -st.size * 0.35 : st.align === 'left' ? st.size * 0.35 : 0;
        renderProps();
        render();
      });
    }
    $('#te-box')?.addEventListener('change', e => {
      selectedText().box_color = e.target.checked ? '#000000' : '';
      renderProps();
      render();
    });
    $('#te-t-center')?.addEventListener('click', () => {
      const st = selectedText();
      const b = textBounds(ctx, st, SAMPLE_VARS);
      st.x = Math.round(st.x + (E.tpl.canvas_w / 2 - (b.x + b.w / 2)));
      afterChange();
    });
    $('#te-t-delete')?.addEventListener('click', () => {
      E.tpl.texts = E.tpl.texts.filter(x => x.id !== E.sel.id);
      E.sel = null;
      renderProps();
      render();
    });
  };

  const afterChange = () => { syncInputs(); render(); };

  const syncInputs = () => {
    const props = $('#te-props');
    for (const el of $$('[data-bind]', props)) {
      const [head, key] = el.dataset.bind.split('.');
      const src = head === 'video' ? E.tpl.video : head === 'text' ? selectedText() : E.tpl;
      const k = key || head;
      if (src && document.activeElement !== el && src[k] !== undefined) el.value = src[k];
    }
  };

  const resizeCanvas = (w, h) => {
    const t = E.tpl;
    const nw = clamp(even(w), 64, MAX_SIDE), nh = clamp(even(h), 64, MAX_SIDE);
    const sx = nw / t.canvas_w, sy = nh / t.canvas_h, sf = Math.min(sx, sy);
    const v = t.video;
    Object.assign(v, { x: Math.round(v.x * sx), y: Math.round(v.y * sy), w: Math.round(v.w * sx), h: Math.round(v.h * sy) });
    for (const x of t.texts) {
      x.x = Math.round(x.x * sx); x.y = Math.round(x.y * sy);
      x.size = Math.max(6, Math.round(x.size * sf)); x.max_width = Math.round((x.max_width || 0) * sx);
    }
    t.canvas_w = nw; t.canvas_h = nh;
  };

  // ---- canvas interaction ----
  const toCanvas = e => {
    const r = canvas.getBoundingClientRect();
    return { x: (e.clientX - r.left) * canvas.width / r.width, y: (e.clientY - r.top) * canvas.height / r.height };
  };
  const snapThreshold = () => E.tpl.canvas_w * 0.012;

  canvas.addEventListener('pointerdown', e => {
    const pt = toCanvas(e);
    const hit = hitTest(ctx, E.tpl, pt, E.sel, SAMPLE_VARS);
    const prevSel = JSON.stringify(E.sel);
    if (!hit) {
      E.sel = null;
    } else if (hit.type === 'handle') {
      E.drag = { mode: 'resize', corner: hit.corner, start: pt, orig: { ...E.tpl.video } };
    } else {
      E.sel = hit.type === 'video' ? { type: 'video' } : { type: 'text', id: hit.id };
      const obj = hit.type === 'video' ? E.tpl.video : E.tpl.texts.find(t => t.id === hit.id);
      E.drag = { mode: 'move', start: pt, orig: { x: obj.x, y: obj.y } };
    }
    if (E.drag) canvas.setPointerCapture(e.pointerId);
    if (JSON.stringify(E.sel) !== prevSel) renderProps();
    render();
  });

  canvas.addEventListener('pointermove', e => {
    const pt = toCanvas(e);
    if (!E.drag) {
      const hit = hitTest(ctx, E.tpl, pt, E.sel, SAMPLE_VARS);
      canvas.style.cursor = !hit ? 'default' : hit.type === 'handle'
        ? (hit.corner === 'nw' || hit.corner === 'se' ? 'nwse-resize' : 'nesw-resize') : 'move';
      return;
    }
    const d = E.drag, dx = pt.x - d.start.x, dy = pt.y - d.start.y;
    E.guides = {};
    if (d.mode === 'move') {
      const obj = E.sel.type === 'video' ? E.tpl.video : selectedText();
      obj.x = Math.round(d.orig.x + dx);
      obj.y = Math.round(d.orig.y + dy);
      // Snap to the horizontal centre - the most common alignment in these layouts.
      const b = E.sel.type === 'video' ? obj : textBounds(ctx, obj, SAMPLE_VARS);
      const off = E.tpl.canvas_w / 2 - (b.x + b.w / 2);
      if (Math.abs(off) < snapThreshold()) { obj.x = Math.round(obj.x + off); E.guides.centerX = true; }
    } else {
      const o = d.orig, min = 32;
      let { x, y, w, h } = o;
      if (d.corner.includes('e')) w = Math.max(min, o.w + dx);
      if (d.corner.includes('w')) w = Math.max(min, o.w - dx);
      if (d.corner.includes('s')) h = Math.max(min, o.h + dy);
      if (d.corner.includes('n')) h = Math.max(min, o.h - dy);
      if (e.shiftKey) h = Math.max(min, w * o.h / o.w);
      if (d.corner.includes('w')) x = o.x + o.w - w;
      if (d.corner.includes('n')) y = o.y + o.h - h;
      Object.assign(E.tpl.video, { x: Math.round(x), y: Math.round(y), w: Math.round(w), h: Math.round(h) });
    }
    syncInputs();
    render();
  });

  const endDrag = () => { E.drag = null; E.guides = {}; render(); };
  canvas.addEventListener('pointerup', endDrag);
  canvas.addEventListener('pointercancel', endDrag);

  // ---- actions ----
  $('#te-back').addEventListener('click', () => renderTemplatesView(main, app));
  $('#te-delete')?.addEventListener('click', async () => {
    if (!(await confirmDialog('حذف القالب', `هتحذف القالب "${E.tpl.name}" نهائيًا؟`, { okText: 'حذف', danger: true }))) return;
    try {
      await api(`api/templates/${encodeURIComponent(E.tpl.id)}`, { method: 'DELETE' });
      await app.reloadTemplates();
      renderTemplatesView(main, app);
    } catch (err) { toast(err.message, 'error'); }
  });
  $('#te-save').addEventListener('click', async () => {
    const btn = $('#te-save');
    if (!E.tpl.name.trim()) { toast('اكتب اسمًا للقالب', 'error'); return; }
    btn.disabled = true;
    btn.textContent = 'جارٍ الحفظ...';
    try {
      await ensureFonts(E.tpl);
      const W = even(E.tpl.canvas_w), H = even(E.tpl.canvas_h);
      const bg = document.createElement('canvas');
      bg.width = W;
      bg.height = H;
      drawBackground(bg.getContext('2d'), E.tpl, E.srcImg);
      const saved = await api('api/templates', {
        method: 'POST',
        body: {
          template: { ...E.tpl, canvas_w: W, canvas_h: H },
          background: bg.toDataURL('image/jpeg', 0.92),
          source_image: E.srcChanged ? E.srcDataUrl : null,
          clear_source: E.clearSource,
        },
      });
      Object.assign(E.tpl, saved);
      Object.assign(E, { srcChanged: false, clearSource: false });
      await app.reloadTemplates();
      toast('تم حفظ القالب ✓', 'success');
      renderTemplatesView(main, app);
    } catch (err) {
      toast(err.message, 'error');
      btn.disabled = false;
      btn.textContent = '💾 حفظ القالب';
    }
  });

  renderProps();
  renderWithFonts();
}
