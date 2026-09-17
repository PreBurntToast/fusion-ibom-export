"""
PcbIbomExport -- Fusion 360 Add-In
===================================

WHAT THIS DOES, IN PLAIN TERMS:
This add-in puts a button called "Interactive HTML BOM" on its own tab in
the toolbar of Fusion's PCB (Board Layout) editor. Click the button, and
it will:
  1. Show a small dialog with checkboxes for a few commonly wanted BOM
     options (include copper tracks, include nets, dark mode) and a text
     field for extra fields.
  2. Export the PCB you currently have open to an EAGLE-format ".brd" file
     (a file format, not related to the word "board" as in lumber -- it's
     just the standard file extension for this kind of PCB data).
  3. Hand that file to a separate, free command-line tool called
     "InteractiveHtmlBom" (ibom for short), which reads it and produces a
     single self-contained HTML web page -- a Bill of Materials you can
     open in any browser, where clicking a part in the list highlights it
     on a picture of the board, and vice versa.

WHY THE CODE LOOKS THE WAY IT DOES:
Fusion's automation interface ("API") is written for software engineers,
and it uses a programming pattern called "event-driven programming" that
doesn't have a direct equivalent in mechanical CAD parametrics. Instead of
your code running top-to-bottom once, you write small functions and *tell
Fusion to call them later* when something happens (a button is clicked, a
workspace is switched, etc). This file is mostly that kind of setup code:
"when X happens, call function Y." The actual useful work (exporting the
board and running the BOM tool) is a normal top-to-bottom function near
the bottom, called export_and_generate_bom().

FILE STRUCTURE, TOP TO BOTTOM:
  1. Imports -- pulling in code other people/Autodesk already wrote.
  2. Module-level variables and constants -- values used throughout the
     file, kept in one place so they're easy to find and change.
  3. _attempt_placement() -- builds the toolbar button, if it isn't there
     already.
  4. "Command wiring" classes -- the event-driven plumbing mentioned
     above.
  5. run() / stop() -- the two functions Fusion itself calls directly:
     run() when the add-in is loaded/turned on, stop() when it's
     unloaded/turned off.
  6. export_and_generate_bom() -- what actually happens when you click
     the button. This is the "real" logic; everything above it exists
     just to get this function connected to a clickable button.
  7. Two small helper functions used only by export_and_generate_bom().
"""

# ---------------------------------------------------------------------------
# 1. IMPORTS
# ---------------------------------------------------------------------------
# These are Python's built-in toolbox modules -- none of this is Fusion-
# specific, it's just general-purpose Python plumbing.

import os            # Working with file paths and folders.
import json          # Custom events (see section 4) can only carry a
                      # plain string as their payload, not a Python list
                      # directly -- json.dumps()/loads() converts our
                      # list of ibom flags to and from that string form.
import shutil        # shutil.which() finds a program on the system PATH;
                      # shutil.rmtree() deletes a folder and everything in it.
import subprocess     # Lets Python launch a *separate* program (in our case,
                      # the ibom command-line tool) and wait for it to finish.
import tempfile       # Creates a scratch folder in the OS's temp directory
                      # for files we only need briefly.
import traceback      # Turns a Python error into a readable multi-line
                      # string, so we can show it in a message box instead
                      # of the add-in just silently failing.

# These are Fusion-specific. adsk.core is the general application/UI
# layer (windows, toolbars, dialogs, commands); adsk.electron is the
# newer, PCB/Electronics-specific layer (boards, schematics, exporting to
# EAGLE format, etc).
import adsk.core
import adsk.electron


# ---------------------------------------------------------------------------
# 2. MODULE-LEVEL VARIABLES AND CONSTANTS
# ---------------------------------------------------------------------------
# In Python, variables written at the top level of a file (not inside any
# function) belong to the whole file/module and keep their value for as
# long as the add-in is loaded. We use a small number of these to remember
# state between one function call and the next -- similar in spirit to a
# global parameter in a CAM post-processor that multiple subroutines need
# to read.

_app = None       # Will hold the running Fusion Application object once
                   # run() has executed -- our "handle" to Fusion itself.
_ui = None         # Will hold Fusion's UserInterface object -- our handle
                   # to windows, toolbars, dialogs, etc.
_cmd_def = None    # Will hold the "Command Definition" object -- Fusion's
                   # internal representation of our button (its label,
                   # tooltip, icon, and what happens when it's clicked),
                   # as opposed to the *visible button itself*, which is a
                   # separate object (see _placement below and the panel/
                   # control code further down).

# IMPORTANT PYTHON-SPECIFIC GOTCHA, explained here because it trips up
# everyone the first time they write a Fusion add-in:
#   Fusion's API is written in C++ under the hood, and it only keeps a
#   "weak" reference to the little Python objects we create to catch its
#   events (see the classes in section 4 below). If our own Python code
#   doesn't *also* keep a normal reference to those objects somewhere,
#   Python's automatic memory cleanup ("garbage collection") will delete
#   them -- and then Fusion tries to call a function that no longer
#   exists, and things break in a very confusing way with no clear error.
#   The fix is simply to keep every event-handler object we create in a
#   list that stays alive for as long as the add-in is running:
_handlers = []

# Remembers whether we've already built the toolbar tab/panel/button this
# session, and if so, which workspace/tab/panel objects they live in. This
# starts out empty (None) and gets filled in by _attempt_placement() the
# first time it succeeds. We check this before doing the work again so
# that re-running things doesn't create duplicate buttons.
_placement = None   # Will become a 3-item tuple: (workspace, tab, panel)

# --- Identifiers for the button itself ---
# Every button/command in Fusion needs a unique internal ID string (never
# shown to the user -- think of it like a part number) plus a human-
# readable name and tooltip (what the user actually sees).
CMD_ID = 'pcbIbomExportCmd'
CMD_NAME = 'Interactive HTML BOM'
CMD_TOOLTIP = 'Export the open PCB and run InteractiveHtmlBom on it'

# --- Extra, always-on customization for this add-in ---
# Clicking the button now shows a small dialog with checkboxes for the
# most commonly wanted InteractiveHtmlBom options (include tracks,
# include nets, dark mode) and a text field for extra fields -- see
# CommandCreatedHandler and CommandExecutedHandler further down for how
# that dialog gets built and read. This list is an escape hatch for
# anything the dialog *doesn't* cover: less common ibom flags you always
# want applied, regardless of what's checked in the dialog. Whatever's
# here gets combined with the dialog's selections every time.
# --dest-dir and --name-format are already handled separately, further
# down in run_ibom_pipeline() -- don't add those here.
#
# Full flag list: run `generate_interactive_bom --help` in a terminal, or
# see the project's wiki: https://github.com/openscopeproject/InteractiveHtmlBom/wiki/Usage
#
# WHY THE DIALOG DOESN'T JUST USE ibom's OWN --show-dialog OPTION, WHICH
# SHOWS A CHECKBOX WINDOW FOR EVERY SETTING ibom HAS: that comes with
# three real problems, discovered and reported by a user named
# Funkenjaeger while testing it as a possible fix for this exact request:
# in dialog mode ibom ignores our --dest-dir and --name-format entirely
# and picks its own default folder and filename instead; there's no way
# to tell whether the user clicked Cancel or actually finished, since
# both look the same to us; and it leaves an extra temporary copy of the
# .brd file sitting in the output folder afterward. Building our own
# small dialog with just the commonly wanted options, using Fusion's own
# CommandInputs instead of ibom's, avoids all three.
EXTRA_IBOM_ARGS: list = []

# Where to find the icon image files for the button. This is a RELATIVE
# path (relative to wherever this .py file itself lives), which Fusion
# requires -- it will not accept a full absolute path here, only a
# relative one, matching the folder structure:
#   PcbIbomExport/
#     PcbIbomExport.py        <- this file
#     Resources/
#       PcbIbomExport/
#         16x16.png, 32x32.png, 64x64.png   <- the icon, at three sizes
RESOURCE_FOLDER = './Resources/PcbIbomExport'

# --- Identifiers for WHERE the button lives in Fusion's ribbon ---
# Fusion's PCB editor is internally called "Board Layout" and, confusingly,
# Autodesk's own internal ID for it has a typo baked into it --
# "Environement" instead of "Environment". This isn't a mistake in this
# file; it's genuinely misspelled inside Fusion itself. We confirmed this
# exact string two independent ways: it showed up in a diagnostic log we
# wrote while debugging where the button should live, and it's also
# hardcoded (with the same typo) inside a different, already-published,
# open-source Fusion add-in (Fusion-EEToolBox) that works with this same
# PCB editor.
BOARD_WORKSPACE_ID = 'BoardLayoutEnvironement'

# We don't want to inject our button into one of Fusion's pre-existing
# toolbar tabs (like "Design" or "Utilities") -- through a lot of trial
# and error, we found that this particular PCB editor's toolbar (which is
# actually the old EAGLE software's toolbar, wrapped inside Fusion) only
# reliably displays buttons that live on a BRAND NEW tab we create
# ourselves, not ones bolted onto its existing tabs. We did try anchoring
# a new panel onto the existing "Utilities" tab (right next to SnapEDA and
# UltraLibrarian's panels there) since that would have looked nicer, but
# it didn't render either -- so we're back to the approach that's actually
# proven to work: our own tab, and our own panel within it. These are just
# internal ID strings and display names for that tab and panel -- pick
# anything, as long as the ID half is unique and never changes between
# versions of this add-in.
TAB_ID = 'pcbIbomExportTab'
TAB_NAME = 'BOM Export'
PANEL_ID = 'pcbIbomExportPanel'
PANEL_NAME = 'BOM Export'


# ---------------------------------------------------------------------------
# 3. BUILDING THE TOOLBAR BUTTON
# ---------------------------------------------------------------------------

def _attempt_placement():
    """
    Create our toolbar tab, panel, and button (if they don't already
    exist), and remember that we've done so.

    Think of this like a one-time "setup" pass, similar to defining a new
    tool in a CAM tool library before you can use it in a toolpath -- this
    function defines the button and where it lives; it does NOT run the
    export itself (that's export_and_generate_bom(), much further down).
    """
    global _placement

    # If we've already built everything once this session, there's
    # nothing more to do -- just exit the function immediately.
    # ("return" with nothing after it just means "stop here.")
    if _placement is not None:
        return

    # Ask Fusion for the PCB editor's Workspace object, by the ID string
    # we hardcoded above. A "Workspace" in Fusion's API is the object that
    # represents one whole editing environment -- e.g. "Design", "CAM",
    # "Drawing", or in this case, "Board Layout" (the PCB editor).
    workspace = _ui.workspaces.itemById(BOARD_WORKSPACE_ID)
    if workspace is None:
        # If Fusion doesn't recognize that ID at all (e.g. a future
        # Fusion update renames it internally), there's nothing more we
        # can safely do, so we quietly give up rather than crash.
        return

    # Look for our tab by ID first, in case it already exists from an
    # earlier run this session. itemById() returns None if nothing with
    # that ID exists yet.
    tab = workspace.toolbarTabs.itemById(TAB_ID)
    if tab is None:
        # Doesn't exist yet -- create it. .add(id, display_name) is the
        # Fusion API call that actually builds a new tab.
        tab = workspace.toolbarTabs.add(TAB_ID, TAB_NAME)

    # Same idea, one level down: look for our panel *inside that tab*
    # (not inside the workspace generally -- this distinction turned out
    # to matter a lot during development), and create it if missing.
    panel = tab.toolbarPanels.itemById(PANEL_ID)
    if panel is None:
        panel = tab.toolbarPanels.add(PANEL_ID, PANEL_NAME)

    # Finally, check whether our button (a "control" in Fusion's
    # vocabulary) already exists inside that panel, and add it if not.
    if not panel.controls.itemById(CMD_ID):
        # _cmd_def is the button's "definition" (name/icon/tooltip),
        # created back in run() below. addCommand() takes that definition
        # and creates the actual visible, clickable button from it.
        control = panel.controls.addCommand(_cmd_def)
        # isPromoted = the button is shown directly in the ribbon, not
        # tucked away inside a dropdown you have to click to reveal.
        control.isPromoted = True
        # isPromotedByDefault = keep it promoted even after Fusion resets
        # ribbon customizations back to defaults.
        control.isPromotedByDefault = True

    # Remember what we built, so a second call to this function (which
    # could happen if, for some reason, run() executes more than once)
    # doesn't try to build everything all over again.
    _placement = (workspace, tab, panel)


# ---------------------------------------------------------------------------
# 4. COMMAND WIRING (the event-driven plumbing mentioned in the file intro)
# ---------------------------------------------------------------------------
# In Python, a "class" is a blueprint for creating an object that bundles
# together some data and some functions ("methods") that act on it. Here,
# we're not using classes for their usual purpose (representing a "thing"
# with properties) -- we're using them purely because that's the shape
# Fusion's API requires for something called an "event handler": a small
# object with one required method, notify(), that Fusion will call
# automatically when a specific event occurs. You never call notify()
# yourself; Fusion calls it for you, at a time it decides.
#
# There are two separate events involved in "a button that does
# something when clicked," which is one more layer than you might expect:
#
#   CommandCreatedHandler: fires ONCE, the very first time Fusion is
#   about to actually run our command (i.e., right after the user clicks
#   the button for the first time in a session). Its job here is TWO
#   things: build the little checkbox dialog the user sees, and attach
#   the SECOND handler below so we find out what they chose.
#
#   CommandExecutedHandler: fires every time the button is actually
#   clicked, the dialog is filled in, and the user clicks OK. THIS is
#   where we read back what got checked, and call our real function,
#   export_and_generate_bom().
#
# Every notify() method below is wrapped in a try/except block. This is a
# safety net: if anything inside goes wrong, instead of Fusion silently
# swallowing the error (which is genuinely how it behaves by default,
# leaving you no idea why nothing happened), we catch the error ourselves
# and pop up a message box with the full details.
#
# WHY A DIALOG HERE, RATHER THAN JUST A PYTHON CONSTANT LIKE
# EXTRA_IBOM_ARGS ABOVE: this add-in's whole selling point is one-click
# convenience -- editing a Python file to change a checkbox-shaped
# setting defeats that. Since we already have a real Fusion "Command"
# wired up for the button, adding proper checkboxes to it costs very
# little extra code and matches what people actually expect from a GUI
# tool. EXTRA_IBOM_ARGS is still here as an escape hatch for anything the
# dialog doesn't cover (odd one-off flags, for instance), and gets
# combined with whatever the dialog collects.
#
# A UI-TIMING QUIRK, AND WHY WE USE A "CUSTOM EVENT" TO WORK AROUND IT:
# You might expect CommandExecutedHandler (fires when the user clicks OK)
# to be the natural place to just do the real work: read the checkboxes,
# export the board, run ibom, show a result. That's what an earlier
# version of this file did, and it caused the checkbox dialog to
# visually stay on screen the ENTIRE time all of that was happening,
# only disappearing once everything finally finished. Moving the work to
# the command's "destroy" event (which fires once the dialog is supposed
# to be done closing) didn't help either -- it turns out Fusion fires
# execute and destroy back-to-back, synchronously, as part of the same
# unbroken chain of code triggered by the user's click, so neither one
# actually gives Fusion's UI a chance to repaint before we pile on more
# work.
#
# The fix is Fusion's "Custom Event" mechanism: instead of calling our
# slow function directly, we ask Fusion to run it LATER, on a fresh pass
# through its own event loop, by "firing" a custom event and reacting to
# it in a separate handler (RunExportHandler, below). That gap -- however
# brief -- is enough for Fusion to actually finish closing the dialog
# before our slow work begins.

# A unique name for our custom event, registered once in run() (see
# below) and fired every time the user clicks OK on the dialog.
CUSTOM_EVENT_ID = 'pcbIbomExportRunEvent'

# Unique IDs for each input on the dialog -- same idea as CMD_ID above,
# an internal name Fusion uses to find each input again, never shown to
# the user.
INPUT_INCLUDE_TRACKS = 'includeTracks'
INPUT_INCLUDE_NETS = 'includeNets'
INPUT_DARK_MODE = 'darkMode'
INPUT_EXTRA_FIELDS = 'extraFields'


class CommandExecutedHandler(adsk.core.CommandEventHandler):
    def notify(self, args):
        try:
            # args.command is the same Command object CommandCreatedHandler
            # built the dialog on; commandInputs.itemById() reads back
            # whichever input we're asking about, by the ID strings
            # defined above.
            inputs = args.command.commandInputs

            # .value on a checkbox input is a plain True/False. We build a
            # small list of command-line flags out of whichever boxes
            # ended up checked -- if a box isn't checked, its flag simply
            # never gets added to the list.
            dialog_args = []
            if inputs.itemById(INPUT_INCLUDE_TRACKS).value:
                dialog_args.append('--include-tracks')
            if inputs.itemById(INPUT_INCLUDE_NETS).value:
                dialog_args.append('--include-nets')
            if inputs.itemById(INPUT_DARK_MODE).value:
                dialog_args.append('--dark-mode')

            # .value on a text input is just a string. .strip() removes
            # any accidental leading/trailing spaces the user typed. We
            # only add the flag at all if they actually typed something.
            extra_fields = inputs.itemById(INPUT_EXTRA_FIELDS).value.strip()
            if extra_fields:
                dialog_args += ['--extra-fields', extra_fields]

            # Combine what the dialog collected with whatever's in the
            # EXTRA_IBOM_ARGS escape hatch near the top of this file.
            ibom_args = dialog_args + EXTRA_IBOM_ARGS

            # Fire the custom event instead of calling export_and_generate_bom()
            # directly -- see the big comment above this class for why.
            # fireCustomEvent()'s second argument must be a plain string,
            # so we JSON-encode our list of flags; RunExportHandler
            # decodes it back on the other end.
            _app.fireCustomEvent(CUSTOM_EVENT_ID, json.dumps(ibom_args))
        except Exception:
            if _ui:
                _ui.messageBox(f'Failed:\n{traceback.format_exc()}')


class RunExportHandler(adsk.core.CustomEventHandler):
    """
    Reacts to the custom event fired by CommandExecutedHandler, above.
    Because Fusion delivers custom events on a fresh pass through its own
    event loop rather than synchronously inside whatever code fired them,
    this is the one place in the whole add-in where it's actually safe to
    do slow, blocking work (folder picker, board export, launching ibom,
    result message box) without it visually fighting the checkbox dialog
    for screen time.
    """
    def notify(self, event_args):
        try:
            # event_args.additionalInfo is the exact string we passed to
            # fireCustomEvent() above; json.loads() turns it back into a
            # real Python list.
            ibom_args = json.loads(event_args.additionalInfo) if event_args.additionalInfo else []
            export_and_generate_bom(ibom_args)
        except Exception:
            if _ui:
                _ui.messageBox(f'Failed:\n{traceback.format_exc()}')


class CommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        try:
            cmd = args.command
            inputs = cmd.commandInputs

            # addBoolValueInput(id, label, isCheckbox, iconFolder, default)
            # -- passing True for isCheckbox gives a checkbox rather than
            # a toggle button; an empty string for iconFolder means "use
            # the default look, no custom icon"; the last argument is
            # whether it starts checked or unchecked.
            inputs.addBoolValueInput(
                INPUT_INCLUDE_TRACKS, 'Include copper tracks', True, '', False
            )
            inputs.addBoolValueInput(
                INPUT_INCLUDE_NETS, 'Include nets', True, '', False
            )
            inputs.addBoolValueInput(
                INPUT_DARK_MODE, 'Dark mode', True, '', False
            )
            # addStringValueInput(id, label, default) -- a plain text box.
            inputs.addStringValueInput(
                INPUT_EXTRA_FIELDS, 'Extra fields (comma-separated)', ''
            )

            on_execute = CommandExecutedHandler()
            cmd.execute.add(on_execute)
            # Keep a reference alive -- see the big comment in section 2
            # about why this list exists.
            _handlers.append(on_execute)
        except Exception:
            if _ui:
                _ui.messageBox(f'Failed:\n{traceback.format_exc()}')


# ---------------------------------------------------------------------------
# 5. run() AND stop() -- Fusion calls these two functions directly
# ---------------------------------------------------------------------------
# Every Fusion add-in file must define a function literally named run(),
# which Fusion calls automatically the moment the add-in is loaded
# (whether that's because you clicked "Run" in the Scripts and Add-ins
# dialog, or because it's set to load automatically on Fusion startup).
# If the add-in also defines stop() (ours does), Fusion calls that when
# the add-in is turned off or Fusion is closing, so we get a chance to
# clean up anything we created.

def run(context):
    # "global" tells Python that when we assign to these variable names
    # inside this function, we mean the module-level ones from section 2,
    # not brand-new local variables that would disappear when the
    # function ends.
    global _app, _ui, _cmd_def, _placement
    try:
        # Get our handles to the running Fusion application and its UI.
        # Every other line in this add-in ultimately depends on these two
        # lines having run first.
        _app = adsk.core.Application.get()
        _ui = _app.userInterface
        _placement = None   # reset in case this is a reload, not a fresh start

        # If a command definition with our ID is already hanging around
        # from a previous load of this add-in (e.g. you clicked Stop then
        # Run again without fully restarting Fusion), delete it first.
        # Otherwise Fusion would refuse to create a second one with the
        # same ID and this whole function would fail partway through.
        cmd_defs = _ui.commandDefinitions
        existing = cmd_defs.itemById(CMD_ID)
        if existing:
            existing.deleteMe()

        # Sanity-check that the icon files actually exist on disk before
        # we try to use them. If someone copies just this .py file
        # without the Resources folder alongside it, this gives a clear,
        # actionable error message instead of a cryptic Fusion API crash.
        expected_resources = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), 'Resources', 'PcbIbomExport'
        )
        if not os.path.isdir(expected_resources):
            _ui.messageBox(
                "Resource folder not found at:\n\n"
                f"{expected_resources}\n\n"
                "Create that folder and put 16x16.png, 32x32.png, and "
                "64x64.png in it, then reload the add-in."
            )
            return   # can't continue without icons, so stop here

        # Create the button's "definition": its internal ID, the text
        # label, the tooltip, and where to find its icon. This does NOT
        # make the button appear anywhere yet -- it just defines what the
        # button *would* look like and do, ready to be placed somewhere
        # by _attempt_placement().
        _cmd_def = cmd_defs.addButtonDefinition(
            CMD_ID, CMD_NAME, CMD_TOOLTIP, RESOURCE_FOLDER
        )

        # Connect the "created" event handler from section 4 to this
        # specific button definition, and keep a reference to the handler
        # object alive (again, see the big comment in section 2).
        on_created = CommandCreatedHandler()
        _cmd_def.commandCreated.add(on_created)
        _handlers.append(on_created)

        # Register our custom event (see the big comment in section 4 for
        # why this exists) and connect RunExportHandler to it -- this is
        # what actually does the export work, once CommandExecutedHandler
        # fires it. unregisterCustomEvent() first clears out a stale
        # leftover from a previous load of this add-in in the same
        # session; it's wrapped in try/except because it errors if
        # nothing was registered yet, which is the normal case on a
        # completely fresh Fusion session.
        try:
            _app.unregisterCustomEvent(CUSTOM_EVENT_ID)
        except Exception:
            pass
        custom_event = _app.registerCustomEvent(CUSTOM_EVENT_ID)
        on_run_export = RunExportHandler()
        custom_event.add(on_run_export)
        _handlers.append(on_run_export)

        # Now actually build the tab/panel/button and place it in the UI.
        _attempt_placement()

    except Exception:
        # Catch-all safety net for the whole run() function: if anything
        # above failed unexpectedly, show the details instead of failing
        # silently.
        if _ui:
            _ui.messageBox(f'Failed:\n{traceback.format_exc()}')


def stop(context):
    """
    Fusion calls this when the add-in is being unloaded (Stop button, or
    Fusion closing while "Run on Startup" is off). We undo everything we
    created in run(), in reverse order: delete the button, then delete
    the panel if it's now empty, then delete the tab if IT is now empty,
    then delete the button's definition. This keeps things tidy if you
    reload the add-in repeatedly during development -- without this,
    you'd accumulate duplicate empty tabs/panels over time.
    """
    global _placement
    try:
        ui = adsk.core.Application.get().userInterface

        if _placement:
            # Unpack the 3-item tuple we saved in _attempt_placement().
            # The underscore means "we don't need the workspace object
            # here, just the tab and panel" -- a common Python convention
            # for "ignore this value."
            _, tab, panel = _placement

            ctrl = panel.controls.itemById(CMD_ID)
            if ctrl:
                ctrl.deleteMe()

            if panel.controls.count == 0:
                panel.deleteMe()

            if tab.toolbarPanels.count == 0:
                tab.deleteMe()

        _placement = None

        cmd_def = ui.commandDefinitions.itemById(CMD_ID)
        if cmd_def:
            cmd_def.deleteMe()

        # Clean up the custom event too, so a later Run in the same
        # Fusion session starts from a clean slate instead of piling up
        # duplicate registrations.
        try:
            adsk.core.Application.get().unregisterCustomEvent(CUSTOM_EVENT_ID)
        except Exception:
            pass
    except Exception:
        # Deliberately silent here (no message box): stop() often runs
        # while Fusion itself is in the middle of closing down, and
        # popping up a dialog at that moment can be more disruptive than
        # helpful. If cleanup fails, the worst outcome is a leftover empty
        # tab, not a broken add-in.
        pass


# ---------------------------------------------------------------------------
# 6. THE ACTUAL WORK -- what happens when you click the button
# ---------------------------------------------------------------------------
# Everything above this point exists purely to get this one function
# connected to a clickable toolbar button. This function itself is normal,
# top-to-bottom code -- no event-handler indirection here.

def export_and_generate_bom(ibom_args):
    """
    ibom_args: the list of extra generate_interactive_bom command-line
    flags collected from the dialog's checkboxes/text field (plus
    EXTRA_IBOM_ARGS), built by CommandExecutedHandler above and passed
    straight through to run_ibom_pipeline() near the bottom of this file.
    """
    ui = _ui
    temp_dir = None   # will hold the path to a scratch folder, created below

    try:
        # "Cast" the currently active document/product to a Board object.
        # In plain terms: ask Fusion "is the thing the user currently has
        # open actually a PCB board layout?" If the user has, say, a
        # regular 3D model open instead, this returns None (Python's way
        # of representing "nothing"/"no such value") rather than an error.
        board = adsk.electron.Board.cast(_app.activeProduct)
        if not board:
            ui.messageBox(
                "Please switch to the 2D PCB layout (Board) view in the "
                "Electronics workspace, then click this button again."
            )
            return

        # Ask the user, via a standard Windows/Mac folder-picker dialog,
        # where they want the finished BOM web page saved.
        folder_dlg = ui.createFolderDialog()
        folder_dlg.title = "Select Output Location to Save HTML BOM"
        if folder_dlg.showDialog() != adsk.core.DialogResults.DialogOK:
            # User clicked Cancel instead of choosing a folder -- stop
            # here without doing anything further or showing any error;
            # cancelling isn't a failure.
            return
        out_dir = folder_dlg.folder

        # Build a safe filename from the board's own name. os.path.splitext
        # splits "MyBoard.brd" into ("MyBoard", ".brd") and we keep only
        # the first part. The line after that replaces any character that
        # isn't a letter, digit, dash, or underscore with an underscore --
        # this avoids problems if the board's name contains spaces, slashes,
        # or other characters that aren't safe to use in a filename.
        raw_name = os.path.splitext(board.name)[0] if board.name else "board"
        design_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in raw_name)

        # Create a temporary scratch folder (somewhere in the OS's usual
        # temp-file location) to hold the intermediate .brd file. We clean
        # this up automatically at the very end, in the "finally" block
        # below, regardless of whether everything else succeeded or failed.
        temp_dir = tempfile.mkdtemp(prefix="fs_ibom_")
        temp_brd = os.path.join(temp_dir, f"{design_name}.brd")

        # This is the key step that makes the whole add-in work: Fusion's
        # Electronics API can export the currently open board directly to
        # the industry-standard EAGLE ".brd" file format. We're not
        # reconstructing the board data ourselves -- we're asking Fusion
        # to do a real, accurate export, the same as if you'd used a
        # File > Export menu command by hand.
        export_options = board.exportManager.createEagleBrdExportOptions(temp_brd)
        if export_options is None:
            ui.messageBox("Could not create export options for this board.")
            return

        # .execute() actually performs the export and returns True/False
        # depending on whether it succeeded.
        export_ok = board.exportManager.execute(export_options)
        if not export_ok or not os.path.exists(temp_brd):
            ui.messageBox(
                "Fusion's Electronics API failed to export the board to "
                "EAGLE 9.6.2 .brd format. Check the Text Commands window for details."
            )
            return

        # Just for the final success message -- count how many components
        # (parts) are actually on the board, so the user gets a sanity-
        # check number along with the "success" message.
        element_count = board.elements.count if board.elements else 0

        # Look for the separate InteractiveHtmlBom tool on this computer.
        # See the _find_ibom_command() function below for exactly how and
        # why this search works the way it does.
        ibom_cmd = _find_ibom_command()
        if ibom_cmd is None:
            # We deliberately do NOT try to silently install it for the
            # user -- see the comment on _find_ibom_command() for why.
            # Instead we tell them the exact command to run themselves,
            # using a standalone Python -- not Fusion's own bundled one
            # (see _find_ibom_command()'s comment for why that wouldn't
            # work even if we tried to point at it).
            install_cmd = (
                "py -m pip install InteractiveHtmlBom wxpython jsonschema"
                if os.name == "nt"
                else "python3 -m pip install InteractiveHtmlBom wxpython jsonschema"
            )
            ui.messageBox(
                "InteractiveHtmlBom isn't installed where this add-in can find it.\n\n"
                "Install it once, using a standalone Python on your system "
                "PATH (not Fusion's own bundled Python) -- from a normal "
                "terminal:\n\n"
                f"  {install_cmd}\n\n"
                "then click this button again."
            )
            return

        # Hand off to the helper function below, which actually launches
        # the external tool and reports back whether it succeeded.
        run_ibom_pipeline(ibom_cmd, temp_brd, out_dir, design_name, element_count, ui, ibom_args)

    except Exception:
        # Catch-all safety net for this whole function.
        if ui:
            ui.messageBox(f"Failure:\n{traceback.format_exc()}")
    finally:
        # "finally" means this code runs no matter what happened above --
        # whether everything succeeded, an error was caught, or we
        # returned early. We use it here to guarantee the scratch temp
        # folder always gets deleted, so these don't pile up on disk over
        # repeated use.
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# 7. HELPER FUNCTIONS for launching the external InteractiveHtmlBom tool
# ---------------------------------------------------------------------------

def _find_ibom_command():
    """
    Locate the InteractiveHtmlBom program on this computer, and return it
    as a list of strings (a "command," in the format Python's subprocess
    module expects -- e.g. ['/usr/local/bin/generate_interactive_bom']).
    Returns None if the tool can't be found, meaning it isn't installed
    for a Python this add-in can actually reach.

    THIS FUNCTION USED TO DO SOMETHING DIFFERENT AND WRONG, WORTH
    EXPLAINING SINCE IT'S AN INSTRUCTIVE MISTAKE:
    An earlier version of this add-in assumed that sys.executable (a
    Python built-in that's supposed to give you "the path to the current
    Python interpreter") would point at Fusion's own bundled Python, and
    tried to look for the ibom tool in a "Scripts" folder right next to
    it. That assumption was wrong in a way that's specific to how Fusion
    works: Fusion *embeds* Python directly inside its own application
    process, rather than launching a separate python.exe process the way
    a normal terminal does. For an embedded interpreter like this,
    sys.executable reports the path to the *host application* doing the
    embedding -- i.e. Fusion360.exe itself -- not a Python interpreter at
    all. So the old code was checking for a "Scripts" folder next to
    Fusion360.exe, which was never going to exist, and the check silently
    failed every single time without any indication anything was wrong.
    (Caught and diagnosed by a user named Funkenjaeger, filed as an issue
    against this project on GitHub -- not something we found ourselves.)

    Even setting that mistake aside, installing packages into Fusion's
    real bundled Python (which does exist, just not at the path the old
    code was checking) wouldn't actually be a good idea anyway: Fusion
    replaces that entire folder on every update, so anything installed
    there would silently vanish the next time Fusion updates itself.

    The only combination that actually works is a standalone Python
    install (the kind you'd download from python.org, or get via your
    OS's package manager) with its own Scripts/bin folder already on your
    system's PATH -- which is exactly what shutil.which() checks for
    below. This is simpler than the old logic, not just more correct:
    there's no interpreter path to reason about at all anymore.
    """
    found = shutil.which("generate_interactive_bom")
    if found:
        # subprocess.run() (used later) wants a LIST of command pieces,
        # even if there's only one, hence the square brackets.
        return [found]

    # Not found anywhere we know to look.
    return None


def run_ibom_pipeline(ibom_cmd, brd_path, out_dir, design_name, count, ui, ibom_args):
    """
    Actually launch the InteractiveHtmlBom tool as a separate program,
    wait for it to finish, and report the result to the user.

    ibom_cmd: the list returned by _find_ibom_command() above, e.g.
              ['C:/.../generate_interactive_bom.exe'].
    brd_path: full path to the .brd file we exported earlier.
    out_dir:  the folder the user chose for the finished HTML file.
    design_name: used both as the output filename and to keep the ibom
              tool from mixing up unrelated boards if run repeatedly.
    count:    number of components, purely for the success message.
    ui:       Fusion's UserInterface object, so we can show message boxes.
    ibom_args: extra command-line flags -- whatever the dialog's
              checkboxes/text field collected, combined with
              EXTRA_IBOM_ARGS, built by export_and_generate_bom() and
              passed straight through from there.
    """
    # Build the full command line as a list of strings. This is
    # equivalent to typing, in a terminal:
    #   generate_interactive_bom  <brd_path>  --dest-dir <out_dir>
    #       --name-format <design_name>  --no-browser  <your extra flags>
    # "--no-browser" stops the tool from automatically popping open a web
    # browser window itself -- we'd rather just tell the user where the
    # file ended up. ibom_args (whatever the dialog collected, plus
    # EXTRA_IBOM_ARGS) is tacked on at the end.
    cmd = ibom_cmd + [
        brd_path,
        "--dest-dir", out_dir,
        "--name-format", design_name,
        "--no-browser",
    ] + ibom_args

    # subprocess.run() launches "cmd" as its own separate program and
    # waits (blocks) until it finishes before continuing.
    #   capture_output=True  -- collect whatever the program prints,
    #                           instead of letting it print to a console
    #                           window we can't see anyway.
    #   text=True            -- give us that captured output as normal
    #                           text (strings) rather than raw bytes.
    #   creationflags=...    -- Windows-only setting that stops a brief,
    #                           distracting console window from flashing
    #                           on screen while the tool runs. Ignored
    #                           entirely on Mac/Linux (hence the "if
    #                           os.name == 'nt' else 0").
    engine_run = subprocess.run(
        cmd, capture_output=True, text=True,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )

    # Every well-behaved command-line program reports success or failure
    # through a numeric "return code" when it finishes: 0 means success,
    # anything else means something went wrong. We check that here rather
    # than assuming it worked just because nothing crashed on our end.
    if engine_run.returncode == 0:
        ui.messageBox(
            f"BOM Generation Complete!\n\n"
            f"Extracted {count} component(s) from the real board data.\n\n"
            f"File Saved: {design_name}.html\n"
            f"Location: {out_dir}"
        )
    else:
        # engine_run.stderr holds whatever error text the ibom tool
        # itself printed, which is far more useful for diagnosing the
        # problem than just knowing "it failed."
        ui.messageBox(
            f"InteractiveHtmlBom failed (code {engine_run.returncode}):\n\n"
            f"{engine_run.stderr}"
        )
