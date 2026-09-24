// Pure canvas drawing for templates. The editor, thumbnails and the per-clip
// overlay PNGs sent to the server all go through these same functions, so the
// editor preview is exactly what gets burned into the exported video. Text is
// rendered here (not by ffmpeg) because the browser shapes Arabic correctly.

export const FONTS = ['Cairo', 'Tajawal', 'Almarai', 'Noto Kufi Arabic', 'Amiri', 'Readex Pro'];
export const SAMPLE_VARS = { title: 'عنوان المقطع يظهر هنا', n: 1 };

export const even = n => { const r = Math.round(n); return r % 2 ? r + 1 : r; };

export function fontString(t) {
  return `${t.weight || 700} ${Math.max(1, t.size || 1)}px "${t.font || 'Cairo'}", "Cairo", sans-serif`;
}

export function applyVars(text, vars) {
  return String(text ?? '').replace(/\{(title|n)\}/g, (m, k) => (vars && vars[k] != null ? String(vars[k]) : m));
}

/** Load the web fonts (including their Arabic unicode-range subset) before drawing. */
export async function ensureFonts(tpl, extraTexts = []) {
  const sample = ['أبجد هوز abc 123', ...extraTexts, ...(tpl.texts || []).map(t => t.text || '')].join(' ');
  const specs = new Set((tpl.texts || []).map(fontString));
  await Promise.all([...specs].map(f => document.fonts.load(f, sample).catch(() => null)));
}

export function loadImage(src) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error('تعذر تحميل الصورة'));
    img.src = src;
  });
}

function roundRectPath(ctx, x, y, w, h, r) {
  r = Math.max(0, Math.min(r, w / 2, h / 2));
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

export function layoutText(ctx, t, vars) {
  ctx.save();
  ctx.font = fontString(t);
  ctx.direction = 'rtl';
  const maxW = t.max_width > 0 ? t.max_width : Infinity;
  const lines = [];
  for (const para of applyVars(t.text, vars).split('\n')) {
    const words = para.split(/\s+/).filter(Boolean);
    if (!words.length) { lines.push(''); continue; }
    let line = words[0];
    for (const w of words.slice(1)) {
      const test = `${line} ${w}`;
      if (ctx.measureText(test).width <= maxW) line = test;
      else { lines.push(line); line = w; }
    }
    lines.push(line);
  }
  const widths = lines.map(l => ctx.measureText(l).width);
  ctx.restore();
  const lh = (t.size || 1) * (t.line_height || 1.3);
  const w = Math.max(1, ...widths);
  const h = Math.max(lh, lines.length * lh);
  const align = t.align || 'center';
  const left = align === 'center' ? t.x - w / 2 : align === 'right' ? t.x - w : t.x;
  const pad = t.box_color ? t.size * 0.35 : 0;
  return {
    lines, lh, align,
    rect: { x: left, y: t.y, w, h },
    box: { x: left - pad, y: t.y - pad, w: w + pad * 2, h: h + pad * 2 },
  };
}

export function textBounds(ctx, t, vars) {
  const L = layoutText(ctx, t, vars);
  return t.box_color ? L.box : L.rect;
}

export function drawTexts(ctx, tpl, vars) {
  for (const t of tpl.texts || []) {
    const L = layoutText(ctx, t, vars);
    ctx.save();
    if (t.box_color) {
      ctx.fillStyle = t.box_color;
      roundRectPath(ctx, L.box.x, L.box.y, L.box.w, L.box.h, t.size * 0.3);
      ctx.fill();
    }
    ctx.font = fontString(t);
    ctx.direction = 'rtl';
    ctx.textAlign = L.align;
    ctx.textBaseline = 'middle';
    L.lines.forEach((line, i) => {
      const y = t.y + i * L.lh + L.lh / 2;
      if (t.stroke_width > 0) {
        ctx.lineJoin = 'round';
        ctx.miterLimit = 2;
        ctx.lineWidth = t.stroke_width * 2;
        ctx.strokeStyle = t.stroke_color || '#000000';
        ctx.strokeText(line, t.x, y);
      }
      ctx.fillStyle = t.color || '#ffffff';
      ctx.fillText(line, t.x, y);
    });
    ctx.restore();
  }
}

function drawImageFit(ctx, img, w, h, fit) {
  if (fit === 'stretch') { ctx.drawImage(img, 0, 0, w, h); return; }
  const iw = img.naturalWidth || img.width, ih = img.naturalHeight || img.height;
  const s = fit === 'contain' ? Math.min(w / iw, h / ih) : Math.max(w / iw, h / ih);
  const dw = iw * s, dh = ih * s;
  ctx.drawImage(img, (w - dw) / 2, (h - dh) / 2, dw, dh);
}

export function drawBackground(ctx, tpl, img) {
  const W = even(tpl.canvas_w), H = even(tpl.canvas_h);
  ctx.fillStyle = tpl.bg_color || '#000000';
  ctx.fillRect(0, 0, W, H);
  if (img) drawImageFit(ctx, img, W, H, tpl.bg_fit || 'cover');
}

export function drawVideoPlaceholder(ctx, tpl, highlight = false) {
  const v = tpl.video;
  const s = Math.max(tpl.canvas_w, tpl.canvas_h);
  ctx.save();
  ctx.fillStyle = highlight ? 'rgba(59,109,240,0.38)' : 'rgba(59,109,240,0.28)';
  ctx.fillRect(v.x, v.y, v.w, v.h);
  ctx.setLineDash([s / 90, s / 140]);
  ctx.lineWidth = Math.max(2, s / 450);
  ctx.strokeStyle = 'rgba(255,255,255,0.9)';
  ctx.strokeRect(v.x, v.y, v.w, v.h);
  ctx.setLineDash([]);
  const cx = v.x + v.w / 2, cy = v.y + v.h / 2, r = Math.max(8, Math.min(v.w, v.h) * 0.1);
  ctx.fillStyle = 'rgba(255,255,255,0.92)';
  ctx.beginPath();
  ctx.moveTo(cx + r * 0.9, cy - r * 0.35);
  ctx.lineTo(cx - r * 0.5, cy - r * 1.05);
  ctx.lineTo(cx - r * 0.5, cy + r * 0.35);
  ctx.closePath();
  ctx.fill();
  ctx.font = `700 ${Math.max(12, Math.min(v.w, v.h) * 0.065)}px Cairo, sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  const label = v.fit === 'contain' ? 'الفيديو (احتواء)' : v.fit === 'stretch' ? 'الفيديو (تمديد)' : 'الفيديو (تغطية)';
  ctx.fillText(label, cx, cy + r * 0.7);
  ctx.restore();
}

export const handleSize = tpl => Math.max(tpl.canvas_w, tpl.canvas_h) / 55;

export function videoCorners(v) {
  return [['nw', v.x, v.y], ['ne', v.x + v.w, v.y], ['sw', v.x, v.y + v.h], ['se', v.x + v.w, v.y + v.h]];
}

export function drawSelection(ctx, tpl, sel, vars, guides = {}) {
  const s = Math.max(tpl.canvas_w, tpl.canvas_h);
  const hs = handleSize(tpl);
  ctx.save();
  ctx.lineWidth = Math.max(2, s / 360);
  ctx.strokeStyle = '#3B6DF0';
  if (sel?.type === 'video') {
    const v = tpl.video;
    ctx.strokeRect(v.x, v.y, v.w, v.h);
    for (const [, x, y] of videoCorners(v)) {
      ctx.fillStyle = '#ffffff';
      ctx.fillRect(x - hs / 2, y - hs / 2, hs, hs);
      ctx.strokeRect(x - hs / 2, y - hs / 2, hs, hs);
    }
  } else if (sel?.type === 'text') {
    const t = (tpl.texts || []).find(x => x.id === sel.id);
    if (t) {
      const b = textBounds(ctx, t, vars);
      const m = s / 200;
      ctx.setLineDash([s / 120, s / 200]);
      ctx.strokeRect(b.x - m, b.y - m, b.w + 2 * m, b.h + 2 * m);
    }
  }
  if (guides.centerX) {
    ctx.setLineDash([s / 100, s / 150]);
    ctx.strokeStyle = '#EC4899';
    ctx.beginPath();
    ctx.moveTo(tpl.canvas_w / 2, 0);
    ctx.lineTo(tpl.canvas_w / 2, tpl.canvas_h);
    ctx.stroke();
  }
  ctx.restore();
}

function inside(pt, r, margin = 0) {
  return pt.x >= r.x - margin && pt.x <= r.x + r.w + margin && pt.y >= r.y - margin && pt.y <= r.y + r.h + margin;
}

/** What's under the pointer: a resize handle of the selected video, a text, or the video. */
export function hitTest(ctx, tpl, pt, sel, vars) {
  const hs = handleSize(tpl) * 1.5;
  if (sel?.type === 'video') {
    for (const [corner, x, y] of videoCorners(tpl.video)) {
      if (Math.abs(pt.x - x) <= hs && Math.abs(pt.y - y) <= hs) return { type: 'handle', corner };
    }
  }
  const texts = tpl.texts || [];
  for (let i = texts.length - 1; i >= 0; i--) {
    if (inside(pt, textBounds(ctx, texts[i], vars), hs / 2)) return { type: 'text', id: texts[i].id };
  }
  if (inside(pt, tpl.video)) return { type: 'video' };
  return null;
}

export async function drawTemplateThumb(canvas, tpl, vars, { maxW = 220, backgroundUrl = null } = {}) {
  const W = even(tpl.canvas_w), H = even(tpl.canvas_h);
  const scale = maxW / W;
  let img = null;
  if (backgroundUrl) img = await loadImage(backgroundUrl).catch(() => null);
  await ensureFonts(tpl, [vars?.title || '']);
  canvas.width = Math.round(W * scale);
  canvas.height = Math.round(H * scale);
  const ctx = canvas.getContext('2d');
  ctx.setTransform(scale, 0, 0, scale, 0, 0);
  if (img) ctx.drawImage(img, 0, 0, W, H);
  else drawBackground(ctx, tpl, null);
  drawVideoPlaceholder(ctx, tpl);
  drawTexts(ctx, tpl, vars);
}

/** One transparent PNG per clip with that clip's texts ({title}/{n} filled in). */
export async function renderOverlays(tpl, clips) {
  if (!(tpl.texts || []).length) return {};
  await ensureFonts(tpl, clips.map(c => c.name));
  const W = even(tpl.canvas_w), H = even(tpl.canvas_h);
  const canvas = document.createElement('canvas');
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext('2d');
  const out = {};
  clips.forEach((clip, i) => {
    ctx.clearRect(0, 0, W, H);
    drawTexts(ctx, tpl, { title: clip.name, n: i + 1 });
    out[clip.id] = canvas.toDataURL('image/png');
  });
  return out;
}
