/*
 * مساعد إدخال الترجمة الصومالية في محرر BotStar / taswikabot
 * --------------------------------------------------------------
 * 1) افتح Bot Builder ← F12 ← Console ← الصق الملف ده كله ← Enter.
 * 2) هتظهر لوحة صغيرة تحت على الشمال.
 * 3) دوس على أي عنصر في الكانفاس (نص / زر / Quick Reply / عنوان كارت / اسم البلوك):
 *    - اللوحة هتعرض الترجمة بتاعته، وتنسخها في الـ Clipboard تلقائياً.
 * 4) في لوحة الخصائص على اليمين: دوس جوة الحقل ← Ctrl+A ← Ctrl+V
 *    (أو دوس جوة الحقل وبعدين زرار "⬇ إدخال في الحقل" في اللوحة).
 * 5) المحرر بيحفظ لوحده (هتشوف Saved فوق)، أو دوس حفظ.
 */
(function () {
  'use strict';
  const T = {"labels": {"Profil Akademi": "Nagu Saabsan", "Cara Mendaftar": "Is-diiwaangelinta", "Hubungi Kami": "Nala Soo Xiriir", "Cara Belajar": "Sida Wax Loo Barto", "Cara Ujian": "Nidaamka Imtixaanka", "Cara mengunduh serti": "Soo Dejinta Shahaado", "Sertifikat Akademi": "Shahaadooyinka", "Kurikulum Pembelajar": "Manhajka Waxbarasho", "Masuk untuk Siswa Te": "Soo Galidda Ardayda", "Lupa Kata Sandi": "Ilowday Erayga Sirta", "Cara mengetahui stat": "Ma La I Aqbalay?", "Ku Saabsan Akadeemiy": "Nagu Saabsan", "Sida Loo Isdiiwaange": "Is-diiwaangelinta", "Nala Soo Xiriir": "Nala Soo Xiriir", "App-ka Akadeemiyada": "App-ka Akadeemiyada"}, "blocks": {"Menu Utama": {"name": "Menu Utama", "cardTitle": "Ku soo dhawoow Akadeemiyada Rushd.", "cardSubtitle": "Fadlan dooro adeegga aad u baahan tahay adigoo gujinaya badhamada hoose."}, "Komentar": {"name": "Komentar", "text": "Ku soo dhawoow Akadeemiyada Rushd, {first_name} ✨\n\nWaxaan dhammaan faahfaahinta kuugu soo dirnay Messenger-ka. Waxaan diyaar u nahay inaan halkaas kuugu adeegno, kana jawaabno dhammaan su'aalahaaga. 🤍\n\nAkadeemiyada Rushd waa madal waxbarasho oo loogu talagalay in ardayda Soomaaliyeed lagu baro culuumta shareecada Islaamka, iyadoo loo marayo barnaamijyo iyo koorsooyin si nidaamsan loo diyaariyey, oo ay ardaydu si fudud u fahmi karaan.\n\nAkadeemiyadu waxay ardayda siisaa fursad ay ku kororsadaan cilmiga diinta, kuna bartaan caqiidada, tawxiidka iyo fiqiga, si ay diintooda si sax ah u fahmaan, ugana dhaqmaan cilmi iyo garasho sugan.\n\nMar walba waxaan ku faraxsanahay inaan kuu adeegno. 💫\n\nWaxaan kugu sugaynaa Messenger-ka si aan uga jawaabno dhammaan su'aalahaaga. ✨"}, "Cara Belajar": {"name": "Sida Wax Loo Barto", "text": "Sida wax loo barto ee Akadeemiyada Rushd:\n\n🗓️ Waxbarashadu waxay bilaabanaysaa 3-da Janaayo 2027.\n💥 Waxbarashadu waxay kuu bilaabanaysaa isla marka aad dhammaystirto is-diiwaangelinta.\n🔗 https://akadeemiyarushd.com/register\n🔸 Gal bogga barnaamijyada ama dibloomayaasha, kadibna dooro barnaamijka aad rabto inaad barato iyo maaddada aad ka bilaabayso.\n🔗 https://akadeemiyarushd.com/diplomas\n🔸 Casharrada waxaad ku baranaysaa muuqaallo waxbarasho iyo qoraallo cilmiyeed.\n🔸 Kadib waxaad galaysaa imtixaanka, waxaadna isla markiiba soo dejisan kartaa shahaadada marka aad ku guulaysato."}, "Cara Ujian": {"name": "Nidaamka Imtixaanka", "text": "📝 Nidaamka imtixaanka:\n\n🔸 Imtixaanka gal kadib markaad daawato casharka oo aad eegto tixraacyada (ugu yaraan 80% maaddada).\n🔸 Badhanka \"Bilow Imtixaanka\" wuxuu ku yaal cashar kasta.\n🔸 Cashar kasta 2 fursadood ayaad leedahay; dhibcaha ugu sarreeya ayaa la qaadanayaa.\n🔸 Isku dayada u dhexeysii 120 daqiiqo oo dib-u-akhris ah.\n🔸 Furitaanka imtixaanka waa isku day, xitaa haddii la xiro.\n🔸 Dhammee ka hor inta waqtigu dhammaan, haddii kale wuu xirmayaa.\n🔸 Natiijada ka eeg \"Koorsooyinkeyga & Shahaadooyinkeyga\".\n🔸 Haddii aad 2 jeer ku dhacdo, waad sii wadi kartaa; fursad 3aad ayaad helaysaa dhammaadka (ugu badnaan 3 cashar)."}, "Cara mengunduh sertifikat": {"name": "Soo Dejinta Shahaadada", "text": "📌 Sida loo soo dejiyo shahaadada koorsada:\n\n⭐️ Kadib markaad gasho akoonkaaga ee bogga Akadeemiyada Rushd, dooro \"Koorsooyinkeyga & Shahaadooyinkeyga\".\n⭐️ Dooro dibloomada aad rabto inaad aragto natiijadeeda iyo shahaadadeeda.\n⭐️ Guji \"Natiijooyinka iyo shahaadooyinka\".\n⭐️ Dooro koorsada aad rabto shahaadadeeda.\n⭐️ Guji \"Soo Deji Shahaadada\".\n⭐️ Qiimaynta koorsada ayaa soo baxaysa; dooro heerka aad ku qanacsan tahay, kadib guji \"Waan Oggolahay\".\n⭐️ Shahaadadu waxay ku soo baxaysaa laba qaab: sawir iyo PDF — dooro midka kuu habboon oo soo deji.\n\n🔗 https://akadeemiyarushd.com/my-courses-certificates"}, "Masuk untuk Siswa Terdaftar": {"name": "Soo Galidda Ardayda", "text": "🔑 Sida ay u soo galaan ardayda horey isugu diiwaangeliyey Akadeemiyada Rushd:\n1️⃣ Fur bogga soo galidda adigoo isticmaalaya xiriirkan:\nhttps://akadeemiyarushd.com/login\n2️⃣ Geli iimaylka aad isku diiwaangelisay.\n3️⃣ Geli erayga sirta ah ee aad hore u samaysay.\n4️⃣ Daar doorashada \"I xasuuso\" si nidaamku u kaydiyo xogtaada soo galidda.\n5️⃣ Guji badhanka \"Gal\" si aad akoonkaaga u gasho."}, "Lupa Kata Sandi": {"name": "Ilowday Erayga Sirta", "text": "Haddii aad ilowday erayga sirta ah, fadlan raac tallaabooyinkan:\n1️⃣ Bogga soo galidda ku guji \"Ma ilowday erayga sirta?\": https://akadeemiyarushd.com/login\n2️⃣ Nidaamku wuxuu iimaylkaaga kuugu soo dirayaa farriin aad ku bedeli karto erayga sirta ah.\n📨 Hubi in iimaylka aad gelisay uu sax yahay, oo eeg sanduuqa farriimaha (Inbox) ama galka Spam-ka.\nHaddii farriintu ku soo gaari weydo, fadlan la xiriir kooxda taageerada ee Telegram:\nhttps://t.me/AkadeemiyadaRushd"}, "Sertifikat Akademi": {"name": "Shahaadooyinka", "text": "📜 Shahaadooyinka Akadeemiyada Rushd:\n\n✅ Shahaadada dhammaystirka koorsada\n✅ Shahaadada dhammaystirka dibloomada\n✅ Shahaadada dhammaystirka simistarka\n✅ Shahaadada qalinjebinta\n✅ Kashfiga dhibcaha ardayga (Transcript)\n\n👈 Faahfaahinta shahaadooyinka ka eeg halkan:\nhttps://akadeemiyarushd.com/info/shahaadada\n✍️ Hadda isdiiwaangeli:\nhttps://akadeemiyarushd.com/register\n\n🔹 Si aad u barato akadeemiyada iyo barnaamijyada dibloomada:\nhttps://akadeemiyarushd.com/info/nagu-saabsan"}, "Profil Akademi": {"name": "Nagu Saabsan", "text": "Akadeemiyada Rushd waa madal waxbarasho oo online ah, loogu talagalay in bulshada Soomaaliyeed lagu baro culuumta shareecada Islaamka, iyadoo la raacayo manhajka Ahlus-Sunnah wal-Jamaacah.\n\nWaxay bixisaa koorsooyin diini ah oo si fudud oo nidaamsan loo diyaariyey, gaar ahaan caqiidada, tawxiidka iyo cibaadada, si ardaygu u helo cilmi sugan oo uu nolol maalmeedkiisa ku dabaqi karo.\n\nCasharrada waxaa la socda imtixaanno lagu qiimeeyo fahamka ardayga.\n\nArdayda si guul leh u dhammaystirta barnaamijyada waxay helaan shahaado rasmi ah. 🎓"}, "Cara Mendaftar": {"name": "Is-diiwaangelinta", "text": "📚 Sida loo isdiiwaangeliyo Akadeemiyada Rushd\n\nKu bilow safarkaaga waxbarasho tallaabooyinkan:\n\n1️⃣ Fur bogga diiwaangelinta:\nhttps://akadeemiyarushd.com/register\n\n2️⃣ Qor magacaaga oo buuxa, sida aad rabto inuu shahaadada uga muuqdo.\n\n3️⃣ Geli iimayl sax ah oo aad isticmaasho.\n\n4️⃣ Samee furaha sirta ah, dabadeed mar kale geli si aad u xaqiijiso.\n\n5️⃣ Riix «Isdiiwaangeli Hadda».\n\n✅ Si taxaddar leh u hubi magacaaga iyo iimaylkaaga ka hor intaadan dirin.\n\n🛟 Haddii aad dhibaato la kulanto, la xiriir taageerada:\nhttps://t.me/AkadeemiyadaRushd"}, "Cara mengetahui status diterima?": {"name": "Ma La I Aqbalay?", "text": "Sideen ku ogaan karaa in la i diiwaangeliyey oo la i aqbalay?\n\nMarka is-diiwaangelintu guulaysato, waxaad bogga ka helaysaa farriin soo dhaweyn ah, magacaaguna wuxuu ka soo muuqanayaa xagga sare ee bogga akoonkaaga Akadeemiyada.\n\n💬 Su'aalo ama caawimaad, fadlan la xiriir Taageerada Farsamada:\nhttps://t.me/AkadeemiyadaRushd"}, "Aplikasi Akademi Bina Al-Muslim": {"name": "App-ka Akadeemiyada", "text": "Ma rabtaa inaad casharrada u hesho si fudud oo habaysan? 📲✨\n\nApp-ka Akadeemiyada Rushd wuxuu hal meel isugu keeni doonaa casharradaada, qorshahaaga iyo horumarkaaga, si aad u hesho waxbarasho raaxo leh.\n\n⏳ App-ku weli lama soo saarin — dhowaan ayuu soo bixi doonaa, insha Allaah!\n\nInta ka horraysa, casharrada waxaad ka heli kartaa bogga Akadeemiyada:\nhttps://akadeemiyarushd.com/"}, "Kurikulum Pembelajaran": {"name": "Manhajka Waxbarashada", "text": "📚 Manhajka Waxbarashada – Akadeemiyada Rushd\n\nManhaj dhammaystiran oo ka kooban afar simistar:\n1️⃣ Dhisidda Aasaaska iyo Aqoonsiga\n2️⃣ Dhisidda Aqoonta iyo Ittibaaca\n3️⃣ Qoto-dheeraynta iyo Xoojinta Cilmiga\n4️⃣ Adkaysiga Nafta iyo Xaqiiqada Nolosha\n\nWaxaan kaa caawinaynaa inaad dareen diineed u beddesho cibaado ku dhisan cilmi iyo baseero, si aad u hesho farxadda adduunka iyo aakhirada.\n\nCasharrada waxaa loo soo bandhigaa si kooban, waxaana isla markiiba la socda imtixaan elektaroonig ah oo lagu cabbiro fahamkaaga.\n\n📘 Barnaamijyada: https://akadeemiyarushd.com/info/nagu-saabsan\n📮 Caawinaad: https://t.me/AkadeemiyadaRushd"}, "Hubungi Kami": {"name": "Nala Soo Xiriir", "text": "📩 Ma qabtaa su'aal ama ma u baahan tahay caawimaad?\n\nKooxda Akadeemiyada Rushd waxay diyaar u tahay inay kaa caawiso wixii su'aalo ama dhibaatooyin ah ee aad qabto. 🤍\n\nWaxaad nagala soo xiriiri kartaa:\n\n📞 Telegram (Taageerada Ardayda):\nhttps://t.me/AkadeemiyadaRushd\n\n📱 WhatsApp:\n+252 61 0456633\n\n📧 Email:\nakadeemiyarushd@gmail.com\n\n🌐 Bogga Rasmiga ah ee Akadeemiyada:\nhttps://akadeemiyarushd.com/\n\n✨ Waxaan ku faraxsanahay inaan kuu adeegno!"}}};
  if (window.__soHelper) { window.__soHelper.remove(); }

  // lookup بالاسم القديم أو الجديد (علشان لو غيرت اسم البلوك قبل النص)
  const byName = {};
  Object.entries(T.blocks).forEach(([old, b]) => { byName[old] = b; byName[b.name] = b; });
  const labelNew = new Set(Object.values(T.labels));

  // ---------- اللوحة ----------
  const box = document.createElement('div');
  box.dir = 'ltr';
  box.style.cssText = 'position:fixed;left:12px;bottom:12px;z-index:2147483647;width:380px;max-height:60vh;' +
    'display:flex;flex-direction:column;background:#fff;border:2px solid #5a38fd;border-radius:10px;' +
    'box-shadow:0 6px 24px rgba(0,0,0,.25);font:13px/1.45 system-ui,sans-serif;color:#222';
  box.innerHTML =
    '<div style="background:#5a38fd;color:#fff;padding:6px 10px;display:flex;justify-content:space-between;align-items:center">' +
      '<b>🇸🇴 Somali helper</b><span><span id="so-count"></span> <button id="so-x" style="border:0;background:none;color:#fff;font-size:16px;cursor:pointer">×</button></span></div>' +
    '<div id="so-what" style="padding:6px 10px;color:#666;border-bottom:1px solid #eee">دوس على عنصر في الكانفاس…</div>' +
    '<textarea id="so-text" style="flex:1;min-height:140px;margin:6px 10px;border:1px solid #ccc;border-radius:6px;padding:6px;font:13px/1.45 system-ui;resize:vertical"></textarea>' +
    '<div style="display:flex;gap:6px;padding:0 10px 10px">' +
      '<button id="so-copy" style="flex:1;padding:6px;border:1px solid #5a38fd;background:#fff;color:#5a38fd;border-radius:6px;cursor:pointer">📋 نسخ</button>' +
      '<button id="so-ins" style="flex:1;padding:6px;border:0;background:#5a38fd;color:#fff;border-radius:6px;cursor:pointer">⬇ إدخال في الحقل</button>' +
    '</div>';
  document.body.appendChild(box);
  window.__soHelper = box;
  const $ = s => box.querySelector(s);
  const ta = $('#so-text'), what = $('#so-what');
  $('#so-x').onclick = () => box.remove();

  let done = new Set();
  try { done = new Set(JSON.parse(localStorage.getItem('soHelperDone') || '[]')); } catch (e) {}
  const total = Object.values(T.blocks).reduce((n, b) => n + (b.text ? 1 : 0) + 1 + (b.cardTitle ? 2 : 0), 0);
  const updCount = () => { $('#so-count').textContent = done.size + '/' + total; };
  updCount();
  let currentKey = null;

  function copy(text) {
    if (navigator.clipboard) navigator.clipboard.writeText(text).catch(() => {});
  }
  function show(label, text, key, already) {
    what.innerHTML = label + (already ? ' <b style="color:green">✔ مترجم بالفعل</b>' : '');
    ta.value = text;
    currentKey = key;
    copy(text);
  }

  // ---------- تتبع آخر حقل دوست فيه (في لوحة الخصائص) ----------
  let lastField = null;
  document.addEventListener('focusin', e => {
    const el = e.target;
    if (box.contains(el) || el.closest('#board-detail-inner')) return;
    if (el.matches('input[type=text], input:not([type]), textarea, [contenteditable=""], [contenteditable=true]')) lastField = el;
  }, true);

  function insert() {
    const text = ta.value;
    const f = lastField;
    if (!f || !document.contains(f)) { alert('دوس الأول جوة الحقل في لوحة الخصائص (يمين)، وبعدين دوس إدخال.\nأو استخدم Ctrl+A ثم Ctrl+V.'); return; }
    const qc = f.closest('.ql-container');
    if (qc && qc.__quill) {                         // محرر Quill
      qc.__quill.setText(text, 'user');
      qc.__quill.blur && qc.__quill.blur();
    } else {
      f.focus();
      if (f.isContentEditable) { const r = document.createRange(); r.selectNodeContents(f); const s = getSelection(); s.removeAllRanges(); s.addRange(r); }
      else f.select();
      if (!document.execCommand('insertText', false, text)) {
        const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(f), 'value').set;
        setter.call(f, text);
        f.dispatchEvent(new Event('input', { bubbles: true }));
      }
      f.dispatchEvent(new Event('change', { bubbles: true }));
      f.dispatchEvent(new Event('blur', { bubbles: true }));
    }
    if (currentKey) { done.add(currentKey); try { localStorage.setItem('soHelperDone', JSON.stringify([...done])); } catch (e) {} updCount(); }
    what.innerHTML += ' <b style="color:green">⬅ اتحط</b>';
  }
  $('#so-copy').onclick = () => { copy(ta.value); what.innerHTML += ' <b style="color:#5a38fd">نُسخ</b>'; };
  $('#so-ins').onclick = insert;

  // ---------- لما تدوس على عنصر في الكانفاس ----------
  document.addEventListener('click', e => {
    const msg = e.target.closest && e.target.closest('sab-message');
    if (!msg || box.contains(e.target)) return;
    const nameEl = msg.querySelector('.message-name');
    const bname = nameEl ? nameEl.textContent.trim() : '';
    const b = byName[bname];
    const el = e.target.closest('sab-element');
    const content = el && el.querySelector(':scope > .element-content');
    const cur = content ? content.textContent.trim() : '';

    if (el && (el.classList.contains('button') || el.classList.contains('quick_reply_item'))) {
      const kind = el.classList.contains('button') ? 'زر' : 'Quick Reply';
      if (T.labels[cur]) return show(kind + ': <b>' + cur + '</b>', T.labels[cur], 'L:' + bname + ':' + cur, cur === T.labels[cur]);
      if (labelNew.has(cur)) return show(kind + ': <b>' + cur + '</b>', cur, null, true);
      return show(kind + ': <b>' + cur + '</b> — مفيش ترجمة', '', null);
    }
    if (!b) return show('بلوك: <b>' + bname + '</b> — مش في ملف الترجمة', '', null);
    if (el && el.classList.contains('title') && b.cardTitle) return show(bname + ' ← عنوان الكارت', b.cardTitle, 'CT:' + bname, cur === b.cardTitle);
    if (el && el.classList.contains('subtitle') && b.cardSubtitle) return show(bname + ' ← وصف الكارت', b.cardSubtitle, 'CS:' + bname, cur === b.cardSubtitle);
    if (el && el.classList.contains('text') && b.text) return show(bname + ' ← النص', b.text, 'T:' + bname, false);
    if (e.target.closest('.card-header')) return show('اسم البلوك: <b>' + bname + '</b>', b.name, 'N:' + bname, bname === b.name);
    if (b.text) return show(bname + ' ← النص', b.text, 'T:' + bname, false);
  }, true);

  console.log('%c🇸🇴 Somali helper جاهز — دوس على أي عنصر في الكانفاس', 'color:#5a38fd;font-weight:bold;font-size:14px');
})();
