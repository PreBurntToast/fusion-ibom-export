# fusion-ibom-export

Export the board open in Fusion 360's Electronics workspace to an
EAGLE-compatible `.brd` file and generate an
[Interactive HTML BOM](https://github.com/openscopeproject/InteractiveHtmlBom)
from it, without leaving Fusion.

## Two ways to use this

| | [`fusion_ibom_export.py`](fusion_ibom_export.py) | [`PcbIbomExport/`](PcbIbomExport/) |
|---|---|---|
| Type | Plain script | Add-in with a toolbar button |
| Setup | Copy one file in | Folder/file naming rules apply — see below |
| Run | From *Scripts and Add-ins → Scripts*, each time | Click a permanent button in a "BOM Export" tab |
| Best for | Zero-fuss, works everywhere | One-click convenience, don't mind a fussier one-time install |

Both do the exact same export + BOM generation underneath. Pick whichever
fits how you work.

## What this does

Fusion 360's Electronics API (`adsk.electron`) can export the currently open
PCB straight to EAGLE 9.6.2 `.brd` format. InteractiveHtmlBom already parses
`.brd` files natively. This script wires the two together: export, then call
`generate_interactive_bom` for you, in one step from Fusion's Scripts menu.

## Requirements

- Fusion 360 with the Electronics workspace. Fusion's Electronics API is
  currently in **preview** — see
  [Autodesk's docs](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/ElectronicsIntro.htm).
- [InteractiveHtmlBom](https://github.com/openscopeproject/InteractiveHtmlBom)
  installed for the same Python interpreter Fusion uses to run scripts:

  ```
  pip install InteractiveHtmlBom wxpython jsonschema
  ```

  The script will tell you the exact command (with the right interpreter
  path) if it can't find InteractiveHtmlBom.

## Install (script)

1. Download `fusion_ibom_export.py` from this repo (or `git clone` it).
2. In Fusion 360: **Utilities tab → Scripts and Add-ins → Scripts tab → +**
   (green plus) → select the downloaded file.

## Usage (script)

1. Open your PCB in Fusion's Electronics workspace (Board editor).
2. Run this script from the Scripts and Add-ins dialog.
3. Choose a folder to save the BOM in when prompted.
4. Find `<board-name>.html` in that folder.

## Install (add-in)

Fusion is strict about add-in folder structure, more so than for scripts.
Get these details right or the Add-Ins browser won't recognize the
folder at all:

1. `git clone` this repo (or download it), then locate the
   `PcbIbomExport/` folder inside it.
2. The folder name, the main `.py` file, and the `.manifest` file must
   all share the same base name — this repo already ships them correctly
   matched:
   ```
   PcbIbomExport/
     PcbIbomExport.py
     PcbIbomExport.manifest
     Resources/
       PcbIbomExport/
         16x16.png, 32x32.png, 64x64.png
   ```
   If you rename anything, rename all three consistently.
3. In Fusion: **Utilities tab → Scripts and Add-ins → Add-Ins tab**
   (not the Scripts tab — this matters, see note below) **→ +** (green
   plus) → select the `PcbIbomExport` folder.
4. Select it in the list and click **Run**. Check **Run on Startup** if
   you want it to load automatically every time you open Fusion.

**Why the Add-Ins tab specifically matters:** if you add this folder
while the Scripts tab is active instead, Fusion files it as a one-shot
script rather than a persistent add-in. It'll still technically run, but
the toolbar button won't reliably survive, and you won't get a "Run on
Startup" option. If that happens, remove it from the Scripts list (select
it, click `-`) and re-add it from the Add-Ins tab instead.

**While developing/testing:** Fusion caches an add-in's Python module in
memory. Clicking Stop then Run again in the same session doesn't always
pick up code changes — fully quit and reopen Fusion if something seems
stale after an edit.

## Usage (add-in)

1. Open your PCB in the Board Layout editor.
2. Look for the **"BOM Export"** tab in the ribbon — a new top-level tab,
   not a panel tucked inside Design/Utilities/etc.
3. Click **Interactive HTML BOM**.
4. Choose a folder when prompted; find `<board-name>.html` there.

Both versions need the same InteractiveHtmlBom install (see
Requirements above); the add-in will tell you the exact `pip install`
command if it can't find it.

## Why not just run the ibom script directly?

You still can — InteractiveHtmlBom already supports Eagle/Fusion360 `.brd`
files natively. This just automates the manual **File → Export → EAGLE →
Board (.brd)** step in Fusion so you don't have to do it by hand every time
you want an updated BOM.

## License

MIT
