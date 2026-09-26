"""Private Camoufox runtime for Auto Dang Video."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import threading
import urllib.request
import zipfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from core.config_manager import PROFILES_DIR, SYSTEM_DIR

APP_ID = "auto-dang-video"
PYTHON_VERSION = "3.11.9"
CAMOUFOX_PACKAGE_VERSION = "0.5.6"
PLAYWRIGHT_VERSION = "1.62.0"
CAMOUFOX_BROWSER_SPEC = "official/152.0.4-beta.30"
CAMOUFOX_BROWSER_VERSION = "152.0.4"
CAMOUFOX_BROWSER_BUILD = "beta.30"
CAMOUFOX_BROWSER_SHA256 = "ea52a02fb1cfb1813ef6a326bea03fb2b650c9774143d953a94a27bfc8f10072"
CAMOUFOX_FIREFOX_MAJOR = CAMOUFOX_BROWSER_VERSION.split(".", 1)[0]


class BrowserRuntimeError(RuntimeError):
    pass


class BrowserRuntime:
    def __init__(
        self,
        base_dir: Optional[Path] = None,
        profile_dir: Optional[Path] = None,
        app_id: str = APP_ID,
    ) -> None:
        self.app_id = app_id
        self.base_dir = Path(base_dir or SYSTEM_DIR).resolve()
        self.profile_dir = Path(profile_dir or (Path(PROFILES_DIR) / "camoufox")).resolve()
        self.runtime_root = self.base_dir / ".runtime" / self.app_id
        self.browser_dir = self.runtime_root / "browser"
        self.executable = self.browser_dir / "camoufox.exe"
        self.addons_dir = self.runtime_root / "addons"
        self.cache_dir = self.runtime_root / "cache"
        self.temp_dir = self.runtime_root / "temp"
        self.playwright_dir = self.runtime_root / "playwright"
        self.manifest_path = self.runtime_root / "runtime.json"
        self.owner_path = self.runtime_root / "owner.json"
        self.setup_lock_path = self.runtime_root / ".setup.lock"
        self._state_lock = threading.RLock()
        self._error: Optional[str] = None
        self._status = "ready" if self._validate_install() else "missing"
        self.configure_process_environment()

    def configure_process_environment(self) -> None:
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.playwright_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        os.environ["TEMP"] = str(self.temp_dir)
        os.environ["TMP"] = str(self.temp_dir)
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(self.playwright_dir)
        os.environ["LOCALAPPDATA"] = str(self.cache_dir)

    def bind_camoufox_cache(self) -> Path:
        """Bat Camoufox dung cache rieng, ke ca khi platformdirs bo qua LOCALAPPDATA."""
        import platformdirs

        scoped_root = (self.cache_dir / "camoufox").resolve()
        scoped_root.mkdir(parents=True, exist_ok=True)
        current = platformdirs.user_cache_dir
        original = getattr(current, "_camoufox_original", current)

        def scoped_user_cache_dir(appname=None, *args, **kwargs):
            if str(appname or "").lower() == "camoufox":
                return str(scoped_root)
            return original(appname, *args, **kwargs)

        scoped_user_cache_dir._camoufox_original = original
        platformdirs.user_cache_dir = scoped_user_cache_dir
        return scoped_root

    def _read_manifest(self) -> Dict[str, Any]:
        try:
            return json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _validate_install(self) -> bool:
        manifest = self._read_manifest()
        return bool(
            self._version_matches(self.browser_dir)
            and manifest.get("app_id") == self.app_id
            and manifest.get("camoufox_package") == CAMOUFOX_PACKAGE_VERSION
            and manifest.get("playwright") == PLAYWRIGHT_VERSION
            and manifest.get("browser_spec") == CAMOUFOX_BROWSER_SPEC
            and manifest.get("browser_sha256") == CAMOUFOX_BROWSER_SHA256
        )

    @property
    def is_ready(self) -> bool:
        with self._state_lock:
            if self._status == "ready" and not self._validate_install():
                self._status = "missing"
            return self._status == "ready"

    def _relative(self, path: Path) -> str:
        try:
            return str(path.resolve().relative_to(self.base_dir))
        except Exception:
            return path.name

    def status(self) -> Dict[str, Any]:
        with self._state_lock:
            return {
                "status": self._status if self._status in {"installing", "ready", "error"} else "installing",
                "app_id": self.app_id,
                "python": PYTHON_VERSION,
                "camoufox_package": CAMOUFOX_PACKAGE_VERSION,
                "playwright": PLAYWRIGHT_VERSION,
                "browser": CAMOUFOX_BROWSER_SPEC,
                "runtime": self._relative(self.runtime_root),
                "executable": self._relative(self.executable),
                "cache": self._relative(self.cache_dir),
                "temp": self._relative(self.temp_dir),
                "profile": self._relative(self.profile_dir),
                "error": self._error,
            }

    def launch_environment(self) -> Dict[str, str]:
        environment = dict(os.environ)
        environment.update({
            "TEMP": str(self.temp_dir),
            "TMP": str(self.temp_dir),
            "PLAYWRIGHT_BROWSERS_PATH": str(self.playwright_dir),
            "LOCALAPPDATA": str(self.cache_dir),
        })
        return environment

    @contextmanager
    def _setup_lock(self):
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        handle = open(self.setup_lock_path, "a+b")
        handle.seek(0)
        handle.write(b"0")
        handle.flush()
        try:
            if sys.platform == "win32":
                import msvcrt
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            try:
                if sys.platform == "win32":
                    import msvcrt
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            finally:
                handle.close()

    @staticmethod
    def _version_matches(path: Path) -> bool:
        try:
            metadata = json.loads((path / "version.json").read_text(encoding="utf-8"))
            return bool(
                metadata.get("version") == CAMOUFOX_BROWSER_VERSION
                and metadata.get("build") == CAMOUFOX_BROWSER_BUILD
                and metadata.get("sha256") == CAMOUFOX_BROWSER_SHA256
                and (path / "camoufox.exe").is_file()
                and (path / "properties.json").is_file()
            )
        except Exception:
            return False

    def _resolve_asset(self) -> Dict[str, Any]:
        from camoufox.__main__ import _do_sync, _repo_data, _resolve_spec
        from camoufox.multiversion import load_repo_cache
        _do_sync()
        repo_data = _repo_data(load_repo_cache(), "official")
        asset, _ = _resolve_spec(repo_data, f"{CAMOUFOX_BROWSER_VERSION}-{CAMOUFOX_BROWSER_BUILD}")
        if not asset:
            raise BrowserRuntimeError(f"Khong tim thay {CAMOUFOX_BROWSER_SPEC}.")
        if asset.get("sha256") != CAMOUFOX_BROWSER_SHA256:
            raise BrowserRuntimeError("Checksum Camoufox tren kho khong khop lockfile.")
        return asset

    def _download_runtime(self) -> None:
        staging = self.runtime_root / f"browser.installing-{os.getpid()}"
        archive = self.runtime_root / f"browser.installing-{os.getpid()}.zip"
        backup = self.runtime_root / f"browser.previous-{os.getpid()}"
        shutil.rmtree(staging, ignore_errors=True)
        shutil.rmtree(backup, ignore_errors=True)
        archive.unlink(missing_ok=True)
        try:
            asset = self._resolve_asset()
            expected_size = int(asset.get("asset_size") or 0)
            if shutil.disk_usage(self.runtime_root).free < expected_size * 2 + 256 * 1024 * 1024:
                raise BrowserRuntimeError("Khong du dung luong de cai Camoufox rieng.")
            digest = hashlib.sha256()
            with urllib.request.urlopen(asset["url"], timeout=60) as response, archive.open("wb") as output:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    digest.update(chunk)
                    output.write(chunk)
            if digest.hexdigest() != CAMOUFOX_BROWSER_SHA256:
                raise BrowserRuntimeError("Checksum goi Camoufox tai ve khong hop le.")
            staging.mkdir(parents=True)
            with zipfile.ZipFile(archive) as package:
                package.extractall(staging)
            (staging / "version.json").write_text(json.dumps({
                "version": CAMOUFOX_BROWSER_VERSION,
                "build": CAMOUFOX_BROWSER_BUILD,
                "sha256": CAMOUFOX_BROWSER_SHA256,
            }), encoding="utf-8")
            if not self._version_matches(staging):
                raise BrowserRuntimeError("Camoufox staging khong hop le.")
            if self.browser_dir.exists():
                self.browser_dir.replace(backup)
            try:
                staging.replace(self.browser_dir)
            except Exception:
                if backup.exists() and not self.browser_dir.exists():
                    backup.replace(self.browser_dir)
                raise
            shutil.rmtree(backup, ignore_errors=True)
        finally:
            archive.unlink(missing_ok=True)
            shutil.rmtree(staging, ignore_errors=True)

    def _write_manifest(self) -> None:
        payload = {
            "schema": 1, "app_id": self.app_id, "python": PYTHON_VERSION,
            "camoufox_package": CAMOUFOX_PACKAGE_VERSION, "playwright": PLAYWRIGHT_VERSION,
            "browser_spec": CAMOUFOX_BROWSER_SPEC, "browser_sha256": CAMOUFOX_BROWSER_SHA256,
            "executable": str(self.executable), "installed_at": datetime.now(timezone.utc).isoformat(),
        }
        temporary = self.manifest_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.manifest_path)

    def _recover_interrupted_install(self) -> None:
        for path in self.runtime_root.glob("browser.installing-*"):
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)
        previous = sorted(self.runtime_root.glob("browser.previous-*"), key=lambda item: item.stat().st_mtime, reverse=True)
        if not self.browser_dir.exists():
            for candidate in previous:
                if candidate.is_dir() and self._version_matches(candidate):
                    candidate.replace(self.browser_dir)
                    break
        for candidate in previous:
            if candidate.exists():
                shutil.rmtree(candidate, ignore_errors=True)

    def ensure_ready(self) -> Path:
        with self._setup_lock():
            self.bind_camoufox_cache()
            self._recover_interrupted_install()
            with self._state_lock:
                if self._validate_install():
                    self._status, self._error = "ready", None
                    return self.executable
                self._status, self._error = "installing", None
            try:
                self._download_runtime()
                self._write_manifest()
                if not self._validate_install():
                    raise BrowserRuntimeError("Runtime rieng khong hop le sau khi cai.")
                with self._state_lock:
                    self._status = "ready"
                return self.executable
            except Exception as exc:
                with self._state_lock:
                    self._status, self._error = "error", str(exc)
                raise

    def launch_addon_options(self) -> Dict[str, Any]:
        try:
            self.bind_camoufox_cache()
            from camoufox.addons import DefaultAddons
            ubo = self.addons_dir / "UBO"
            return {"addons": [str(ubo)] if (ubo / "manifest.json").is_file() else [], "exclude_addons": list(DefaultAddons)}
        except Exception:
            return {}

    def owned_browser_pids(self) -> list[int]:
        try:
            import psutil
            executable = os.path.normcase(str(self.executable.resolve()))
            profile = os.path.normcase(str(self.profile_dir.resolve()))
            result = []
            for process in psutil.process_iter(["pid", "exe", "cmdline"]):
                try:
                    exe = os.path.normcase(process.info.get("exe") or "")
                    command = os.path.normcase(" ".join(process.info.get("cmdline") or []))
                    if exe == executable and profile in command:
                        result.append(int(process.info["pid"]))
                except Exception:
                    continue
            return result
        except Exception:
            return []

    def record_owner(self, browser_pids: Iterable[int]) -> None:
        payload = {
            "app_id": self.app_id, "server_pid": os.getpid(),
            "browser_pids": sorted({int(pid) for pid in browser_pids if pid}),
            "executable": str(self.executable), "profile": str(self.profile_dir),
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        temporary = self.owner_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.owner_path)

    def clear_owner(self) -> None:
        try:
            owner = json.loads(self.owner_path.read_text(encoding="utf-8"))
            if owner.get("server_pid") == os.getpid():
                self.owner_path.unlink(missing_ok=True)
        except Exception:
            pass


class ProfileProcessLock:
    def __init__(self, app_id: str, profile_dir: Path) -> None:
        digest = hashlib.sha256(f"{app_id}|{Path(profile_dir).resolve()}".encode()).hexdigest()[:24]
        self.name = f"Local\\THV_Camoufox_{digest}"
        self._handle = None

    def acquire(self) -> bool:
        if self._handle:
            return True
        if sys.platform != "win32":
            return True
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.CreateMutexW(None, False, self.name)
        if not handle:
            return False
        result = kernel32.WaitForSingleObject(handle, 0)
        if result not in (0x00000000, 0x00000080):
            kernel32.CloseHandle(handle)
            return False
        self._handle = handle
        return True

    def release(self) -> None:
        if self._handle and sys.platform == "win32":
            import ctypes
            ctypes.windll.kernel32.ReleaseMutex(self._handle)
            ctypes.windll.kernel32.CloseHandle(self._handle)
        self._handle = None


browser_runtime = BrowserRuntime()
