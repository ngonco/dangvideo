"""Hidden Windows startup launcher; restart crashes, honor normal user exit."""
import os
import subprocess
import sys
import time
from pathlib import Path


def supervise(executable):
    executable = Path(executable).resolve()
    if executable.name != 'Tu_dong_dang_video.exe' or not executable.is_file():
        return
    # No shell string interpolation, and no process is killed by this launcher.
    failures = 0
    while failures < 5:
        started = time.monotonic()
        process = subprocess.Popen([str(executable)],cwd=str(executable.parent),creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        code = process.wait()
        if code == 0:
            return
        failures = 1 if time.monotonic()-started > 300 else failures+1
        time.sleep(min(60,10*failures))


if __name__ == '__main__' and len(sys.argv) == 2:
    supervise(sys.argv[1])
