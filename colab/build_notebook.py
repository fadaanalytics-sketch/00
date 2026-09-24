"""Build the self-contained Colab notebook.

The whole `ava` package (backend + web UI) is embedded in the notebook as a
base64 zip, so the notebook is the only file the user needs - no repo access,
no copying files into Drive. Rebuild after changing anything under colab/ava:

    python colab/build_notebook.py
"""
import base64
import io
import json
import os
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
PACKAGE_DIR = os.path.join(HERE, "ava")
OUTPUT = os.path.join(HERE, "AI_Video_Analyzer.ipynb")
# Fixed timestamps + sorted order keep the zip byte-identical across rebuilds, so the
# committed notebook only changes when the code actually does.
ZIP_TIME = (2020, 1, 1, 0, 0, 0)

INTRO = """<div dir="rtl">

# 🎬 AI Video Analyzer — نسخة كولاب

التفريغ الصوتي والقص والتصدير بيتعمل هنا على كولاب (بكارت شاشة مجاني)، والواجهة بتتفتح في تاب منفصل في المتصفح.
الفيديوهات بتتقرا من جوجل درايف والمقاطع بتتحفظ عليه مباشرة — جهازك بيعرض الواجهة بس.

## أول مرة بس
1. **مفتاح Gemini:** اضغط أيقونة المفتاح 🔑 (Secrets) في الشريط الجانبي ← **Add new secret** ← الاسم `GEMINI_API_KEY` والقيمة مفتاحك من [Google AI Studio](https://aistudio.google.com/app/apikey) ← فعّل **Notebook access**.
   - اختياري: `OPENROUTER_API_KEY` لو عايز تستخدم OpenRouter في التحليل.
2. **كارت الشاشة:** النوت بوك بيطلب T4 GPU تلقائيًا. لو ظهر إنه من غير GPU: **Runtime ← Change runtime type ← T4 GPU ← Save**.

## كل مرة
1. **Runtime ← Run all** (أو `Ctrl+F9`).
2. وافق على صلاحية الوصول لجوجل درايف.
3. استنى لحد ما يظهر رابط **«🚀 افتح الواجهة»** تحت، واضغط عليه.

> خلي تاب كولاب ده مفتوح طول ما انت شغال. الجلسة المجانية بتقفل لو فضلت من غير استخدام فترة، وأقصاها حوالي 12 ساعة —
> كل المشاريع والقوالب محفوظة على الدرايف، فتقدر تكمل من مكانك بتشغيل النوت بوك تاني.

</div>"""

SETTINGS_CELL = """#@title ⚙️ الإعدادات { display-mode: "form" }
#@markdown اسم الفولدر على جوجل درايف اللي هيتحفظ فيه كل حاجة (المشاريع، القوالب، المقاطع المصدّرة):
DRIVE_FOLDER = "AIVideoAnalyzer"  #@param {type:"string"}
PORT = 8000  #@param {type:"integer"}"""

INSTALL_CELL = """#@title 📦 تثبيت المكتبات (حوالي دقيقة في أول كل جلسة)
import importlib, subprocess, sys
r = subprocess.run([sys.executable, "-m", "pip", "install",
                    "faster-whisper>=1.1", "fastapi>=0.110", "uvicorn>=0.29"],
                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
if r.returncode != 0:
    print(r.stdout[-6000:])
    raise RuntimeError("تثبيت المكتبات فشل — ابعت الكلام اللي فوق")
importlib.invalidate_caches()
import fastapi, uvicorn  # the server can't start without these
try:
    import faster_whisper
except Exception as e:  # not fatal: transcription falls back to Gemini
    print("⚠ faster-whisper مش شغالة، التفريغ هيتم بـ Gemini:", e)
print("✓ تم تثبيت المكتبات")"""

EXTRACT_CELL_TEMPLATE = '''#@title 🧩 تجهيز ملفات التطبيق
import base64, io, shutil, zipfile
APP_DIR = "/content/ava_app"
APP_ZIP = """
{payload}
"""
shutil.rmtree(APP_DIR, ignore_errors=True)
with zipfile.ZipFile(io.BytesIO(base64.b64decode("".join(APP_ZIP.split())))) as z:
    z.extractall(APP_DIR)
print("✓ ملفات التطبيق جاهزة")'''

RUN_CELL = """#@title 🚀 تشغيل التطبيق
import json, os, signal, socket, subprocess, sys, time, urllib.request
from google.colab import drive, output, userdata

APP_DIR = "/content/ava_app"
LOG_PATH = "/content/ava_server.log"
PID_PATH = "/content/ava_server.pid"
# Defaults in case the settings cell wasn't run (e.g. only this cell after a restart).
DRIVE_FOLDER = globals().get("DRIVE_FOLDER", "AIVideoAnalyzer")
PORT = int(globals().get("PORT", 8000))

if not os.path.exists(os.path.join(APP_DIR, "ava", "server.py")):
    raise RuntimeError("ملفات التطبيق مش موجودة — شغّل النوت بوك من الأول: Runtime ← Run all")
try:
    import fastapi, uvicorn
except ImportError:
    raise RuntimeError("المكتبات مش متثبتة — شغّل خلية «📦 تثبيت المكتبات» الأول") from None
try:
    drive.mount("/content/drive")
except Exception as e:
    raise RuntimeError("ماقدرناش نوصل لجوجل درايف — شغّل الخلية دي تاني، واختار حسابك ووافق على "
                       "كل الصلاحيات في النافذة اللي بتظهر (لو النافذة ماظهرتش، اسمح بالـ pop-ups)") from e
if not os.path.isdir("/content/drive/MyDrive"):
    raise RuntimeError("جوجل درايف متوصل بس فولدر MyDrive مش ظاهر — Runtime ← Disconnect and delete runtime وشغّل من الأول")

def secret(name):
    try:
        return userdata.get(name) or ""
    except Exception:  # secret missing, or notebook access not granted
        return ""

env = dict(os.environ,
           AVA_MOUNT_ROOT="/content/drive/MyDrive",
           AVA_DATA_DIR=DRIVE_FOLDER.strip() or "AIVideoAnalyzer",
           AVA_WORK_DIR="/content/ava_work",
           GEMINI_API_KEY=secret("GEMINI_API_KEY"),
           OPENROUTER_API_KEY=secret("OPENROUTER_API_KEY"),
           PYTHONUNBUFFERED="1")

# Stop a server left over from a previous run of this cell. The PID lives in a file
# (not a variable) so this still works after a kernel restart; it's checked against
# /proc first because PIDs get reused.
try:
    old_pid = int(open(PID_PATH).read().strip())
    if b"ava.server:app" in open(f"/proc/{old_pid}/cmdline", "rb").read():
        os.kill(old_pid, signal.SIGTERM)
except (OSError, ValueError):
    pass
for _ in range(40):  # wait for the port to be released
    with socket.socket() as s:
        if s.connect_ex(("127.0.0.1", PORT)) != 0:
            break
    time.sleep(0.25)

server = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "ava.server:app", "--host", "0.0.0.0", "--port", str(PORT)],
    cwd=APP_DIR, env=env, stdout=open(LOG_PATH, "w"), stderr=subprocess.STDOUT)
with open(PID_PATH, "w") as f:
    f.write(str(server.pid))

status = None
for _ in range(90):
    if server.poll() is not None:
        break
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/status", timeout=3) as r:
            status = json.load(r)
        break
    except Exception:
        time.sleep(1)

if status is None:
    print(open(LOG_PATH, encoding="utf-8", errors="replace").read()[-4000:])
    raise RuntimeError("السيرفر ما اشتغلش — شوف السجل اللي فوق")

print("✓ السيرفر شغال")
print("• كارت الشاشة:", status["gpu"] or "⚠ مش متاح (التفريغ هيبقى أبطأ) — Runtime ← Change runtime type ← T4 GPU")
print("• التصدير:", "بكارت الشاشة (NVENC)" if status["nvenc"] else "بالمعالج")
print("• Gemini:", "✓" if status["gemini_key"] else "✗ ضيف GEMINI_API_KEY في Secrets وشغّل الخلية دي تاني")
print("• الفولدر على الدرايف:", "My Drive/" + status["data_root"])
print()
try:
    output.serve_kernel_port_as_window(PORT, anchor_text="🚀 افتح الواجهة")
except TypeError:  # older google.colab without anchor_text
    output.serve_kernel_port_as_window(PORT)"""

LOG_CELL = """#@title 🩺 تشخيص المشاكل (لو حصلت مشكلة، شغّل الخلية دي وابعت اللي يظهر)
import importlib.util, os, shutil, sys, traceback

def row(ok, text):
    print(("✓ " if ok else "✗ ") + text)

print("===== آخر خطأ في النوت بوك =====")
err = getattr(sys, "last_exc", None) or getattr(sys, "last_value", None)
print("".join(traceback.format_exception(type(err), err, err.__traceback__))[-4000:] if err else "مفيش")

print("===== الخطوات =====")
row(shutil.which("nvidia-smi") is not None, "كارت الشاشة (GPU)")
for mod in ("fastapi", "uvicorn", "faster_whisper"):
    row(importlib.util.find_spec(mod) is not None, "مكتبة " + mod)
row(os.path.exists("/content/ava_app/ava/server.py"), "ملفات التطبيق")
row(os.path.isdir("/content/drive/MyDrive"), "جوجل درايف متوصل")
alive = False
try:
    pid = int(open("/content/ava_server.pid").read().strip())
    alive = b"ava.server:app" in open(f"/proc/{pid}/cmdline", "rb").read()
except (OSError, ValueError):
    pass
row(alive, "السيرفر شغال")

print("===== سجل السيرفر =====")
if os.path.exists("/content/ava_server.log"):
    print(open("/content/ava_server.log", encoding="utf-8", errors="replace").read()[-8000:] or "(فاضي)")
else:
    print("السيرفر ما اتشغلش خالص — المشكلة في خلية قبل «🚀 تشغيل التطبيق» (أول خلية فيها علامة حمرا)")"""


def package_zip_b64() -> str:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(PACKAGE_DIR):
            dirs[:] = sorted(d for d in dirs if d != "__pycache__")
            for name in sorted(files):
                if name.endswith(".pyc"):
                    continue
                full = os.path.join(root, name)
                info = zipfile.ZipInfo(os.path.relpath(full, HERE).replace(os.sep, "/"), date_time=ZIP_TIME)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                with open(full, "rb") as f:
                    z.writestr(info, f.read())
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _source(text: str) -> list[str]:
    lines = text.split("\n")
    return [line + "\n" for line in lines[:-1]] + [lines[-1]]


def _code(text: str) -> dict:
    return {"cell_type": "code", "execution_count": None, "metadata": {"cellView": "form"},
            "outputs": [], "source": _source(text)}


def build() -> dict:
    b64 = package_zip_b64()
    payload = "\n".join(b64[i:i + 100] for i in range(0, len(b64), 100))
    return {
        "nbformat": 4,
        "nbformat_minor": 0,
        "metadata": {
            "colab": {"provenance": [], "gpuType": "T4", "name": "AI_Video_Analyzer.ipynb"},
            "accelerator": "GPU",
            "kernelspec": {"name": "python3", "display_name": "Python 3"},
            "language_info": {"name": "python"},
        },
        "cells": [
            {"cell_type": "markdown", "metadata": {}, "source": _source(INTRO)},
            _code(SETTINGS_CELL),
            _code(INSTALL_CELL),
            _code(EXTRACT_CELL_TEMPLATE.format(payload=payload)),
            _code(RUN_CELL),
            _code(LOG_CELL),
        ],
    }


def render() -> str:
    return json.dumps(build(), ensure_ascii=False, indent=1) + "\n"


def main():
    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(render())
    print(f"wrote {OUTPUT}")


if __name__ == "__main__":
    main()
