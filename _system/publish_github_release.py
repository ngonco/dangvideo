"""Dong goi exe + day ma nguon + tao GitHub Release.

Cach dung (sau nay chi chay file nay):
  python _system/publish_github_release.py
  publish_github_release.bat

Mac dinh: tang so giua TRUOC khi dong goi (1.2.0 -> 1.3.0 -> 1.4.0).
Tag da co tren GitHub thi tang tiep den khi trong. Khong ghi de.
--tag chi dung khi muon chi dinh so cu the (khong tu tang).

Khong commit: .exe, config.json, .env, data.db, browser_profiles.
Khong in token GitHub.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REPO_SLUG = "ngonco/dangvideo"
REQUIRED_BRANCH = "main"
EXE_NAME = "Tu_dong_dang_video.exe"
LATEST_URL = "https://github.com/ngonco/dangvideo/releases/latest"

FORBIDDEN_NAMES = {"tu_dong_dang_video.exe", "config.json", ".env", "data.db"}
FORBIDDEN_PATH_PARTS = ("browser_profiles/", "browser_profiles\\")

DEFAULT_NOTES = """Tai Tu_dong_dang_video.exe, click dup de chay.

Mac dinh: tat tieng trinh duyet Playwright; an cua so khi tai/dang.
Dashboard co nut TAT TIENG va HIEN THI QUA TRINH DANG.
Nut Mo Trinh Duyet Dang Nhap van luon mo cua so.

Khong kem cookie, browser_profiles, .env, data.db hay mat khau HatBuiNho.
Lan dau: dien tai khoan HatBuiNho tren Dashboard, dang nhap 4 kenh mot lan.
"""


def _print(msg: str) -> None:
    print(msg, flush=True)


def die(msg: str, code: int = 1) -> None:
    _print("LOI: " + msg)
    sys.exit(code)


def run(cmd: list[str], cwd: str = ROOT, check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=cwd,
        check=check,
        capture_output=capture,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def version_path() -> str:
    return os.path.join(HERE, "VERSION")


def read_version_file() -> str:
    path = version_path()
    if not os.path.isfile(path):
        die("Khong tim thay _system/VERSION")
    value = open(path, encoding="utf-8").read().strip().split()[0]
    if not value:
        die("_system/VERSION trong")
    return value


def parse_semver(raw: str) -> tuple[int, int, int]:
    value = raw.strip()
    if value.lower().startswith("v"):
        value = value[1:]
    parts = (value.split(".") + ["0", "0", "0"])[:3]
    nums = []
    for p in parts:
        try:
            nums.append(int(p))
        except ValueError:
            nums.append(0)
    return nums[0], nums[1], nums[2]


def format_semver(major: int, minor: int, patch: int) -> str:
    return f"{major}.{minor}.{patch}"


def bump_minor(ver: str) -> str:
    major, minor, _patch = parse_semver(ver)
    return format_semver(major, minor + 1, 0)


def write_version(ver: str) -> None:
    with open(version_path(), "w", encoding="utf-8", newline="\n") as f:
        f.write(ver.strip() + "\n")
    html_path = os.path.join(HERE, "static", "index.html")
    if os.path.isfile(html_path):
        text = open(html_path, encoding="utf-8").read()
        updated, n = re.subn(
            r'(id="appVersion">Bản\s+)[^<]+',
            r"\g<1>" + ver,
            text,
            count=1,
        )
        if n:
            open(html_path, "w", encoding="utf-8", newline="\n").write(updated)


def normalize_tag(raw: str | None) -> str:
    value = (raw or "").strip() or read_version_file()
    if value.lower().startswith("v"):
        return "v" + value[1:]
    return "v" + value


def pick_next_tag(token: str) -> tuple[str, str]:
    """Tang so giua, roi tang tiep neu tag GitHub da ton tai. Tra ve (version, tag)."""
    ver = bump_minor(read_version_file())
    tag = "v" + ver
    for _ in range(50):
        if not release_exists(token, tag):
            return ver, tag
        _print(f"Tag {tag} da co Release, tang so giua...")
        ver = bump_minor(ver)
        tag = "v" + ver
    die("Khong tim duoc tag trong sau 50 lan tang minor.")
    return ver, tag


def git_out(*args: str) -> str:
    res = run(["git", *args], capture=True)
    return (res.stdout or "").strip()


def assert_repo_and_branch() -> None:
    if not os.path.isdir(os.path.join(ROOT, ".git")):
        die("Khong phai git repo: " + ROOT)
    remote = git_out("remote", "get-url", "origin")
    if REPO_SLUG not in remote.replace("\\", "/"):
        die(f"origin phai la {REPO_SLUG}, hien tai: {remote}")
    branch = git_out("rev-parse", "--abbrev-ref", "HEAD")
    if branch != REQUIRED_BRANCH:
        die(f"Phai o nhanh {REQUIRED_BRANCH}, hien tai: {branch}")


def path_forbidden(rel: str) -> bool:
    p = rel.replace("\\", "/").lstrip("./")
    name = os.path.basename(p).lower()
    if name in FORBIDDEN_NAMES:
        return True
    lower = p.lower()
    return any(part.replace("\\", "/") in lower for part in ("browser_profiles/",))


def staged_files() -> list[str]:
    out = git_out("diff", "--cached", "--name-only", "-z")
    if not out:
        return []
    return [p for p in out.split("\0") if p]


def refuse_leaks(files: list[str]) -> None:
    bad = [f for f in files if path_forbidden(f)]
    if bad:
        die("Tu choi commit file cam leak:\n  " + "\n  ".join(bad))


def build_exe() -> str:
    _print("=== Dong goi exe (PyInstaller) ===")
    rc = subprocess.call([sys.executable, os.path.join(HERE, "build_exe.py")], cwd=HERE)
    if rc != 0:
        die(f"build_exe.py that bai (exit {rc})")
    exe = os.path.join(ROOT, EXE_NAME)
    if not os.path.isfile(exe):
        die("Khong tim thay " + exe)
    size_mb = os.path.getsize(exe) / (1024 * 1024)
    _print(f"OK exe: {exe} ({size_mb:.1f} MB)")
    return exe


def commit_and_push(tag: str) -> None:
    _print("=== Git add / commit / push ma nguon ===")
    run(["git", "add", "-A"])
    staged = staged_files()
    refuse_leaks(staged)
    if staged:
        msg = f"Release {tag}: dong goi exe qua GitHub Releases"
        run(["git", "commit", "-m", msg])
        _print("Da commit: " + msg)
    else:
        _print("Khong co thay doi ma nguon de commit.")
    run(["git", "push", "origin", REQUIRED_BRANCH])
    _print("Da push origin " + REQUIRED_BRANCH)


def github_token() -> str:
    env = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if env:
        return env.strip()
    payload = "protocol=https\nhost=github.com\n\n"
    res = subprocess.run(
        ["git", "credential", "fill"],
        input=payload,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=ROOT,
    )
    if res.returncode != 0:
        die("Khong lay duoc GitHub credential (cai gh hoac dang nhap git).")
    token = ""
    for line in (res.stdout or "").splitlines():
        if line.startswith("password="):
            token = line.split("=", 1)[1].strip()
            break
    if not token:
        die("Git credential khong co password/token.")
    return token


def api_request(method: str, url: str, token: str, data: bytes | None = None, content_type: str = "application/json") -> tuple[int, dict | str]:
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "dangvideo-publish-release",
        },
    )
    if data is not None:
        req.add_header("Content-Type", content_type)
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            body: dict | str
            try:
                body = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                body = raw
            return resp.status, body
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            body = raw
        return e.code, body


def release_exists(token: str, tag: str) -> bool:
    code, _ = api_request("GET", f"https://api.github.com/repos/{REPO_SLUG}/releases/tags/{tag}", token)
    return code == 200


def create_release_with_gh(tag: str, exe: str, notes: str) -> None:
    cmd = [
        "gh", "release", "create", tag, exe,
        "--repo", REPO_SLUG,
        "--title", f"{tag} — {EXE_NAME}",
        "--notes", notes,
    ]
    rc = subprocess.call(cmd, cwd=ROOT)
    if rc != 0:
        die(f"gh release create that bai (exit {rc})")


def create_release_with_api(tag: str, exe: str, notes: str, token: str) -> None:
    body = json.dumps({
        "tag_name": tag,
        "name": f"{tag} — {EXE_NAME}",
        "body": notes,
        "draft": False,
        "prerelease": False,
        "target_commitish": REQUIRED_BRANCH,
    }).encode("utf-8")
    code, meta = api_request("POST", f"https://api.github.com/repos/{REPO_SLUG}/releases", token, data=body)
    if code not in (200, 201) or not isinstance(meta, dict):
        die(f"Tao GitHub Release that bai (HTTP {code}).")
    upload = str(meta.get("upload_url") or "").split("{")[0]
    if not upload:
        die("Release khong co upload_url.")
    data = open(exe, "rb").read()
    _print(f"Dang tai {EXE_NAME} ({len(data)} bytes) len Release {tag}...")
    up_url = upload + f"?name={EXE_NAME}"
    code, _ = api_request(
        "POST",
        up_url,
        token,
        data=data,
        content_type="application/octet-stream",
    )
    if code not in (200, 201):
        die(f"Tai exe len Release that bai (HTTP {code}).")


def publish_release(tag: str, exe: str, notes: str) -> None:
    _print("=== GitHub Release ===")
    token = github_token()
    if release_exists(token, tag):
        die(f"Tag {tag} da co Release. Tang so trong _system/VERSION roi chay lai. Khong ghi de.")
    gh = shutil_which("gh")
    if gh:
        try:
            create_release_with_gh(tag, exe, notes)
            return
        except Exception:
            _print("gh khong dung duoc, chuyen sang GitHub API.")
    create_release_with_api(tag, exe, notes, token)


def shutil_which(name: str) -> str | None:
    from shutil import which
    return which(name)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dong goi exe va tao GitHub Release.")
    parser.add_argument("tag", nargs="?", help="Chi dinh tag, vi du v1.3.0 (bo qua tu tang)")
    parser.add_argument("--tag", dest="tag_opt", help="Chi dinh tag, vi du v1.3.0")
    parser.add_argument("--notes", default=DEFAULT_NOTES, help="Mo ta Release")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    os.chdir(ROOT)
    assert_repo_and_branch()
    explicit = (args.tag_opt or args.tag or "").strip()
    token = github_token()
    if explicit:
        tag = normalize_tag(explicit)
        ver = tag[1:] if tag.lower().startswith("v") else tag
        if release_exists(token, tag):
            die(f"Tag {tag} da co Release. Bo --tag de script tu tang so giua.")
        write_version(ver)
        _print(f"Dung tag chi dinh {tag}. Ghi VERSION={ver} truoc khi dong goi.")
    else:
        ver, tag = pick_next_tag(token)
        write_version(ver)
        _print(f"Tu tang VERSION -> {ver} (tag {tag}) truoc khi dong goi.")
    _print(f"Phat hanh {tag} cho {REPO_SLUG}")
    exe = build_exe()
    commit_and_push(tag)
    publish_release(tag, exe, args.notes.strip() + "\n")
    _print("")
    _print("XONG. User tai exe tai:")
    _print("  " + LATEST_URL)
    _print(f"  https://github.com/{REPO_SLUG}/releases/download/{tag}/{EXE_NAME}")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        die(f"lenh that bai: {e}")
