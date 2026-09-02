"""Bien dich Tu_dong_dang_video.exe (PyInstaller onefile, khong console)."""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.chdir(HERE)

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
    "--add-data", "static;static",
    "--add-data", "config.example.json;.",
    "--add-data", "VERSION;.",
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
    "--clean",
]

for mod in EXCLUDES:
    cmd.extend(["--exclude-module", mod])

cmd.append("tray_app.py")

print(" ".join(cmd))
rc = subprocess.call(cmd)
if rc != 0:
    sys.exit(rc)

src = os.path.join(HERE, "dist", "Tu_dong_dang_video.exe")
if not os.path.isfile(src):
    print("Khong tim thay", src)
    sys.exit(1)

shutil.copy2(src, os.path.join(HERE, "Tu_dong_dang_video.exe"))
shutil.copy2(src, os.path.join(ROOT, "Tu_dong_dang_video.exe"))
print("OK:", os.path.join(ROOT, "Tu_dong_dang_video.exe"))
