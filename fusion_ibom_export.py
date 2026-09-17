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
InteractiveHtmlBom must be installed for a standalone Python on your
system PATH -- NOT for Fusion's own bundled Python. Fusion embeds Python
inside its own process (sys.executable resolves to Fusion360.exe itself,
not a python.exe), so there's no pip and no Scripts/bin folder to install
into there, and even if there were, Fusion replaces its entire bundled-
Python folder on every update, so anything installed there wouldn't
survive an update anyway. Install it once with:

    Windows:      py -m pip install InteractiveHtmlBom wxpython jsonschema
    Mac/Linux:    python3 -m pip install InteractiveHtmlBom wxpython jsonschema

(Thanks to Funkenjaeger for catching and diagnosing this.)
"""

import os
import shutil
import subprocess
import tempfile
import traceback
from typing import Optional

import adsk.core
import adsk.electron

# --- Customize the generated BOM here ---
# Add any extra generate_interactive_bom command-line flags you want on
# every run. --dest-dir and --name-format are already handled for you
# (see run(), below) -- don't add those here. Some commonly wanted ones:
#
#   "--include-tracks"              draw copper traces on the board view
#   "--include-nets"                include net names in the BOM
#   "--dark-mode"                   dark color scheme
#   "--extra-fields", "MPN,Supplier"   pull extra columns from component
#                                       attributes (comma-separated, no
#                                       spaces around the comma)
#
# Full list: run `generate_interactive_bom --help` in a terminal, or see
# https://github.com/openscopeproject/InteractiveHtmlBom/wiki/Usage
#
# We deliberately don't route through ibom's own --show-dialog option
# for this instead of a static list: in dialog mode ibom ignores
# --dest-dir/--name-format and uses its own defaults, doesn't report
# back if the user cancels, and leaves extra temp files in the output
# folder. A fixed, edited-by-hand list avoids all three problems, at the
# cost of needing a text-editor change instead of a checkbox.
EXTRA_IBOM_ARGS: list = ["--include-tracks", "--include-nets"]


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

        ibom_cmd = _find_ibom_command()
        if ibom_cmd is None:
            install_cmd = (
                "py -m pip install InteractiveHtmlBom wxpython jsonschema"
                if os.name == "nt"
                else "python3 -m pip install InteractiveHtmlBom wxpython jsonschema"
            )
            ui.messageBox(
                "InteractiveHtmlBom isn't installed where this script can find it.\n\n"
                "Install it once, using a standalone Python on your system PATH "
                "(not Fusion's own bundled Python) -- from a normal terminal:\n\n"
                f"  {install_cmd}\n\n"
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
            ] + EXTRA_IBOM_ARGS,
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


def _find_ibom_command() -> Optional[list]:
    """
    Locate the `generate_interactive_bom` console script on the system
    PATH.

    We deliberately do NOT look next to sys.executable. Inside Fusion,
    sys.executable resolves to Fusion360.exe itself -- Fusion embeds
    Python in its own process rather than launching a separate python.exe
    -- so there's no Scripts/bin folder to find there at all, and the
    check silently never matched anything. Even for a real interpreter,
    a package installed into Fusion's bundled Python wouldn't survive an
    update anyway, since Fusion replaces that whole folder each time. A
    standalone system Python that's on PATH is the only combination that
    actually works, which is exactly what shutil.which() checks for.

    (Diagnosed by Funkenjaeger -- see this repo's issue tracker.)
    """
    found = shutil.which("generate_interactive_bom")
    if found:
        return [found]
    return None
