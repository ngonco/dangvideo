import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from core.browser_runtime import (
    CAMOUFOX_BROWSER_SHA256,
    CAMOUFOX_BROWSER_SPEC,
    CAMOUFOX_PACKAGE_VERSION,
    PLAYWRIGHT_VERSION,
    BrowserRuntime,
    ProfileProcessLock,
)


class _FakeProcess:
    def __init__(self, pid, executable, command):
        self.info = {"pid": pid, "exe": executable, "cmdline": command}


class BrowserRuntimeIsolationTests(unittest.TestCase):
    def _runtime(self, root: Path, app_id: str) -> BrowserRuntime:
        return BrowserRuntime(root, root / "profile", app_id=app_id)

    @staticmethod
    def _write_valid_runtime(runtime: BrowserRuntime):
        runtime.browser_dir.mkdir(parents=True, exist_ok=True)
        runtime.executable.write_bytes(b"private-camoufox")
        (runtime.browser_dir / "properties.json").write_text("{}", encoding="utf-8")
        (runtime.browser_dir / "version.json").write_text(json.dumps({
            "version": "152.0.4",
            "build": "beta.30",
            "sha256": CAMOUFOX_BROWSER_SHA256,
        }), encoding="utf-8")
        runtime.manifest_path.write_text(json.dumps({
            "app_id": runtime.app_id,
            "camoufox_package": CAMOUFOX_PACKAGE_VERSION,
            "playwright": PLAYWRIGHT_VERSION,
            "browser_spec": CAMOUFOX_BROWSER_SPEC,
            "browser_sha256": CAMOUFOX_BROWSER_SHA256,
        }), encoding="utf-8")

    def test_two_apps_have_distinct_runtime_and_lock_names(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            auto = self._runtime(root, "auto-dang-video")
            scan = self._runtime(root, "scan-viral")
            self.assertNotEqual(auto.executable, scan.executable)
            self.assertNotEqual(auto.temp_dir, scan.temp_dir)
            self.assertNotEqual(auto.cache_dir, scan.cache_dir)
            self.assertNotEqual(
                ProfileProcessLock(auto.app_id, auto.profile_dir).name,
                ProfileProcessLock(scan.app_id, scan.profile_dir).name,
            )

    def test_browser_engine_never_uses_global_launch_path(self):
        source = (Path(__file__).resolve().parent / "automation" / "browser_engine.py").read_text(encoding="utf-8")
        self.assertIn("executable_path=executable", source)
        self.assertIn("ff_version=CAMOUFOX_FIREFOX_MAJOR", source)
        self.assertNotIn("launch_path(", source)

    def test_camoufox_platform_cache_is_forced_under_app_runtime(self):
        import platformdirs

        with tempfile.TemporaryDirectory() as temp:
            runtime = self._runtime(Path(temp), "auto-dang-video")
            previous = platformdirs.user_cache_dir
            try:
                scoped = runtime.bind_camoufox_cache()
                self.assertEqual(Path(platformdirs.user_cache_dir("camoufox")), scoped)
                self.assertTrue(scoped.is_relative_to(runtime.cache_dir))
            finally:
                platformdirs.user_cache_dir = previous

    def test_partial_or_wrong_manifest_is_not_ready(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = self._runtime(Path(temp), "auto-dang-video")
            runtime.browser_dir.mkdir(parents=True, exist_ok=True)
            runtime.executable.write_bytes(b"partial")
            runtime._status = "ready"
            self.assertFalse(runtime.is_ready)
            self._write_valid_runtime(runtime)
            runtime._status = "ready"
            self.assertTrue(runtime.is_ready)

    def test_wrong_browser_checksum_is_not_ready(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = self._runtime(Path(temp), "auto-dang-video")
            self._write_valid_runtime(runtime)
            version_path = runtime.browser_dir / "version.json"
            metadata = json.loads(version_path.read_text(encoding="utf-8"))
            metadata["sha256"] = "wrong"
            version_path.write_text(json.dumps(metadata), encoding="utf-8")
            runtime._status = "ready"
            self.assertFalse(runtime.is_ready)

    def test_interrupted_atomic_swap_restores_valid_previous_runtime(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = self._runtime(Path(temp), "auto-dang-video")
            self._write_valid_runtime(runtime)
            previous = runtime.runtime_root / "browser.previous-123"
            runtime.browser_dir.replace(previous)
            staging = runtime.runtime_root / "browser.installing-123"
            staging.mkdir()
            (staging / "partial").write_text("partial", encoding="utf-8")
            self.assertEqual(runtime.ensure_ready(), runtime.executable)
            self.assertTrue(runtime.executable.is_file())
            self.assertFalse(staging.exists())
            self.assertFalse(previous.exists())

    def test_foreign_camoufox_process_is_never_owned(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = self._runtime(Path(temp), "auto-dang-video")
            executable = str(runtime.executable.resolve())
            profile = str(runtime.profile_dir.resolve())
            processes = [
                _FakeProcess(21, executable, [executable, "-profile", profile]),
                _FakeProcess(22, "D:/scan/browser/camoufox.exe", ["D:/scan/browser/camoufox.exe", "-profile", "D:/scan/profile"]),
            ]
            with patch("psutil.process_iter", return_value=processes):
                self.assertEqual(runtime.owned_browser_pids(), [21])

    @unittest.skipUnless(sys.platform == "win32", "Windows named mutex")
    def test_same_profile_is_exclusive_but_other_app_can_run(self):
        with tempfile.TemporaryDirectory() as temp:
            profile = Path(temp) / "profile"
            first = ProfileProcessLock("auto-dang-video", profile)
            duplicate = ProfileProcessLock("auto-dang-video", profile)
            other_app = ProfileProcessLock("scan-viral", profile)
            acquired = threading.Event()
            release = threading.Event()

            def hold_first():
                self.assertTrue(first.acquire())
                acquired.set()
                release.wait(5)
                first.release()

            holder = threading.Thread(target=hold_first)
            holder.start()
            try:
                self.assertTrue(acquired.wait(2))
                self.assertFalse(duplicate.acquire())
                self.assertTrue(other_app.acquire())
            finally:
                duplicate.release()
                other_app.release()
                release.set()
                holder.join(2)


if __name__ == "__main__":
    unittest.main()
