# fusion-ibom-export

Export the board open in Fusion 360's Electronics workspace to an
EAGLE-compatible `.brd` file and generate an
[Interactive HTML BOM](https://github.com/openscopeproject/InteractiveHtmlBom)
from it, without leaving Fusion.

## Two ways to use this

| | [`fusion_ibom_export.py`](fusion_ibom_export.py) | [`PcbIbomExport/`](PcbIbomExport/) |
|---|---|---|
| Type | Plain script | Add-in with a toolbar button |
| Setup | Copy one file in | Folder/file naming rules apply — see its [README](PcbIbomExport/README.md) |
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

For the add-in version's install steps instead, see
[`PcbIbomExport/README.md`](PcbIbomExport/README.md).

## Why not just run the ibom script directly?

You still can — InteractiveHtmlBom already supports Eagle/Fusion360 `.brd`
files natively. This just automates the manual **File → Export → EAGLE →
Board (.brd)** step in Fusion so you don't have to do it by hand every time
you want an updated BOM.

## License

MIT
