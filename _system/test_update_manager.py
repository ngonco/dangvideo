import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from unittest import mock

import publish_github_release as release_publisher
from core.update_manager import (
    EXE_NAME,
    SHA_NAME,
    UpdateManager,
    normalize_version,
    parse_version,
    sha256_file,
)
from publish_github_release import create_sha256_file


class FakeResponse:
    def __init__(self, *, payload=None, content=b"", text=None, headers=None, status=200):
        self._payload = payload
        self.content = content
        self.text = text if text is not None else content.decode("utf-8", errors="replace")
        self.headers = headers or {}
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload

    def iter_content(self, chunk_size=1024 * 1024):
        for start in range(0, len(self.content), chunk_size):
            yield self.content[start:start + chunk_size]


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.headers = {}
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if not self.responses:
            raise AssertionError(f"Unexpected request: {url}")
        return self.responses.pop(0)


def release_payload(version, exe_bytes, *, prerelease=False, draft=False):
    base = f"https://github.com/ngonco/dangvideo/releases/download/v{version}"
    return {
        "tag_name": f"v{version}",
        "draft": draft,
        "prerelease": prerelease,
        "assets": [
            {
                "name": EXE_NAME,
                "size": len(exe_bytes),
                "browser_download_url": f"{base}/{EXE_NAME}",
            },
            {
                "name": SHA_NAME,
                "size": 100,
                "browser_download_url": f"{base}/{SHA_NAME}",
            },
        ],
    }


class UpdateManagerTests(unittest.TestCase):
    def test_strict_version_parsing(self):
        self.assertEqual(parse_version("v1.12.3"), (1, 12, 3))
        self.assertEqual(normalize_version("1.12.3"), "1.12.3")
        self.assertIsNone(parse_version("1.12"))
        self.assertIsNone(parse_version("1.12.3-beta"))
        self.assertIsNone(parse_version("latest"))

    def test_download_is_atomic_and_writes_pending_manifest(self):
        exe_bytes = b"MZ" + (b"safe-update" * 100)
        digest = hashlib.sha256(exe_bytes).hexdigest()
        release = release_payload("1.12.0", exe_bytes)
        session = FakeSession([
            FakeResponse(payload=release),
            FakeResponse(text=f"{digest}  {EXE_NAME}\n"),
            FakeResponse(content=exe_bytes, headers={"Content-Length": str(len(exe_bytes))}),
        ])
        with tempfile.TemporaryDirectory() as temp_dir:
            current = os.path.join(temp_dir, EXE_NAME)
            with open(current, "wb") as handle:
                handle.write(b"MZ-old")
            manager = UpdateManager(
                current_version="1.11.0",
                executable_path=current,
                frozen=True,
                update_root=temp_dir,
                session=session,
            )
            manager._check_and_download()
            status = manager.status()
            self.assertEqual(status["state"], "ready")
            self.assertEqual(status["latest_version"], "1.12.0")
            self.assertTrue(status["pending"])
            with open(manager.pending_path, encoding="utf-8") as handle:
                pending = json.load(handle)
            self.assertEqual(pending["sha256"], digest)
            self.assertTrue(os.path.isfile(pending["ready_path"]))
            self.assertFalse(os.path.exists(pending["ready_path"] + ".part"))

    def test_bad_sha_does_not_create_pending_update(self):
        exe_bytes = b"MZ" + b"broken"
        release = release_payload("1.12.0", exe_bytes)
        session = FakeSession([
            FakeResponse(payload=release),
            FakeResponse(text=("0" * 64) + f"  {EXE_NAME}\n"),
            FakeResponse(content=exe_bytes),
        ])
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = UpdateManager(
                current_version="1.11.0",
                executable_path=os.path.join(temp_dir, EXE_NAME),
                frozen=True,
                update_root=temp_dir,
                session=session,
            )
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                manager._check_and_download()
            self.assertFalse(os.path.exists(manager.pending_path))
            self.assertFalse(any(name.endswith(".part") for name in os.listdir(manager.update_dir)))

    def test_busy_workflow_defers_download_without_network_call(self):
        exe_bytes = b"MZ-new"
        release = release_payload("1.12.0", exe_bytes)
        exe_asset, sha_asset = UpdateManager._select_assets(release)
        session = FakeSession([])
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = UpdateManager(
                current_version="1.11.0",
                executable_path=os.path.join(temp_dir, EXE_NAME),
                frozen=True,
                update_root=temp_dir,
                session=session,
            )
            manager.set_busy_provider(lambda: True)
            manager._available_release = {
                "version": "1.12.0",
                "exe_asset": exe_asset,
                "sha_asset": sha_asset,
            }
            manager._download_available_release()
            self.assertEqual(manager.status()["state"], "deferred")
            self.assertEqual(session.calls, [])

    def test_prerelease_is_rejected(self):
        session = FakeSession([FakeResponse(payload=release_payload("1.12.0", b"MZ", prerelease=True))])
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = UpdateManager(
                current_version="1.11.0",
                executable_path=os.path.join(temp_dir, EXE_NAME),
                frozen=True,
                update_root=temp_dir,
                session=session,
            )
            with self.assertRaisesRegex(ValueError, "nháp/thử nghiệm"):
                manager._check_and_download()

    def test_source_mode_never_launches_replacement(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = UpdateManager(
                current_version="1.11.0",
                executable_path=os.path.join(temp_dir, "python.exe"),
                frozen=False,
                update_root=temp_dir,
                session=FakeSession([]),
            )
            self.assertFalse(manager.launch_pending_installer())
            self.assertEqual(manager.status()["state"], "source_mode")

    def test_verified_pending_update_launches_helper_and_exits(self):
        exe_bytes = b"MZ" + b"new-version"
        digest = hashlib.sha256(exe_bytes).hexdigest()
        with tempfile.TemporaryDirectory() as temp_dir:
            current = os.path.join(temp_dir, EXE_NAME)
            ready = os.path.join(temp_dir, "new.ready")
            for path, data in ((current, b"MZ-old"), (ready, exe_bytes)):
                with open(path, "wb") as handle:
                    handle.write(data)
            manager = UpdateManager(
                current_version="1.11.0",
                executable_path=current,
                frozen=True,
                update_root=temp_dir,
                session=FakeSession([]),
            )
            os.makedirs(manager.update_dir, exist_ok=True)
            with open(manager.pending_path, "w", encoding="utf-8") as handle:
                json.dump({
                    "version": "1.12.0",
                    "sha256": digest,
                    "ready_path": ready,
                    "target_path": current,
                }, handle)
            with mock.patch("core.update_manager.subprocess.Popen") as popen:
                self.assertTrue(manager.launch_pending_installer())
            popen.assert_called_once()
            self.assertFalse(os.path.exists(manager.pending_path))
            self.assertTrue(os.path.exists(manager.applying_path))
            self.assertTrue(os.path.exists(manager.helper_path))
            command = popen.call_args.args[0]
            self.assertIn("-ExpectedVersion", command)
            self.assertIn("1.12.0", command)

    def test_stale_handoff_with_valid_stage_is_retried(self):
        exe_bytes = b"MZ" + b"retry-version"
        digest = hashlib.sha256(exe_bytes).hexdigest()
        with tempfile.TemporaryDirectory() as temp_dir:
            current = os.path.join(temp_dir, EXE_NAME)
            ready = os.path.join(temp_dir, "retry.ready")
            for path, data in ((current, b"MZ-old"), (ready, exe_bytes)):
                with open(path, "wb") as handle:
                    handle.write(data)
            manager = UpdateManager(
                current_version="1.11.0",
                executable_path=current,
                frozen=True,
                update_root=temp_dir,
                session=FakeSession([]),
            )
            os.makedirs(manager.update_dir, exist_ok=True)
            with open(manager.applying_path, "w", encoding="utf-8") as handle:
                json.dump({
                    "version": "1.12.0",
                    "sha256": digest,
                    "ready_path": ready,
                    "target_path": current,
                }, handle)
            self.assertEqual(manager.recover_stale_applying(max_age_seconds=0), "retry")
            self.assertTrue(os.path.isfile(manager.pending_path))
            self.assertFalse(os.path.exists(manager.applying_path))

    def test_release_checksum_sidecar_format(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            exe_path = os.path.join(temp_dir, EXE_NAME)
            with open(exe_path, "wb") as handle:
                handle.write(b"MZ-release")
            sha_path = create_sha256_file(exe_path)
            with open(sha_path, encoding="ascii") as handle:
                line = handle.read().strip()
            expected = hashlib.sha256(b"MZ-release").hexdigest()
            self.assertEqual(line, f"{expected}  {EXE_NAME}")

    def test_release_stays_draft_until_both_assets_are_uploaded(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            exe_path = os.path.join(temp_dir, EXE_NAME)
            sha_path = exe_path + ".sha256"
            for path, data in ((exe_path, b"MZ-release"), (sha_path, b"abc  file\n")):
                with open(path, "wb") as handle:
                    handle.write(data)
            responses = [
                (201, {"id": 123, "upload_url": "https://uploads.github.test/release{?name}"}),
                (201, {}),
                (201, {}),
                (200, {"draft": False}),
            ]
            with mock.patch.object(release_publisher, "api_request", side_effect=responses) as request:
                release_publisher.create_release_with_api(
                    "v1.12.0", [exe_path, sha_path], "notes", "secret-token"
                )
            create_payload = json.loads(request.call_args_list[0].kwargs["data"].decode("utf-8"))
            self.assertTrue(create_payload["draft"])
            self.assertEqual(request.call_args_list[-1].args[0], "PATCH")
            publish_payload = json.loads(request.call_args_list[-1].kwargs["data"].decode("utf-8"))
            self.assertFalse(publish_payload["draft"])

    @unittest.skipUnless(os.name == "nt", "Windows updater helper")
    def test_unhealthy_replacement_rolls_back_real_files(self):
        old_program = shutil.which("whoami.exe")
        new_program = shutil.which("where.exe")
        self.assertTrue(old_program and new_program)
        with tempfile.TemporaryDirectory(prefix="Auto Video Updater ") as temp_dir:
            current = os.path.join(temp_dir, EXE_NAME)
            staged = os.path.join(temp_dir, "staged.exe")
            backup = current + ".update-backup.exe"
            applying = os.path.join(temp_dir, "applying.json")
            result = os.path.join(temp_dir, "last_result.json")
            shutil.copy2(old_program, current)
            shutil.copy2(new_program, staged)
            old_sha = sha256_file(current)
            staged_sha = sha256_file(staged)
            with open(applying, "w", encoding="utf-8") as handle:
                json.dump({"version": "9.9.9"}, handle)
            manager = UpdateManager(
                current_version="1.0.0",
                executable_path=current,
                frozen=True,
                update_root=temp_dir,
                session=FakeSession([]),
            )
            manager._write_helper_script()
            completed = subprocess.run([
                "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-File", manager.helper_path,
                "-ParentPid", "0",
                "-CurrentExe", current,
                "-StagedExe", staged,
                "-BackupExe", backup,
                "-ExpectedVersion", "9.9.9",
                "-ExpectedSha256", staged_sha,
                "-ApplyingManifest", applying,
                "-ResultPath", result,
            ], capture_output=True, text=True, timeout=30)
            self.assertNotEqual(completed.returncode, 0)
            with open(current, "rb") as handle:
                restored_sha = hashlib.sha256(handle.read()).hexdigest()
            self.assertEqual(restored_sha, old_sha)
            self.assertFalse(os.path.exists(backup))
            self.assertFalse(os.path.exists(applying))
            with open(result, encoding="utf-8-sig") as handle:
                payload = json.load(handle)
            self.assertFalse(payload["success"])
            # The rollback relaunch is intentionally detached; allow this tiny
            # console fixture to exit before TemporaryDirectory removes it.
            time.sleep(2)


if __name__ == "__main__":
    unittest.main()
