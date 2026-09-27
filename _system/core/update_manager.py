"""Automatic updater for the packaged Windows executable.

The running one-file executable is locked by Windows, so updates are downloaded
and verified while the app is running, then applied by a detached PowerShell
helper the next time the app starts.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

import requests

from core.config_manager import config_mgr, get_app_version
from core.logger import logger


REPO_SLUG = "ngonco/dangvideo"
RELEASE_API_URL = f"https://api.github.com/repos/{REPO_SLUG}/releases/latest"
EXE_NAME = "Tu_dong_dang_video.exe"
SHA_NAME = EXE_NAME + ".sha256"
CHECK_INTERVAL_SECONDS = 6 * 60 * 60
DEFER_RETRY_SECONDS = 5 * 60
ERROR_RETRY_SECONDS = 30 * 60
STARTUP_DELAY_SECONDS = 10
SCHEDULE_GUARD_MINUTES = 15
VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$", re.IGNORECASE)


def parse_version(value: str) -> Optional[Tuple[int, int, int]]:
    """Parse a strict three-component release version."""
    match = VERSION_RE.fullmatch((value or "").strip())
    if not match:
        return None
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def normalize_version(value: str) -> Optional[str]:
    parsed = parse_version(value)
    if parsed is None:
        return None
    return ".".join(str(part) for part in parsed)


def sha256_file(path: str, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json_write(path: str, payload: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp_path = path + ".tmp"
    with open(temp_path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp_path, path)


def _read_json(path: str) -> Optional[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError, TypeError):
        return None


class UpdateManager:
    def __init__(
        self,
        *,
        current_version: Optional[str] = None,
        executable_path: Optional[str] = None,
        frozen: Optional[bool] = None,
        update_root: Optional[str] = None,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.current_version = current_version or get_app_version()
        self.frozen = bool(getattr(sys, "frozen", False) if frozen is None else frozen)
        default_executable = sys.executable if self.frozen else os.path.abspath(sys.argv[0])
        self.executable_path = os.path.abspath(executable_path or default_executable)
        install_key = hashlib.sha256(os.path.normcase(self.executable_path).encode("utf-8")).hexdigest()[:16]
        base_root = update_root or os.path.join(
            os.environ.get("LOCALAPPDATA") or os.path.expanduser("~\AppData\Local"),
            "AutoVideoPro",
            "updates",
        )
        self.update_dir = os.path.join(os.path.abspath(base_root), install_key)
        self.pending_path = os.path.join(self.update_dir, "pending.json")
        self.applying_path = os.path.join(self.update_dir, "applying.json")
        self.result_path = os.path.join(self.update_dir, "last_result.json")
        self.helper_path = os.path.join(self.update_dir, "apply_update.ps1")
        self.session = session or requests.Session()
        self.session.headers.update({
            "Accept": "application/vnd.github+json",
            "User-Agent": "AutoVideoPro-Updater",
            "X-GitHub-Api-Version": "2022-11-28",
        })
        self._state_lock = threading.RLock()
        self._async_lock: Optional[asyncio.Lock] = None
        self._loop_task: Optional[asyncio.Task] = None
        self._operation_task: Optional[asyncio.Task] = None
        self._stop_requested = threading.Event()
        self._busy_provider: Callable[[], bool] = lambda: False
        self._available_release: Optional[Dict[str, Any]] = None
        self._status: Dict[str, Any] = {
            "state": "idle" if self.frozen else "source_mode",
            "current_version": self.current_version,
            "latest_version": None,
            "progress": 0,
            "message": (
                "Sẵn sàng kiểm tra cập nhật tự động."
                if self.frozen
                else "Chế độ mã nguồn không tự thay thế file .exe."
            ),
            "last_check": None,
            "pending": False,
        }
        self._restore_persisted_status()

    def _restore_persisted_status(self) -> None:
        if not self.frozen:
            return
        pending = _read_json(self.pending_path)
        if pending:
            ready_path = str(pending.get("ready_path") or "")
            version = normalize_version(str(pending.get("version") or ""))
            if version and os.path.isfile(ready_path):
                self._status.update({
                    "state": "ready",
                    "latest_version": version,
                    "progress": 100,
                    "message": f"Đã tải bản {version}; sẽ cài ở lần mở ứng dụng tiếp theo.",
                    "pending": True,
                })
                return
        result = _read_json(self.result_path)
        if result and result.get("success") is False:
            self._status.update({
                "state": "error",
                "message": str(result.get("message") or "Lần cập nhật trước không thành công; đang giữ bản cũ."),
            })

    def set_busy_provider(self, provider: Callable[[], bool]) -> None:
        self._busy_provider = provider

    def status(self) -> Dict[str, Any]:
        with self._state_lock:
            return dict(self._status)

    def _set_status(self, **changes: Any) -> None:
        with self._state_lock:
            self._status.update(changes)

    async def start(self) -> None:
        if not self.frozen or (self._loop_task and not self._loop_task.done()):
            return
        self._stop_requested.clear()
        self._async_lock = asyncio.Lock()
        self._loop_task = asyncio.create_task(self._periodic_loop(), name="automatic-update-loop")

    async def stop(self) -> None:
        self._stop_requested.set()
        tasks = [task for task in (self._operation_task, self._loop_task) if task and not task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._operation_task = None
        self._loop_task = None

    async def trigger_check(self) -> Dict[str, Any]:
        if not self.frozen:
            return {"success": False, **self.status()}
        if self._operation_task and not self._operation_task.done():
            return {"success": True, **self.status()}
        self._set_status(state="checking", progress=0, message="Đang kiểm tra bản mới trên GitHub...")
        self._operation_task = asyncio.create_task(self._run_operation(), name="automatic-update-check")
        return {"success": True, **self.status()}

    async def _periodic_loop(self) -> None:
        try:
            await asyncio.sleep(STARTUP_DELAY_SECONDS)
            while not self._stop_requested.is_set():
                await self.trigger_check()
                operation = self._operation_task
                if operation:
                    await asyncio.gather(operation, return_exceptions=True)
                state = self.status().get("state")
                if state in {"deferred", "available"}:
                    delay = DEFER_RETRY_SECONDS
                elif state == "error":
                    delay = ERROR_RETRY_SECONDS
                else:
                    delay = CHECK_INTERVAL_SECONDS
                await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return

    async def _run_operation(self) -> None:
        if self._async_lock is None:
            self._async_lock = asyncio.Lock()
        async with self._async_lock:
            try:
                if self._available_release:
                    await asyncio.to_thread(self._download_available_release)
                else:
                    await asyncio.to_thread(self._check_and_download)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._set_status(
                    state="error",
                    progress=0,
                    message=f"Không thể cập nhật: {exc}",
                    last_check=datetime.now().isoformat(timespec="seconds"),
                )
                logger.error(f"Không thể kiểm tra/cập nhật: {exc}", "UPDATE")

    def _check_and_download(self) -> None:
        if self._stop_requested.is_set():
            return
        self._set_status(state="checking", progress=0, message="Đang kiểm tra bản mới trên GitHub...")
        response = self.session.get(RELEASE_API_URL, timeout=(10, 30))
        response.raise_for_status()
        release = response.json()
        now = datetime.now().isoformat(timespec="seconds")
        if not isinstance(release, dict):
            raise ValueError("GitHub trả về dữ liệu bản phát hành không hợp lệ")
        if release.get("draft") or release.get("prerelease"):
            raise ValueError("Bản phát hành mới nhất là bản nháp/thử nghiệm nên đã bị bỏ qua")
        version = normalize_version(str(release.get("tag_name") or ""))
        current = parse_version(self.current_version)
        latest = parse_version(version or "")
        if not version or current is None or latest is None:
            raise ValueError("Số phiên bản GitHub không đúng định dạng x.y.z")
        self._set_status(latest_version=version, last_check=now)
        if latest <= current:
            self._available_release = None
            self._set_status(
                state="up_to_date",
                progress=100,
                message=f"Ứng dụng đang ở bản mới nhất ({self.current_version}).",
                pending=False,
            )
            logger.success("Ứng dụng đang ở phiên bản mới nhất.", "UPDATE")
            return

        existing = _read_json(self.pending_path)
        if existing and normalize_version(str(existing.get("version") or "")) == version:
            ready_path = str(existing.get("ready_path") or "")
            if os.path.isfile(ready_path):
                self._available_release = None
                self._set_status(
                    state="ready",
                    progress=100,
                    message=f"Đã tải bản {version}; sẽ cài ở lần mở ứng dụng tiếp theo.",
                    pending=True,
                )
                return

        exe_asset, sha_asset = self._select_assets(release)
        self._available_release = {
            "version": version,
            "exe_asset": exe_asset,
            "sha_asset": sha_asset,
        }
        self._download_available_release()

    @staticmethod
    def _select_assets(release: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        assets = release.get("assets")
        if not isinstance(assets, list):
            raise ValueError("GitHub Release không có danh sách file")
        by_name = {
            str(asset.get("name")): asset
            for asset in assets
            if isinstance(asset, dict) and asset.get("name")
        }
        exe_asset = by_name.get(EXE_NAME)
        sha_asset = by_name.get(SHA_NAME)
        if not exe_asset or not sha_asset:
            raise ValueError(f"Bản phát hành phải có đủ {EXE_NAME} và {SHA_NAME}")
        for asset in (exe_asset, sha_asset):
            url = str(asset.get("browser_download_url") or "")
            if not url.startswith(f"https://github.com/{REPO_SLUG}/releases/download/"):
                raise ValueError("Đường dẫn file cập nhật không thuộc GitHub Release chính thức")
        return exe_asset, sha_asset

    def _is_near_schedule(self) -> bool:
        slots = config_mgr.get("schedule", {}).get("post_time_slots", [])
        now = datetime.now()
        for raw_slot in slots:
            try:
                hour, minute = (int(part) for part in str(raw_slot).split(":", 1))
                scheduled = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                delta = scheduled - now
                if timedelta(0) <= delta <= timedelta(minutes=SCHEDULE_GUARD_MINUTES):
                    return True
            except (TypeError, ValueError):
                continue
        return False

    def _download_available_release(self) -> None:
        release = self._available_release
        if not release:
            self._check_and_download()
            return
        version = str(release["version"])
        if self._busy_provider():
            self._set_status(
                state="deferred",
                progress=0,
                message=f"Có bản {version}; sẽ tải sau khi tác vụ đăng/tải video hoàn tất.",
            )
            return
        if self._is_near_schedule():
            self._set_status(
                state="deferred",
                progress=0,
                message=f"Có bản {version}; tạm hoãn tải vì sắp đến giờ đăng video.",
            )
            return
        self._download_release(release)

    def _download_release(self, release: Dict[str, Any]) -> None:
        version = str(release["version"])
        exe_asset = release["exe_asset"]
        sha_asset = release["sha_asset"]
        os.makedirs(self.update_dir, exist_ok=True)
        self._set_status(state="downloading", progress=0, message=f"Đang tải bản {version}...")
        logger.info(f"Đang tải bản cập nhật {version} từ GitHub Release...", "UPDATE")

        sha_response = self.session.get(str(sha_asset["browser_download_url"]), timeout=(10, 30))
        sha_response.raise_for_status()
        expected_sha = self._parse_sha256(sha_response.text)

        ready_path = os.path.join(self.update_dir, f"{EXE_NAME}.{version}.ready")
        part_path = ready_path + ".part"
        try:
            if os.path.exists(part_path):
                os.remove(part_path)
            response = self.session.get(str(exe_asset["browser_download_url"]), stream=True, timeout=(15, 120))
            response.raise_for_status()
            expected_size = int(exe_asset.get("size") or response.headers.get("Content-Length") or 0)
            digest = hashlib.sha256()
            written = 0
            with open(part_path, "wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if self._stop_requested.is_set():
                        raise RuntimeError("Ứng dụng đang đóng; đã dừng tải cập nhật")
                    if not chunk:
                        continue
                    handle.write(chunk)
                    digest.update(chunk)
                    written += len(chunk)
                    progress = min(99, int(written * 100 / expected_size)) if expected_size else 0
                    self._set_status(progress=progress, message=f"Đang tải bản {version}: {progress}%")
                handle.flush()
                os.fsync(handle.fileno())
            if expected_size and written != expected_size:
                raise ValueError(f"Kích thước file không khớp ({written}/{expected_size} byte)")
            actual_sha = digest.hexdigest().lower()
            if actual_sha != expected_sha:
                raise ValueError("SHA-256 của file cập nhật không khớp")
            with open(part_path, "rb") as handle:
                if handle.read(2) != b"MZ":
                    raise ValueError("File tải về không phải chương trình Windows hợp lệ")
            os.replace(part_path, ready_path)
            pending = {
                "version": version,
                "sha256": expected_sha,
                "size": written,
                "ready_path": ready_path,
                "target_path": self.executable_path,
                "created_at": datetime.now().isoformat(timespec="seconds"),
            }
            _atomic_json_write(self.pending_path, pending)
            self._available_release = None
            self._set_status(
                state="ready",
                progress=100,
                message=f"Đã tải bản {version}; sẽ cài ở lần mở ứng dụng tiếp theo.",
                pending=True,
            )
            logger.success(f"Đã tải và xác minh bản {version}; sẽ cài ở lần mở tiếp theo.", "UPDATE")
        except Exception:
            try:
                if os.path.exists(part_path):
                    os.remove(part_path)
            except OSError:
                pass
            raise

    @staticmethod
    def _parse_sha256(text: str) -> str:
        for line in (text or "").splitlines():
            parts = line.strip().split()
            if not parts:
                continue
            candidate = parts[0].lower()
            if re.fullmatch(r"[0-9a-f]{64}", candidate):
                if len(parts) > 1 and parts[-1].lstrip("*") != EXE_NAME:
                    continue
                return candidate
        raise ValueError("File SHA-256 không hợp lệ")

    def is_update_applying(self) -> bool:
        return os.path.isfile(self.applying_path)

    def recover_stale_applying(self, max_age_seconds: int = 10 * 60) -> str:
        """Recover an abandoned handoff marker left by a crashed helper.

        Returns ``active``, ``retry``, ``recovered`` or ``none``.
        """
        if not os.path.isfile(self.applying_path):
            return "none"
        try:
            age = time.time() - os.path.getmtime(self.applying_path)
        except OSError:
            return "active"
        if age < max_age_seconds:
            return "active"
        applying = _read_json(self.applying_path) or {}
        expected_version = normalize_version(str(applying.get("version") or ""))
        ready_path = str(applying.get("ready_path") or "")
        expected_sha = str(applying.get("sha256") or "").lower()
        if expected_version == normalize_version(self.current_version):
            try:
                os.remove(self.applying_path)
            except OSError:
                pass
            _atomic_json_write(self.result_path, {
                "success": True,
                "message": f"Đã xác nhận bản {expected_version} sau khi phục hồi trạng thái cập nhật.",
                "version": expected_version,
                "time": datetime.now().isoformat(timespec="seconds"),
            })
            return "recovered"
        if ready_path and os.path.isfile(ready_path):
            try:
                if sha256_file(ready_path) == expected_sha:
                    os.replace(self.applying_path, self.pending_path)
                    return "retry"
            except OSError:
                pass
        try:
            os.remove(self.applying_path)
        except OSError:
            pass
        _atomic_json_write(self.result_path, {
            "success": False,
            "message": "Lần cập nhật trước bị gián đoạn; ứng dụng tiếp tục dùng bản hiện tại.",
            "version": expected_version,
            "time": datetime.now().isoformat(timespec="seconds"),
        })
        return "recovered"

    def launch_pending_installer(self) -> bool:
        """Launch the detached helper and return True when this process must exit."""
        if not self.frozen:
            return False
        pending = _read_json(self.pending_path)
        if not pending:
            return False
        version = normalize_version(str(pending.get("version") or ""))
        ready_path = os.path.abspath(str(pending.get("ready_path") or ""))
        target_path = os.path.abspath(str(pending.get("target_path") or ""))
        expected_sha = str(pending.get("sha256") or "").lower()
        current = parse_version(self.current_version)
        latest = parse_version(version or "")
        if not version or current is None or latest is None or latest <= current:
            self._discard_pending("Bản chờ cập nhật không còn mới hơn bản đang chạy.")
            return False
        if os.path.normcase(target_path) != os.path.normcase(self.executable_path):
            self._discard_pending("Đường dẫn ứng dụng đã thay đổi; bỏ bản cập nhật chờ.")
            return False
        if not os.path.isfile(ready_path) or sha256_file(ready_path) != expected_sha:
            self._discard_pending("File cập nhật chờ bị thiếu hoặc sai SHA-256.")
            return False

        os.makedirs(self.update_dir, exist_ok=True)
        self._write_helper_script()
        if os.path.exists(self.applying_path):
            os.remove(self.applying_path)
        os.replace(self.pending_path, self.applying_path)
        backup_path = self.executable_path + ".update-backup.exe"
        args = [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-WindowStyle", "Hidden",
            "-File", self.helper_path,
            "-ParentPid", str(os.getpid()),
            "-CurrentExe", self.executable_path,
            "-StagedExe", ready_path,
            "-BackupExe", backup_path,
            "-ExpectedVersion", version,
            "-ExpectedSha256", expected_sha,
            "-ApplyingManifest", self.applying_path,
            "-ResultPath", self.result_path,
        ]
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
        try:
            subprocess.Popen(
                args,
                cwd=os.path.dirname(self.executable_path),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                creationflags=creationflags,
            )
            logger.info(f"Đang áp dụng bản {version}; ứng dụng sẽ tự mở lại.", "UPDATE")
            return True
        except Exception as exc:
            os.replace(self.applying_path, self.pending_path)
            logger.error(f"Không khởi chạy được trình cập nhật: {exc}", "UPDATE")
            return False

    def _discard_pending(self, reason: str) -> None:
        pending = _read_json(self.pending_path) or {}
        ready_path = str(pending.get("ready_path") or "")
        for path in (self.pending_path, ready_path):
            try:
                if path and os.path.isfile(path):
                    os.remove(path)
            except OSError:
                pass
        logger.warning(reason, "UPDATE")

    def _write_helper_script(self) -> None:
        os.makedirs(self.update_dir, exist_ok=True)
        with open(self.helper_path, "w", encoding="utf-8-sig", newline="\r\n") as handle:
            handle.write(POWERSHELL_UPDATE_HELPER)


POWERSHELL_UPDATE_HELPER = r'''param(
    [Parameter(Mandatory=$true)][int]$ParentPid,
    [Parameter(Mandatory=$true)][string]$CurrentExe,
    [Parameter(Mandatory=$true)][string]$StagedExe,
    [Parameter(Mandatory=$true)][string]$BackupExe,
    [Parameter(Mandatory=$true)][string]$ExpectedVersion,
    [Parameter(Mandatory=$true)][string]$ExpectedSha256,
    [Parameter(Mandatory=$true)][string]$ApplyingManifest,
    [Parameter(Mandatory=$true)][string]$ResultPath,
    [switch]$Elevated
)

$ErrorActionPreference = 'Stop'
$UpdateDir = Split-Path -Parent $ApplyingManifest
$LogPath = Join-Path $UpdateDir 'apply_update.log'

function Write-UpdateLog([string]$Message) {
    $stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    Add-Content -LiteralPath $LogPath -Value "[$stamp] $Message" -Encoding UTF8
}

function Save-Result([bool]$Success, [string]$Message) {
    $payload = @{ success = $Success; message = $Message; version = $ExpectedVersion; time = (Get-Date).ToString('s') }
    $payload | ConvertTo-Json | Set-Content -LiteralPath $ResultPath -Encoding UTF8
}

function Quote-Argument([string]$Value) {
    return '"' + ($Value -replace '"', '\"') + '"'
}

try {
    if ($ParentPid -gt 0) {
        Write-UpdateLog "Cho tien trinh cu PID $ParentPid thoat."
        try { Wait-Process -Id $ParentPid -Timeout 60 -ErrorAction Stop } catch {
            if (Get-Process -Id $ParentPid -ErrorAction SilentlyContinue) {
                throw "Tien trinh cu khong thoat sau 60 giay."
            }
        }
    }

    if (-not $Elevated) {
        $probe = Join-Path (Split-Path -Parent $CurrentExe) ('.auto-update-probe-' + $PID + '.tmp')
        try {
            [System.IO.File]::WriteAllText($probe, 'probe')
            Remove-Item -LiteralPath $probe -Force
        } catch {
            Write-UpdateLog 'Thu muc can quyen quan tri; dang yeu cau UAC.'
            $scriptArgs = @(
                '-NoProfile', '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden', '-File', (Quote-Argument $PSCommandPath),
                '-ParentPid', '0', '-CurrentExe', (Quote-Argument $CurrentExe), '-StagedExe', (Quote-Argument $StagedExe),
                '-BackupExe', (Quote-Argument $BackupExe), '-ExpectedVersion', (Quote-Argument $ExpectedVersion),
                '-ExpectedSha256', (Quote-Argument $ExpectedSha256), '-ApplyingManifest', (Quote-Argument $ApplyingManifest),
                '-ResultPath', (Quote-Argument $ResultPath), '-Elevated'
            )
            Start-Process -FilePath 'powershell.exe' -Verb RunAs -ArgumentList ($scriptArgs -join ' ')
            exit 0
        }
    }

    if (-not (Test-Path -LiteralPath $StagedExe)) { throw 'Khong tim thay file cap nhat da tai.' }
    $actualSha = (Get-FileHash -LiteralPath $StagedExe -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualSha -ne $ExpectedSha256.ToLowerInvariant()) { throw 'SHA-256 khong khop khi bat dau cai dat.' }

    if (Test-Path -LiteralPath $BackupExe) { Remove-Item -LiteralPath $BackupExe -Force }
    Move-Item -LiteralPath $CurrentExe -Destination $BackupExe -Force
    try {
        Move-Item -LiteralPath $StagedExe -Destination $CurrentExe -Force
    } catch {
        Move-Item -LiteralPath $BackupExe -Destination $CurrentExe -Force
        throw
    }

    Write-UpdateLog "Da thay file; khoi dong ban $ExpectedVersion."
    $newProcess = Start-Process -FilePath $CurrentExe -ArgumentList @('--post-update', $ExpectedVersion) -WorkingDirectory (Split-Path -Parent $CurrentExe) -PassThru
    $healthy = $false
    $deadline = (Get-Date).AddSeconds(75)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 750
        if ($newProcess.HasExited) { break }
        try {
            $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/system/version' -TimeoutSec 2
            if ([string]$health.version -eq $ExpectedVersion) { $healthy = $true; break }
        } catch { }
    }

    if (-not $healthy) {
        Write-UpdateLog 'Ban moi khong vuot qua kiem tra suc khoe; rollback.'
        if (-not $newProcess.HasExited) {
            Stop-Process -Id $newProcess.Id -Force -ErrorAction SilentlyContinue
            try { Wait-Process -Id $newProcess.Id -Timeout 15 -ErrorAction SilentlyContinue } catch { }
        }
        if (Test-Path -LiteralPath $CurrentExe) { Remove-Item -LiteralPath $CurrentExe -Force }
        Move-Item -LiteralPath $BackupExe -Destination $CurrentExe -Force
        Remove-Item -LiteralPath $ApplyingManifest -Force -ErrorAction SilentlyContinue
        Save-Result $false "Ban $ExpectedVersion khoi dong khong thanh cong; da phuc hoi ban cu."
        Start-Process -FilePath $CurrentExe -ArgumentList @('--update-rollback') -WorkingDirectory (Split-Path -Parent $CurrentExe)
        exit 1
    }

    Remove-Item -LiteralPath $BackupExe -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $ApplyingManifest -Force -ErrorAction SilentlyContinue
    Save-Result $true "Da cap nhat thanh cong len ban $ExpectedVersion."
    Write-UpdateLog "Cap nhat thanh cong len $ExpectedVersion."
    exit 0
} catch {
    $message = $_.Exception.Message
    Write-UpdateLog "LOI: $message"
    try {
        if ((-not (Test-Path -LiteralPath $CurrentExe)) -and (Test-Path -LiteralPath $BackupExe)) {
            Move-Item -LiteralPath $BackupExe -Destination $CurrentExe -Force
        }
        Remove-Item -LiteralPath $ApplyingManifest -Force -ErrorAction SilentlyContinue
        Save-Result $false "Cap nhat khong thanh cong: $message"
        if (Test-Path -LiteralPath $CurrentExe) {
            Start-Process -FilePath $CurrentExe -ArgumentList @('--update-rollback') -WorkingDirectory (Split-Path -Parent $CurrentExe)
        }
    } catch { }
    exit 1
}
'''


update_manager = UpdateManager()
