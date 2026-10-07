"""Bien dich Tu_dong_dang_video.exe (PyInstaller onefile, khong console)."""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.chdir(HERE)
BUILD_ROOT = os.path.abspath(os.environ.get("AUTO_BUILD_ROOT", HERE))
os.makedirs(BUILD_ROOT, exist_ok=True)
SPEC_DIR = os.path.join(BUILD_ROOT, "spec")
WORK_DIR = os.path.join(BUILD_ROOT, "build")
DIST_DIR = os.path.join(BUILD_ROOT, "dist")
for directory in (SPEC_DIR, WORK_DIR, DIST_DIR):
    os.makedirs(directory, exist_ok=True)

RUNTIME_PYTHON = os.path.join(HERE, ".runtime", "auto-dang-video", "python", "python.exe")
if os.path.isfile(RUNTIME_PYTHON) and os.path.normcase(sys.executable) != os.path.normcase(RUNTIME_PYTHON):
    raise SystemExit(subprocess.call([RUNTIME_PYTHON, os.path.abspath(__file__)]))
if not os.path.isfile(RUNTIME_PYTHON):
    raise SystemExit("Chua co Python runtime rieng. Hay chay bootstrap.ps1 truoc khi build.")

from importlib.metadata import version

EXPECTED = {"camoufox": "0.5.6", "playwright": "1.62.0", "pyinstaller": "6.14.2"}
for package, expected in EXPECTED.items():
    actual = version(package)
    if actual != expected:
        raise SystemExit(f"Sai version {package}: can {expected}, dang co {actual}")

EXCLUDES = [
    "torch", "torchaudio", "torchvision", "tensorflow", "keras",
    "pandas", "sklearn", "scipy", "cv2", "transformers", "datasets",
    "nltk", "onnxruntime", "yt_dlp", "wandb", "matplotlib", "numba",
    "pyarrow", "boto3", "botocore", "librosa", "bitsandbytes",
    "altair", "IPython", "notebook", "jupyter", "sympy",
    "soundfile",
]

cmd = [
    sys.executable, "-m", "PyInstaller",
    "--noconsole",
    "--onefile",
    "--name", "Tu_dong_dang_video",
    "--specpath", SPEC_DIR,
    "--workpath", WORK_DIR,
    "--distpath", DIST_DIR,
    "--add-data", os.path.join(HERE, "static") + ";static",
    "--add-data", os.path.join(HERE, "config.example.json") + ";.",
    "--add-data", os.path.join(HERE, "VERSION") + ";.",
    "--add-data", os.path.join(HERE, "core", "app_supervisor.py") + ";.",
    "--hidden-import", "uvicorn.logging",
    "--hidden-import", "uvicorn.loops.auto",
    "--hidden-import", "uvicorn.protocols.http.auto",
    "--hidden-import", "uvicorn.protocols.websockets.auto",
    "--hidden-import", "pystray._win32",
    "--hidden-import", "PIL",
    "--hidden-import", "openai",
    "--hidden-import", "dotenv",
    "--hidden-import", "automation.ai_fallback",
    "--hidden-import", "automation.posters.facebook_poster",
    "--hidden-import", "automation.posters.instagram_poster",
    "--hidden-import", "automation.posters.youtube_poster",
    "--hidden-import", "automation.posters.tiktok_poster",
    "--hidden-import", "core.email_reporter",
    "--hidden-import", "core.schedule_helper",
    "--hidden-import", "psutil",
    "--collect-all", "camoufox",
    "--collect-all", "browserforge",
    "--collect-all", "apify_fingerprint_datapoints",
    "--collect-all", "language_tags",
    "--clean",
]

for mod in EXCLUDES:
    cmd.extend(["--exclude-module", mod])

cmd.append(os.path.join(HERE, "tray_app.py"))

print(" ".join(cmd))
rc = subprocess.call(cmd)
if rc != 0:
    sys.exit(rc)

src = os.path.join(DIST_DIR, "Tu_dong_dang_video.exe")
if not os.path.isfile(src):
    print("Khong tim thay", src)
    sys.exit(1)

if os.path.normcase(BUILD_ROOT) == os.path.normcase(HERE):
    release_artifact = os.path.join(HERE, "Tu_dong_dang_video.exe")
    shutil.copy2(src, release_artifact)
    root_copy = os.path.join(ROOT, "Tu_dong_dang_video.exe")
    try:
        shutil.copy2(src, root_copy)
        print("OK:", root_copy)
    except PermissionError:
        # The installed onefile app may currently be running and Windows locks
        # its executable.  Publishing uses release_artifact, so do not stop a
        # live user workflow just to refresh this ignored convenience copy.
        print("CANH BAO: EXE goc dang duoc su dung; giu artifact moi tai", release_artifact)
else:
    print("OK test build:", src)
