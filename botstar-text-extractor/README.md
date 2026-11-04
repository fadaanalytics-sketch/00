# استخراج نصوص بلوكات البوت (BotStar / taswikabot)

السكربت `extract-bot-texts.js` بيشتغل من Console المتصفح وانت فاتح محرر البوت، ويطلّع كل النصوص اللي جوة البلوكات (رسائل، أزرار، Quick Replies، كروت...) في ملف `.txt` مرتب باسم كل بلوك.

## الخطوات
1. افتح البوت على **Bot Builder**.
2. اضغط `F12` ← تبويب **Console** (لو كروم منعك من اللصق اكتب `allow pasting` واضغط Enter).
3. الصق محتوى `extract-bot-texts.js` واضغط Enter.
4. اضغط تبويب **Messages** فوق وارجع لـ **Bot Builder** (علشان المحرر يحمّل بيانات البوت تاني والسكربت يلقطها).
5. اكتب `botTexts.save()` ← هينزل `bot-texts.txt` و `bot-raw.json`.

## بدائل
- `botTexts.fromDOM()` ← يقرأ النصوص الظاهرة على الكانفاس مباشرة (من غير ما يحتاج يلقط البيانات).
- يدوي: تبويب **Network** ← فلتر **Fetch/XHR** ← اعمل Refresh ← دوّر (Ctrl+F) على جملة من البوت زي `Ku soo dhawoow`
  ← كليك يمين على الطلب ← **Copy response** ← في الـ Console:
  `botTexts.fromJSON(\`الصق هنا\`)`
