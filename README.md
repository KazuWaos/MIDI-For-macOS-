# MIDI++ for macOS

MIDI++ for macOS is a Python desktop application for playing Standard MIDI files through virtual piano websites and games. It can translate a song into QWERTY key presses, send MIDI notes through a virtual MIDI port, or use the numeric-keyboard protocol supported by compatible Roblox piano games.

The project is a macOS reimplementation inspired by [MIDI++ by Zephkek](https://github.com/Zephkek/MIDIPlusPlus). It is a separate implementation built with Python, Tkinter, CoreGraphics/Quartz, and `mido`; it is not the original Windows source code.

> **Important:** The two live-input buttons and the song-output selector are separate. **MidiConnect IN** and **Midi2Key IN** process notes from a connected physical MIDI device. To play a loaded `.mid` file with the game-compatible protocol, set **Config → Song Output → MidiConnect (Roblox)**.

## Features

- Play Standard MIDI files with playback controls, tempo changes, multiple tracks, and channel filtering.
- Choose between QWERTY keyboard output, the MIDI++ numeric-keyboard protocol, a virtual MIDI output port, or QWERTY plus virtual MIDI.
- Use a physical MIDI input with either live **MidiConnect IN** or **Midi2Key IN**.
- Adjust note range, transpose, velocity, sustain, track mute/solo, and playback speed.
- Add folders containing MIDI files and save custom key layouts and velocity curves.
- Resize the application window while keeping its 12:10 aspect ratio. The interface scrolls vertically when it does not fit on screen.

## Requirements

- macOS with Python 3 and Tkinter.
- The Python packages below. `tkinterdnd2` is optional and is not required for normal file loading.
- macOS **Accessibility** permission for MIDI++ (or for Terminal/iTerm/your IDE when running from source). Input Monitoring permission may also be needed for global shortcuts and keyboard-state detection.
- A target website or game that accepts the chosen output method. MidiConnect only works with games that implement the compatible MIDI++ numeric-keyboard protocol.

## Install and run from source

In Terminal, install the dependencies:

```bash
python3 -m pip install mido python-rtmidi pyobjc-framework-Quartz pyobjc-framework-ApplicationServices pyobjc-framework-Cocoa
```

Run the application:

```bash
python3 outputs/midiplusplus_mac_corregido.py
```

If you have the script outside this repository, replace the path above with the path to your `.py` file. The application uses Tkinter, which must be available in your Python installation.

### macOS permissions

Open **System Settings → Privacy & Security → Accessibility** and enable the app that sends keyboard events:

- When running the `.py` file, enable the terminal or editor you used to launch it.
- When running a packaged app, enable **MIDI++** itself.

If global shortcuts or key-state detection do not work, also check **Input Monitoring**. After changing permissions, quit and reopen the app.

## Quick start: play a MIDI file

1. Launch MIDI++ and grant the requested macOS permissions.
2. Click **Add Folder…** under **MIDI Files** and select a folder containing `.mid` or `.midi` files. The file list also scans the application data folder and its `midi` subfolder. Folder scanning is not recursive.
3. Select a song in the list. Double-clicking a file loads it; **Load** loads the selected file. The **Log** shows the selected song output when it is loaded.
4. Choose the desired method from **Config → Song Output**:
   - **QWERTY Keys** for virtual piano sites controlled by normal keyboard keys.
   - **MidiConnect (Roblox)** for games that support MIDI++'s numeric-keyboard protocol.
   - **Virtual MIDI Port** for a MIDI application or game that can receive a system MIDI input port. Select the port named `MIDI++ Out` in that application.
   - **QWERTY + Virtual MIDI** to send through both of those outputs at once.
5. Focus the target game or piano window, then click **Play/Pause**. With **Pause when focus is lost** enabled, playback waits while MIDI++ is the frontmost app and resumes when the target app is focused.

For the Roblox protocol, select **MidiConnect (Roblox)** before starting the song. The separate **MidiConnect IN** button is only for a physical MIDI keyboard and does not select the song's output.

## Playback controls

| Control | What it does |
| --- | --- |
| **Load** | Loads the selected MIDI file. If nothing is selected, opens a file picker. |
| **Play/Pause** | Starts the loaded song or pauses/resumes it. |
| **Restart** | Returns to the beginning and starts again if playback is not already running. |
| **Skip +10** | Moves forward by 10 seconds. |
| **Rew −10** | Moves backward by 10 seconds. |
| **Speed ++ / Speed −−** | Increases or decreases playback speed in small steps. The displayed `x1.00` value is normal speed. |
| **Progress bar** | Click a position to seek to that part of the song. |
| **Loop** | Repeats the song after it finishes. |
| **Channel selector** | Restricts live MIDI input to one MIDI channel, or accepts all channels. |

The **time display** shows the current position and total duration. The status label indicates whether playback is stopped, playing, paused, or waiting for the target app to receive focus.

## MIDI Files panel

- **Name (A–Z) / Recent first** sorts the available files by name or modification time.
- **Refresh** rescans the known folders.
- **Add Folder…** adds a folder to the saved list of MIDI locations. Files directly inside that folder are listed; nested folders are not scanned.
- **Double-click a song** to load it.

MIDI++ reads `.mid` and `.midi` files. The **Details** panel displays file format, track and note counts, tempo, time signature, note mode, playable range, and transposition information.

## Song output methods

### QWERTY Keys

Maps MIDI pitches to keyboard keys using the selected layout. The target piano/game must be focused to receive the simulated key presses. Modifier keys used for black keys or extended ranges are tapped for the key-down event, while the mapped main key remains held for the duration of the note.

### MidiConnect (Roblox)

Encodes each note and velocity as a short series of numeric-keyboard key presses, following the protocol used by the original MIDI++ MidiConnect feature. This is keyboard input, not a CoreMIDI port. The target Roblox game must explicitly support this protocol. Song notes bypass QWERTY layout mapping and octave folding; a manual transposition can still shift their pitches.

To use it for a song, set **Config → Song Output → MidiConnect (Roblox)**. The top-row **MidiConnect IN** button is a different feature for incoming notes from a physical MIDI device.

### Virtual MIDI Port

Creates a virtual output port named **MIDI++ Out**. In the receiving DAW, synthesizer, or game, choose that port as the MIDI input. This sends MIDI note and sustain messages rather than keyboard events.

### QWERTY + Virtual MIDI

Sends notes to the QWERTY target and to the virtual MIDI port together.

## Live MIDI input

The top-row input controls listen to a connected physical MIDI device; they do not change the output method for a loaded song. The device dropdown selects the source, and **Refresh MIDI** rescans available inputs.

- **MidiConnect IN** converts live MIDI input into the numeric-keyboard protocol for compatible games.
- **Midi2Key IN** converts live MIDI input into QWERTY key presses according to the selected layout.
- These two live-input modes are mutually exclusive. Turn one off before enabling the other.
- **Channel selector** applies to live MIDI input. **All Channels** accepts notes from every channel.

An IAC Bus or other virtual input can also appear as a MIDI device. A connected input device is required to use either live-input mode; song playback does not require one.

## Advanced controls

| Control | Purpose |
| --- | --- |
| **88-Key** | Restricts playback to the standard 88-key piano range. Notes outside the range are either folded by **OutRange** or discarded. |
| **AutoVol** | Rescales a song's velocity range to use more of the available range. It is intended for output routes that use the app's velocity processing; MidiConnect sends the song's raw MIDI velocity. |
| **Velocity** | Enables velocity-curve processing for supported output routes. The curve has 32 steps. For QWERTY games that support a soft-note modifier, notes below the configured threshold can be sent with Option/Alt. Many browser pianos do not distinguish key velocity. |
| **Sustain** | Enables sustain/pedal processing for QWERTY and virtual MIDI output. MidiConnect song playback forwards CC64 sustain events from the MIDI file through its protocol. |
| **Sustain Cutoff** | Sets the threshold used to treat MIDI CC64 values as pedal-down or pedal-up. |
| **Transpose** | Automatically chooses a transposition based on the song's pitch range and the selected layout. The displayed number shows the applied semitone shift. |
| **Transpose − / + / 0** | Lowers or raises the manual transposition by one semitone, or resets it to zero. Manual transposition is used when automatic Transpose is off. |
| **OutRange** | Folds notes that fall outside the selected layout's range by octaves instead of discarding them. |
| **VelCurve** | Chooses how incoming MIDI velocity is shaped when Velocity processing is enabled. Built-in curves include Linear Coarse, Soft, Hard, Exponential, Logarithmic, S-Curve, and Flat (max). |

The **Velocity Curve Editor** lets you draw a custom 32-step curve, save it, and apply it. A higher curve value means a stronger outgoing velocity. The **Velocity** tab in **Settings** contains the soft-note modifier and threshold options.

## Configuration and tracks

- **Always On Top** keeps MIDI++ above other windows.
- **Legit Mode** adds small timing variation and spreads chord notes slightly, using the values in **Settings → Legit Mode**.
- **Filter Drums** excludes MIDI percussion channel 10 from song playback.
- **Pause when focus is lost** pauses keyboard-oriented playback while MIDI++ is frontmost or when the configured app filter does not match. Enter an app name in **Only in app** to restrict output to that app. Disable this option if you do not want focus checking.
- **Opacity** adjusts the window transparency.
- **Note Mode (LIFO/FIFO)** controls how overlapping repeated notes with the same pitch are paired when reading MIDI note-on/note-off events.
- **Layout** selects the MIDI-note-to-keyboard map. The built-in **Virtual Piano 88** layout can be supplemented with custom JSON layouts in the `layouts` folder. **Settings → Layout → Export current layout** writes the selected map for editing.
- **Tracks: M** mutes a track; **S** solos it. **Solo Piano** solos tracks identified as piano instruments. **Reset M/S** clears track mute and solo selections.
- **Settings → Hotkeys** lets you change or remove global shortcuts and restore the defaults.

## Global shortcuts

Default shortcuts work while MIDI++ is running, including when another app has focus. The `Ctrl+Option` prefix means Control and Option/Alt together:

| Shortcut | Action |
| --- | --- |
| `Esc` | Stop playback |
| `Ctrl+Option+P` | Play/Pause |
| `Ctrl+Option+R` | Restart |
| `Ctrl+Option+Right` / `Left` | Skip forward / backward 10 seconds |
| `Ctrl+Option+Up` / `Down` | Increase / decrease speed |
| `Ctrl+Option+.` / `,` | Transpose up / down one semitone |
| `Ctrl+Option+L` | Toggle Legit Mode |
| `Ctrl+Option+M` | Toggle Midi2Key IN |

Shortcuts can be changed in **Settings → Hotkeys**. macOS may require Accessibility and Input Monitoring permissions for global key detection.

## Log and utility buttons

- **Clear Log** clears the messages shown in the Log panel.
- **Refresh MIDI** refreshes the list of MIDI input devices.
- **Edit V-Curve** opens the 32-step velocity-curve editor.
- **Ref V-List** reloads saved custom velocity curves.

The log records loaded files, selected song output, MIDI devices, and playback or permission messages. If a song plays through the wrong route, check the `[Load]` line and verify the song output selector before pressing Play.

## Data and saved settings

When run as a script, MIDI++ stores its MIDI files, layouts, velocity curves, and settings beside the script. In a packaged macOS app, it uses:

```text
~/Library/Application Support/MIDI++/
```

The settings file is `midiplusplus_settings.json`. Added MIDI folders, selected output, window preferences, and other configuration are saved when the application closes.

## Troubleshooting

### The song is not playing in the game

1. Confirm the song is loaded and the Log shows the intended **song output**.
2. Select the target game window so it is frontmost.
3. If focus protection is enabled, check **Only in app** and the **Waiting for focus** status.
4. Confirm the selected output matches the game: QWERTY, MidiConnect protocol, or virtual MIDI input.
5. Check macOS Accessibility and Input Monitoring permissions, then restart MIDI++ after changing them.

### MidiConnect IN does not play a song

**MidiConnect IN** is live input for a physical MIDI device. For a MIDI file, select **Config → Song Output → MidiConnect (Roblox)**. The game must support the MIDI++ keypad protocol; merely having another MIDI input option enabled may not be enough.

### No MIDI device appears

Connect or enable the device, then click **Refresh MIDI**. A virtual MIDI device such as **Driver IAC Bus 1** can be selected as an input. A MIDI input device is only needed for MidiConnect IN or Midi2Key IN, not for loading and playing a MIDI file.

### A virtual MIDI output is not visible in another app

Choose **Virtual MIDI Port** or **QWERTY + Virtual MIDI** as the song output, then select **MIDI++ Out** in the receiving app. The receiving app must support CoreMIDI input.

### macOS says the developer cannot be verified

Only open software you trust. If you downloaded MIDI++ from a trusted source and macOS blocks it, use **System Settings → Privacy & Security** to review the app-specific option to open it, or Control-click the app in Finder and choose **Open**. The exact prompt depends on your macOS version and the app's signing/notarization status.

## Known limitations

- The application simulates keyboard events with macOS Quartz. Games and websites differ in whether they accept these events; Accessibility permission is required.
- MidiConnect depends on the target game implementing the compatible numeric-keyboard protocol. It is not a universal MIDI standard or virtual MIDI connection.
- QWERTY key presses usually do not carry real pressure/velocity. Velocity behavior depends on the target app and the selected output route.
- Drag-and-drop is currently disabled in this build. Use **Add Folder…** and **Load** instead.
- Tkinter window aspect-ratio enforcement and MIDI device behavior can vary across macOS and Python/Tk versions.

## Credits and license

MIDI++ for macOS is inspired by [MIDI++ by Zephkek](https://github.com/Zephkek/MIDIPlusPlus). Credit the original project and follow its GPL-3.0 license terms when distributing this reimplementation or derivative work. Include the applicable license text and notices with redistributed copies.
