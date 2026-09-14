"""
Export the currently open Fusion Electronics board to an EAGLE-compatible
.brd file and generate an Interactive HTML BOM from it.

Usage
-----
1. Open your PCB in Fusion 360's Electronics workspace (Board editor).
2. Run this file from the Scripts and Add-ins dialog (Scripts tab -> Run).
3. Choose an output folder when prompted.

Requirements
------------
InteractiveHtmlBom must already be installed for the Python interpreter
Fusion uses to run scripts. This script does not install it for you --
silently modifying a host application's bundled interpreter is surprising
behavior for a script pulled from GitHub. Install it once with:

    pip install InteractiveHtmlBom wxpython jsonschema

(Run that using the same python executable Fusion uses -- this script's
error message will print the exact path if it can't find the package.)
"""

import os
import shutil
import subprocess
import sys
import tempfile
import traceback
from typing import Optional

import adsk.core
import adsk.electron


def run(context):
    app = adsk.core.Application.get()
    ui = app.userInterface
    temp_dir: Optional[str] = None

    try:
        board = adsk.electron.Board.cast(app.activeProduct)
        if board is None:
            ui.messageBox(
                "Open a PCB in the Electronics workspace's Board editor, "
                "then run this script again."
            )
            return

        ibom_cmd = _find_ibom_command(sys.executable)
        if ibom_cmd is None:
            ui.messageBox(
                "InteractiveHtmlBom isn't installed for Fusion's Python.\n\n"
                "Install it once from a terminal with:\n\n"
                f'  "{sys.executable}" -m pip install '
                "InteractiveHtmlBom wxpython jsonschema\n\n"
                "then run this script again."
            )
            return

        folder_dialog = ui.createFolderDialog()
        folder_dialog.title = "Choose a folder for the generated BOM"
        if folder_dialog.showDialog() != adsk.core.DialogResults.DialogOK:
            return
        out_dir = folder_dialog.folder

        design_name = _safe_filename(board.name) or "board"
        temp_dir = tempfile.mkdtemp(prefix="fusion_ibom_")
        brd_path = os.path.join(temp_dir, f"{design_name}.brd")

        if not _export_brd(board, brd_path):
            ui.messageBox(
                "Fusion could not export this board to EAGLE .brd format. "
                "Check the Text Commands window for details."
            )
            return

        result = subprocess.run(
            ibom_cmd + [
                brd_path,
                "--dest-dir", out_dir,
                "--name-format", design_name,
                "--no-browser",
            ],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )

        if result.returncode == 0:
            ui.messageBox(
                f"BOM generated for {board.elements.count} component(s).\n\n"
                f"Saved to: {os.path.join(out_dir, design_name + '.html')}"
            )
        else:
            ui.messageBox(f"generate_interactive_bom failed:\n\n{result.stderr}")

    except Exception:
        ui.messageBox(f"Unexpected error:\n\n{traceback.format_exc()}")
    finally:
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)


def _safe_filename(name: str) -> str:
    """Strip the file extension and replace characters unsafe in filenames."""
    stem = os.path.splitext(name)[0] if name else ""
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in stem)


def _export_brd(board, out_path: str) -> bool:
    """Export `board` to an EAGLE 9.6.2 .brd file at `out_path`."""
    options = board.exportManager.createEagleBrdExportOptions(out_path)
    if options is None:
        return False
    return bool(board.exportManager.execute(options)) and os.path.exists(out_path)


def _find_ibom_command(python_exe: str) -> Optional[list]:
    """
    Locate a working `generate_interactive_bom` invocation for `python_exe`.

    pip installs the console-script binary next to the interpreter it was
    installed for (Scripts/ on Windows, bin/ on POSIX). That directory is
    usually NOT on PATH when a subprocess is spawned from inside a host
    application like Fusion, so we build the path directly instead of
    relying on PATH -- falling back to PATH only if that check fails, e.g.
    for a manually-managed environment.
    """
    base = os.path.dirname(python_exe)
    candidate = os.path.join(
        base, "Scripts" if os.name == "nt" else "bin",
        "generate_interactive_bom.exe" if os.name == "nt" else "generate_interactive_bom",
    )
    if os.path.exists(candidate):
        return [candidate]

    found = shutil.which("generate_interactive_bom")
    if found:
        return [found]

    return None
