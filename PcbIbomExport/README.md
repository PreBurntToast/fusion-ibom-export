# PcbIbomExport (Add-In)

This is the toolbar-button version of the export script one level up in
this repo. Instead of running a script manually each time, this adds a
permanent **"Interactive HTML BOM"** button on its own tab in Fusion's PCB
(Board Layout) editor.

If you just want something that works with zero setup quirks, use
[`fusion_ibom_export.py`](../fusion_ibom_export.py) instead — run it from
*Scripts and Add-ins → Scripts*. This add-in is for anyone who wants the
one-click convenience and doesn't mind a slightly fussier one-time install.

## Why this needs an add-in, not just a script

Fusion's Electronics/PCB editor is Autodesk EAGLE running inside Fusion,
with its own legacy toolbar system. Getting a button to actually render
there (as opposed to silently existing but never showing up — which is
what happens if you get any of the steps below wrong) took a lot of
trial and error. The two things that matter most:

## Install

**1. Folder and file names must match exactly.** Fusion requires the
containing folder, the main `.py` file, and the `.manifest` file to all
share the same base name:

```
PcbIbomExport/
  PcbIbomExport.py
  PcbIbomExport.manifest
  Resources/
    PcbIbomExport/
      16x16.png
      32x32.png
      64x64.png
```

If you rename anything, rename all three consistently, or Fusion's
Add-Ins browser won't recognize the folder as a valid add-in at all.

**2. Add it from the Add-Ins tab, not the Scripts tab.** In *Scripts and
Add-ins*, make sure you're on the **Add-Ins** tab before clicking the
green `+`. If you accidentally add it while the Scripts tab is active,
Fusion files it as a one-shot script instead — it'll still technically
run, but its UI won't reliably persist, and you won't get a "Run on
Startup" option.

**3. Reload with a full Fusion restart while developing.** Fusion caches
an add-in's Python module in memory. Clicking Stop then Run again in the
same session doesn't reliably pick up code changes — fully quit and
reopen Fusion first if something isn't behaving as expected after an edit.

## Usage

1. Open your PCB in the Board Layout editor.
2. Look for the **"BOM Export"** tab in the ribbon (a new top-level tab,
   not a panel within Design/Utilities/etc).
3. Click **Interactive HTML BOM**.
4. Choose a folder when prompted; find `<board-name>.html` there.

## Requirements

Same as the plain script — [InteractiveHtmlBom](https://github.com/openscopeproject/InteractiveHtmlBom)
installed for the same Python interpreter Fusion uses:

```
pip install InteractiveHtmlBom wxpython jsonschema
```

The add-in will tell you the exact command (with the correct interpreter
path) if it can't find it.

## A known limitation, worth knowing about

The button lives on its own dedicated tab rather than tucked next to
other plugins like SnapEDA or UltraLibrarian on the Utilities tab. That
placement was attempted and specifically did not work in testing — new
panels attached to Fusion's pre-existing tabs in this workspace didn't
render at all, while a brand-new tab reliably does. If a future Fusion
update changes this, the fix lives entirely in the `_attempt_placement()`
function in `PcbIbomExport.py`.
