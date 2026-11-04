/*
 * استخراج نصوص البلوكات من محرر البوت (BotStar / taswikabot)
 * ----------------------------------------------------------------
 * طريقة الاستخدام:
 *   1) افتح البوت في صفحة Bot Builder.
 *   2) افتح أدوات المطور: F12  ثم تبويب Console.
 *      (لو كروم رفض اللصق، اكتب:  allow pasting  واضغط Enter)
 *   3) الصق هذا الملف كله واضغط Enter.
 *   4) اضغط تبويب "Messages" فوق، ثم ارجع لـ "Bot Builder"
 *      (أو افتح أي Flow تاني من تحت) علشان المحرر يعيد تحميل البيانات.
 *   5) اكتب في الـ Console:   botTexts.save()
 *      هينزل ملفين: bot-texts.txt (النصوص مرتبة لكل بلوك) و bot-raw.json (البيانات الخام).
 *
 *   أوامر إضافية:
 *     botTexts.save()       ← تنزيل النصوص من البيانات اللي اتلقطت
 *     botTexts.fromDOM()    ← بديل: يقرأ النصوص الظاهرة على الشاشة مباشرة
 *     botTexts.fromJSON(x)  ← لو نسخت Response من تبويب Network، مرّره هنا (نص أو object)
 *     botTexts.captured     ← كل الردود اللي اتلقطت
 */
(function () {
  'use strict';
  if (window.botTexts && window.botTexts.__installed) {
    console.log('%cالسكربت متثبت بالفعل. استخدم botTexts.save()', 'color:#5a38fd');
    return;
  }

  const captured = []; // { url, data }

  function remember(url, text) {
    if (!text || typeof text !== 'string') return;
    const t = text.trim();
    if (t[0] !== '{' && t[0] !== '[') return;
    try {
      const data = JSON.parse(t);
      captured.push({ url: String(url), data });
      console.log('%c[botTexts] اتلقط: ' + url + '  (' + t.length + ' حرف)', 'color:gray');
    } catch (e) { /* not JSON */ }
  }

  // ---- اعتراض fetch ----
  const origFetch = window.fetch;
  if (origFetch) {
    window.fetch = function () {
      const p = origFetch.apply(this, arguments);
      const url = arguments[0] && arguments[0].url ? arguments[0].url : arguments[0];
      p.then(r => r.clone().text().then(t => remember(url, t)).catch(() => {})).catch(() => {});
      return p;
    };
  }

  // ---- اعتراض XMLHttpRequest (Angular بيستخدمه) ----
  const origOpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function (method, url) {
    this.__botUrl = url;
    this.addEventListener('load', function () {
      try {
        if (this.responseType === '' || this.responseType === 'text') remember(this.__botUrl, this.responseText);
        else if (this.responseType === 'json' && this.response) captured.push({ url: String(this.__botUrl), data: this.response });
      } catch (e) {}
    });
    return origOpen.apply(this, arguments);
  };

  // ---- أدوات تنظيف النص ----
  const tmp = document.createElement('div');
  function htmlToText(s) {
    if (!/[<&]/.test(s)) return s;
    tmp.innerHTML = s.replace(/<br\s*\/?>/gi, '\n').replace(/<\/(p|div|li|h\d)>/gi, '\n');
    return tmp.textContent;
  }

  const SKIP_KEYS = /^(id|_id|uuid|key|type|kind|icon|color|colou?r|url|src|href|image|image_url|thumbnail|avatar|logo|created.*|updated.*|.*_at|.*At|.*Id|.*_id|position|x|y|width|height|style|class.*|token|hash|version|lang|locale|language|code|script|webhook.*|method|headers?)$/i;

  function looksHuman(s) {
    const t = s.trim();
    if (t.length < 2) return false;
    if (/^(https?:|data:|\/\/|www\.)/i.test(t)) return false;
    if (/^[0-9a-f-]{16,}$/i.test(t)) return false;              // ids / uuids
    if (/^#[0-9a-f]{3,8}$/i.test(t)) return false;              // colors
    if (/^\d+(\.\d+)?(px|%|em)?$/.test(t)) return false;        // numbers
    if (/^[A-Za-z0-9_.:-]+$/.test(t) && !/\s/.test(t) && t.length > 20) return false; // tokens
    if (/^\{\{?[\w.]+\}?\}$/.test(t)) return false;             // pure variable
    return /[\p{L}]/u.test(t);
  }

  // Quill delta: { ops: [ {insert:'...'} ] }
  function deltaText(o) {
    if (o && Array.isArray(o.ops)) return o.ops.map(op => typeof op.insert === 'string' ? op.insert : '').join('');
    return null;
  }

  const LABEL_KEYS = ['name', 'title', 'label', 'block_name', 'blockName'];

  function labelOf(o) {
    for (const k of LABEL_KEYS) if (typeof o[k] === 'string' && o[k].trim()) return o[k].trim();
    return null;
  }

  /**
   * يمشي على JSON كله ويجمع النصوص، ويجمّعها تحت أقرب "بلوك" (object فيه name/title).
   */
  function collect(root) {
    const groups = new Map(); // label -> Set(text)
    const seenObj = new WeakSet();
    function add(label, text) {
      text = htmlToText(text).replace(/ /g, ' ').replace(/\n{3,}/g, '\n\n').trim();
      if (!looksHuman(text)) return;
      if (!groups.has(label)) groups.set(label, new Set());
      groups.get(label).add(text);
    }
    function walk(node, label, key) {
      if (node == null) return;
      if (typeof node === 'string') {
        if (key && SKIP_KEYS.test(key)) return;
        // أحياناً النص نفسه JSON متخزن كسترنج
        const t = node.trim();
        if ((t[0] === '{' || t[0] === '[') && t.length > 20) {
          try { walk(JSON.parse(t), label, key); return; } catch (e) {}
        }
        add(label, node);
        return;
      }
      if (typeof node !== 'object' || seenObj.has(node)) return;
      seenObj.add(node);
      const d = deltaText(node);
      if (d != null) { add(label, d); return; }
      if (Array.isArray(node)) { node.forEach(n => walk(n, label, key)); return; }
      const own = labelOf(node);
      // البلوك = object له اسم وفيه محتوى متداخل
      const isBlock = own && Object.values(node).some(v => v && typeof v === 'object');
      const nextLabel = isBlock ? own : label;
      for (const k of Object.keys(node)) {
        if (isBlock && LABEL_KEYS.includes(k)) continue;
        walk(node[k], nextLabel, k);
      }
    }
    walk(root, '(بدون اسم)', null);
    return groups;
  }

  function groupsToText(groups) {
    let out = '';
    for (const [label, set] of groups) {
      if (!set.size) continue;
      out += '==============================\n■ ' + label + '\n==============================\n';
      for (const t of set) out += t + '\n\n';
    }
    return out;
  }

  function download(name, content, mime) {
    const blob = new Blob([content], { type: (mime || 'text/plain') + ';charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = name;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
  }

  function mergeGroups(list) {
    const all = new Map();
    for (const g of list) for (const [k, s] of g) {
      if (!all.has(k)) all.set(k, new Set());
      s.forEach(t => all.get(k).add(t));
    }
    return all;
  }

  function fromJSON(x) {
    const data = typeof x === 'string' ? JSON.parse(x) : x;
    const g = collect(data);
    const txt = groupsToText(g);
    download('bot-texts.txt', '﻿' + txt);
    console.log(txt);
    return g;
  }

  function save() {
    if (!captured.length) {
      console.warn('[botTexts] لسه مفيش بيانات اتلقطت. اضغط تبويب Messages وارجع لـ Bot Builder (أو افتح Flow تاني)، وبعدين جرّب botTexts.save() تاني.\n' +
                   'أو استخدم botTexts.fromDOM() لقراءة النصوص الظاهرة على الشاشة.');
      return;
    }
    // نتجاهل الردود الصغيرة اللي ملهاش علاقة (إعدادات، يوزر...) ونركز على اللي فيها نصوص
    const groups = captured.map(c => collect(c.data));
    const merged = mergeGroups(groups);
    const txt = groupsToText(merged);
    download('bot-texts.txt', '﻿' + txt);
    download('bot-raw.json', JSON.stringify(captured, null, 2), 'application/json');
    console.log(txt);
    console.log('%c[botTexts] تم: ' + merged.size + ' مجموعة نصوص من ' + captured.length + ' رد.', 'color:green;font-weight:bold');
  }

  /**
   * بديل: قراءة النصوص من عناصر الصفحة نفسها (اللي ظاهرة في الكانفاس).
   * يجمّع النصوص حسب أقرب عنصر متموضع (absolute) = البلوك.
   */
  function fromDOM() {
    // الكانفاس = العنصر اللي فيه أكتر خطوط SVG (الأسهم بين البلوكات)
    let canvas = document.body;
    let best = 0;
    document.querySelectorAll('div').forEach(d => {
      const n = d.querySelectorAll(':scope > svg path, :scope > * > svg path').length;
      if (n > best) { best = n; canvas = d; }
    });
    const groups = new Map();
    const walker = document.createTreeWalker(canvas, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      const t = node.nodeValue.trim();
      if (!t || node.parentElement.closest('script,style,svg')) continue;
      let el = node.parentElement, block = null;
      while (el && el !== canvas) {
        const cs = getComputedStyle(el);
        if (cs.position === 'absolute' && el.offsetWidth > 40) block = el; // أبعد عنصر absolute = البلوك
        el = el.parentElement;
      }
      block = block || canvas;
      if (!groups.has(block)) groups.set(block, []);
      const arr = groups.get(block);
      if (arr[arr.length - 1] !== t) arr.push(t);
    }
    const named = new Map();
    for (const [, arr] of groups) {
      const label = arr[0] || '(بدون اسم)';
      named.set(label + (named.has(label) ? ' #' + named.size : ''), new Set(arr.slice(1)));
    }
    const txt = groupsToText(named);
    download('bot-texts-screen.txt', '﻿' + txt);
    console.log(txt);
    return named;
  }

  window.botTexts = { __installed: true, captured, save, fromDOM, fromJSON, collect };
  console.log('%c[botTexts] جاهز ✔  دلوقتي اضغط "Messages" وارجع لـ "Bot Builder"، وبعدها اكتب: botTexts.save()',
              'color:#5a38fd;font-weight:bold;font-size:14px');
})();
