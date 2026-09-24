import base64
import importlib.util
import io
import json
import os
import zipfile

COLAB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "colab"))


def load_builder():
    spec = importlib.util.spec_from_file_location("build_notebook", os.path.join(COLAB_DIR, "build_notebook.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def embedded_zip(nb: dict) -> zipfile.ZipFile:
    src = next("".join(c["source"]) for c in nb["cells"] if "APP_ZIP" in "".join(c["source"]))
    blob = src.split('APP_ZIP = """')[1].split('"""')[0]
    return zipfile.ZipFile(io.BytesIO(base64.b64decode("".join(blob.split()))))


def test_committed_notebook_is_up_to_date():
    """The notebook embeds colab/ava; editing the code without rebuilding would ship
    stale code to Colab. Fix with: python colab/build_notebook.py"""
    builder = load_builder()
    with open(builder.OUTPUT, encoding="utf-8") as f:
        assert f.read() == builder.render(), "run: python colab/build_notebook.py"


def test_embedded_package_matches_sources():
    nb = load_builder().build()
    z = embedded_zip(nb)
    names = set(z.namelist())
    expected = set()
    for root, dirs, files in os.walk(os.path.join(COLAB_DIR, "ava")):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in files:
            if not name.endswith(".pyc"):
                expected.add(os.path.relpath(os.path.join(root, name), COLAB_DIR).replace(os.sep, "/"))
    assert names == expected
    assert {"ava/server.py", "ava/web/index.html", "ava/web/app.js"} <= names
    for name in names:
        with open(os.path.join(COLAB_DIR, name), "rb") as f:
            assert z.read(name) == f.read(), name


def test_code_cells_compile_and_gpu_is_requested():
    nb = load_builder().build()
    assert nb["metadata"]["accelerator"] == "GPU"
    code = [c for c in nb["cells"] if c["cell_type"] == "code"]
    assert len(code) >= 4
    for cell in code:
        compile("".join(cell["source"]), "cell", "exec")
        assert cell["metadata"].get("cellView") == "form"
    run = next("".join(c["source"]) for c in code if "serve_kernel_port_as_window" in "".join(c["source"]))
    assert 'userdata.get(name)' in run and "PID_PATH" in run
    json.dumps(nb)  # serialisable
