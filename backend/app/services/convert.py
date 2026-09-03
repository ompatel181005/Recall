"""Best-effort PowerPoint → PDF conversion.

This is optional. Slide *text* is read straight out of a .pptx by
services/slides.py with no external tool, so notes and search work everywhere.
A PDF is only needed to preview the deck in the browser, and to read legacy
binary .ppt at all.

Two converters are tried, in order of how well they behave headlessly:

  LibreOffice — cross-platform, genuinely headless, no user session needed.
  PowerPoint  — Windows only, drives the installed Office via COM.

Both are external processes that can hang, so every call is bounded by a
timeout and every failure returns None rather than raising: a deck that will not
convert should still upload, index and be summarised.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

CONVERT_TIMEOUT_SECONDS = 180

_CREATE_NO_WINDOW = 0x08000000  # keep console windows from flashing on Windows

# PowerPoint's PDF export format id, and the flag that stops it opening a window.
_PPT_SAVE_AS_PDF = 32


def _libreoffice() -> str | None:
    found = shutil.which("soffice") or shutil.which("libreoffice")
    if found:
        return found
    for candidate in (
        Path(os.environ.get("ProgramFiles", "")) / "LibreOffice/program/soffice.exe",
        Path(os.environ.get("ProgramFiles(x86)", "")) / "LibreOffice/program/soffice.exe",
    ):
        if candidate.is_file():
            return str(candidate)
    return None


def _powerpoint() -> str | None:
    """PowerPoint is driven through PowerShell rather than pywin32, so Windows
    users need no extra Python dependency for a feature that is optional."""
    if os.name != "nt":
        return None
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if not powershell:
        return None
    for root in (os.environ.get("ProgramFiles", ""), os.environ.get("ProgramFiles(x86)", "")):
        if root and list(Path(root).glob("Microsoft Office/root/Office*/POWERPNT.EXE")):
            return powershell
    return None


def converter_name() -> str | None:
    """Which converter is usable, for /api/health and for error messages."""
    if _libreoffice():
        return "libreoffice"
    if _powerpoint():
        return "powerpoint"
    return None


def available() -> bool:
    return converter_name() is not None


def _run(args: list[str]) -> bool:
    try:
        done = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=CONVERT_TIMEOUT_SECONDS,
            creationflags=_CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        return done.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def _convert_libreoffice(binary: str, source: Path, out_dir: Path) -> Path | None:
    # LibreOffice writes <stem>.pdf into --outdir. A private profile keeps it
    # from colliding with a copy the user has open.
    with tempfile.TemporaryDirectory() as profile:
        ok = _run([
            binary,
            "--headless",
            "--norestore",
            f"-env:UserInstallation=file:///{Path(profile).as_posix()}",
            "--convert-to", "pdf",
            "--outdir", str(out_dir),
            str(source),
        ])
    result = out_dir / f"{source.stem}.pdf"
    return result if ok and result.exists() else None


def _convert_powerpoint(powershell: str, source: Path, out_dir: Path) -> Path | None:
    result = out_dir / f"{source.stem}.pdf"
    # Presentations.Open with WithWindow:=0 keeps the UI hidden. Quit in a
    # finally so a failure cannot strand a PowerPoint process holding the file.
    script = f"""
$ErrorActionPreference = 'Stop'
$app = New-Object -ComObject PowerPoint.Application
try {{
    $deck = $app.Presentations.Open('{source}', $true, $false, [Microsoft.Office.Core.MsoTriState]::msoFalse)
    try {{ $deck.SaveAs('{result}', {_PPT_SAVE_AS_PDF}) }} finally {{ $deck.Close() }}
}} finally {{ $app.Quit() }}
"""
    ok = _run([powershell, "-NoProfile", "-NonInteractive", "-Command", script])
    return result if ok and result.exists() else None


def to_pdf(source: Path, out_dir: Path) -> Path | None:
    """Convert a presentation to PDF beside it. None if no converter is
    available or the conversion failed — callers must cope with that."""
    binary = _libreoffice()
    if binary:
        converted = _convert_libreoffice(binary, source, out_dir)
        if converted:
            return converted

    powershell = _powerpoint()
    if powershell:
        return _convert_powerpoint(powershell, source, out_dir)

    return None
