"""Portable subprocess helpers. Prefer native tools; use an installed WSL distro on Windows."""
from __future__ import annotations

import functools
import os
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


@functools.lru_cache(maxsize=None)
def tool_command(name: str) -> tuple[str, ...] | None:
    override = os.environ.get(name.upper().replace('-', '_'))
    if override:
        return (override,)
    native = shutil.which(name)
    if native:
        return (native,)
    if os.name == 'nt' and shutil.which('wsl'):
        distro = os.environ.get('NEUROTILE_WSL_DISTRO', 'Ubuntu')
        prefix = ('wsl', '-d', distro, '--')
        try:
            probe = subprocess.run([*prefix, 'which', name], capture_output=True,
                                   timeout=20, text=True)
            if probe.returncode == 0:
                return (*prefix, name)
        except (OSError, subprocess.TimeoutExpired):
            pass
    return None


def tool_available(name: str) -> bool:
    return tool_command(name) is not None


def _linux_arg(value: object) -> str:
    value = str(value)
    # Also handles simulator plusargs, e.g. +INPUT=D:\\project\\input.hex.
    return re.sub(r'([A-Za-z]):[\\/]',
                  lambda m: '/mnt/' + m.group(1).lower() + '/', value).replace('\\', '/')


def run_tool(name: str, args=(), cwd: Path = ROOT, timeout: int = 180,
             check: bool = True) -> subprocess.CompletedProcess:
    command = tool_command(name)
    if command is None:
        raise RuntimeError(f'Missing {name}. See README tool installation instructions.')
    is_wsl = Path(command[0]).stem.lower() == 'wsl'
    argv = [_linux_arg(a) if is_wsl else str(a) for a in args]
    result = subprocess.run([*command, *argv], cwd=str(cwd), capture_output=True,
                            text=True, timeout=timeout, encoding='utf-8', errors='replace')
    if check and result.returncode:
        raise RuntimeError(f'{name} failed ({result.returncode}):\n{result.stdout}\n{result.stderr}')
    return result


def write_hex(path: Path, values, width: int = 8) -> None:
    mask = (1 << width) - 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(f'{int(x) & mask:0{width // 4}x}\n' for x in values), encoding='ascii')
