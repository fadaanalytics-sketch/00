/*
 * استخراج نصوص كل البلوكات من كانفاس محرر BotStar / taswikabot مباشرة من الـ DOM
 * ---------------------------------------------------------------------------
 * - مش محتاج Refresh ولا تلقيط Network: كل البلوكات موجودة في الصفحة
 *   (حتى اللي عاملة "Hide Preview" بتبقى موجودة بس مخفية بـ d-none).
 * - الاستخدام: افتح Bot Builder ← F12 ← Console ← الصق الكود ← Enter.
 *   هينزل ملفين: bot-texts.txt (مقروء) و bot-texts.json (منظم).
 */
(function () {
  'use strict';

  // يحوّل محتوى عنصر لنص مع الحفاظ على السطور، والروابط بتتكتب كـ URL
  function toText(el) {
    if (!el) return '';
    const c = el.cloneNode(true);
    c.querySelectorAll('br').forEach(br => br.replaceWith('\n'));
    c.querySelectorAll('a[href]').forEach(a => {
      const t = a.textContent.trim(), h = a.getAttribute('href');
      a.replaceWith(t && t !== h ? t + ' (' + h + ')' : h);
    });
    return c.textContent.replace(/ /g, ' ').replace(/[ \t]+\n/g, '\n').trim();
  }

  const blocks = [];
  document.querySelectorAll('#board-detail-inner sab-message, sab-message').forEach(msg => {
    if (msg.classList.contains('fb-entry')) return;           // "Conversation Entry"
    const nameEl = msg.querySelector('.message-name');
    const block = {
      id: msg.id,
      name: nameEl ? nameEl.textContent.trim() : '(بدون اسم)',
      type: [...msg.classList].find(c => c.startsWith('fb-')) || '',
      x: +msg.dataset.x || 0,
      y: +msg.dataset.y || 0,
      texts: [], buttons: [], quickReplies: [], images: [], cards: []
    };

    // كروت الـ Horizontal List / Generic
    msg.querySelectorAll('sab-element.generic_element').forEach(g => {
      const card = {
        title: toText(g.querySelector('sab-element.title > .element-content')),
        subtitle: toText(g.querySelector('sab-element.subtitle > .element-content')),
        image: (g.querySelector('img') || {}).src || '',
        buttons: [...g.querySelectorAll('sab-element.button > .element-content')].map(toText)
      };
      block.cards.push(card);
    });

    msg.querySelectorAll('sab-element').forEach(el => {
      if (el.closest('sab-element.generic_element')) return;   // اتعالجت فوق
      const content = el.querySelector(':scope > .element-content');
      const cls = el.classList;
      if (cls.contains('quick_reply_item')) block.quickReplies.push(toText(content));
      else if (cls.contains('button')) block.buttons.push(toText(content));
      else if (cls.contains('image')) { const img = el.querySelector('img'); if (img) block.images.push(img.src); }
      else if (cls.contains('text') || cls.contains('title') || cls.contains('subtitle')) {
        const t = toText(content); if (t) block.texts.push(t);
      }
    });
    blocks.push(block);
  });

  if (!blocks.length) {
    console.warn('مفيش بلوكات اتلقت. اتأكد إنك على صفحة Bot Builder والكانفاس ظاهر.');
    return;
  }

  // ترتيب حسب المكان في الكانفاس (من فوق لتحت، ومن الشمال لليمين)
  blocks.sort((a, b) => a.y - b.y || a.x - b.x);

  const line = '='.repeat(50);
  let out = '';
  blocks.forEach((b, i) => {
    out += line + '\n■ ' + (i + 1) + ') ' + b.name + '\n' + line + '\n';
    b.texts.forEach(t => out += t + '\n\n');
    b.cards.forEach((c, j) => {
      out += '[كارت ' + (j + 1) + ']\n';
      if (c.title) out += 'العنوان: ' + c.title + '\n';
      if (c.subtitle) out += 'الوصف: ' + c.subtitle + '\n';
      if (c.image) out += 'الصورة: ' + c.image + '\n';
      if (c.buttons.length) out += 'الأزرار: ' + c.buttons.join(' | ') + '\n';
      out += '\n';
    });
    if (b.images.length) out += 'صور: ' + b.images.join('\n      ') + '\n';
    if (b.buttons.length) out += 'الأزرار: ' + b.buttons.join(' | ') + '\n';
    if (b.quickReplies.length) out += 'Quick Replies: ' + b.quickReplies.join(' | ') + '\n';
    out += '\n';
  });

  function download(name, content, mime) {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([content], { type: mime + ';charset=utf-8' }));
    a.download = name;
    document.body.appendChild(a); a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
  }
  download('bot-texts.txt', '﻿' + out, 'text/plain');
  download('bot-texts.json', JSON.stringify(blocks, null, 2), 'application/json');

  window.botBlocks = blocks;
  console.log(out);
  console.log('%c✔ تم استخراج ' + blocks.length + ' بلوك — البيانات كمان في المتغير botBlocks',
              'color:green;font-weight:bold;font-size:14px');
})();
