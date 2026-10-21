# MIDI++ for macOS

MIDI++ is a macOS desktop app that plays Standard MIDI files by translating their notes into keyboard presses for virtual piano websites and other keyboard-controlled instruments.

It also supports connecting a MIDI keyboard and sending its live notes as keyboard input. The app is designed around the **Virtual Piano 88** layout, with additional controls for playback, note range, sustain, velocity, and MIDI output.

## Download

Download the prebuilt macOS disk image:

https://www.mediafire.com/file/r45zbysupac2f8d/MIDI++.dmg/file

The DMG contains the MIDI++ app and an Applications shortcut.

## Install

1. Download and open `MIDI++.dmg`.
2. Drag **MIDI++** onto the **Applications** shortcut.
3. Open MIDI++ from the Applications folder.
4. Grant MIDI++ the required macOS permissions described below.

The prebuilt app includes its Python runtime. You do not need to install Python to use it.

## macOS permissions

MIDI++ sends keyboard events to another app, so macOS must authorize it:

1. Open **System Settings > Privacy & Security > Accessibility**.
2. Add **MIDI++** and enable its switch.
3. If macOS requests it, also enable MIDI++ under **Input Monitoring**.
4. Quit and reopen MIDI++ after changing permissions.

Grant permission to the **MIDI++ app** when using the `.app`. Permission granted to Terminal only applies when running the Python script from Terminal.

### If macOS blocks the app

Because this build may not be notarized by Apple, macOS may say that it cannot verify the developer or check the app for malicious software. Only continue if you trust the app and downloaded it from the link above.

To open it, try right-clicking **MIDI++** in Applications and choosing **Open**. If it is still blocked, try to open it once, then go to **System Settings > Privacy & Security > Security** and choose **Open Anyway**. Confirm the prompt that appears. See [Apple’s instructions](https://support.apple.com/es-la/102445).

## Load and play a MIDI file

1. Click **Add Folder…** and choose a folder containing `.mid` or `.midi` files.
2. Select a song in the MIDI Files list and click **Load**. You can also double-click a song to load it.
3. Focus the virtual piano window so it can receive keyboard events.
4. Click **Play/Pause**.

MIDI++ remembers added folders. Click **Refresh** to scan them again after adding or removing files. The current version scans files directly inside each selected folder, not inside its subfolders.

MIDI++ does not include music files. Add your own MIDI files and make sure you have the right to use or share them.

## Playback controls

- **Load** loads the selected song.
- **Play/Pause** starts or pauses playback.
- **Restart** returns to the beginning.
- **Skip +10** and **Rew −10** move through the song by ten seconds.
- **Speed ++** and **Speed −−** adjust playback speed.
- The progress bar lets you move to another position in the song.
- **Loop** repeats the song when playback reaches the end.

## MIDI keyboard output

MIDI++ has two related live-input controls:

- **MidiConnect** connects to an available MIDI input device.
- **Midi2Key** sends incoming MIDI notes as keyboard presses.

The **Salida** setting selects keyboard output, virtual MIDI output, or both. When using virtual MIDI output, select the **MIDI++ Out** port in your synthesizer or DAW.

## Advanced controls

- **88-Key** enables the Virtual Piano 88 note map.
- **Transpose** adjusts notes automatically or by a chosen number of semitones.
- **OutRange** folds notes into the supported range.
- **Sustain** enables pedal behavior; **Sustain Cutoff** sets its threshold.
- **Velocity**, **VelCurve**, and **AutoVol** control how MIDI velocity affects note output.
- **Legit Mode** adds timing variation and chord spread for a less mechanical performance.
- **Filter Drums** controls whether drum-channel notes are included.
- **Loop** repeats the current song.

## Tracks and preferences

For MIDI files with multiple tracks, use **M** to mute a track and **S** to solo it. **Solo Piano** and **Reset M/S** provide quick track controls.

Other settings include window opacity, Always On Top, pause-on-focus-loss, an optional target-app filter, note handling mode, output type, and keyboard layout. Settings are saved by the app.

## Keyboard layouts

The built-in **Virtual Piano 88** layout maps MIDI notes across the 88-key range. White notes use regular keys, black notes use Shift combinations, and extended notes use Ctrl combinations where the layout requires them. Custom layouts can be exported from the layout settings.

## Known limitation

Drag-and-drop MIDI loading is disabled in this build because its native Tcl/Tk extension is incompatible with some macOS installations. Use **Add Folder…**, **Refresh**, and **Load** instead.

## Build from source

The source is written in Python with Tkinter and uses MIDI and macOS frameworks. The prebuilt app was packaged on an Intel Mac (`x86_64`); compatibility with Apple Silicon builds has not been verified.

On macOS, install Python and the dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install pyinstaller mido python-rtmidi pyobjc-framework-Quartz pyobjc-framework-ApplicationServices pyobjc-framework-Cocoa
```

To run the source:

```bash
python "MIDI++.py"
```

To build the app from the project folder:

```bash
python -m PyInstaller --noconfirm --clean --windowed --name "MIDI++" --icon "MIDI++ Icon.png" --osx-bundle-identifier "com.salva.midiplusplus" --collect-all rtmidi --hidden-import mido.backends.rtmidi "MIDI++.py"
```

This project was developed and packaged on macOS 13.7.8 with Python 3.14.6. Other macOS and Python versions may require adjustments.

## Credits

MIDI++ for macOS is a Python/Tkinter reimplementation inspired by Zephkek’s MIDI++ project:

https://github.com/Zephkek/MIDIPlusPlus

This is not the original Windows application.

## Feedback

If you find a bug or have a suggestion, please open an issue in this repository or leave a comment on the project video.
