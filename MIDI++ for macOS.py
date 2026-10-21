#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MIDI++ para macOS  -  autoplayer MIDI -> QWERTY para pianos virtuales (Virtual Piano, 88 teclas)

Reimplementación en Python/tkinter inspirada en MIDI++ de Zephkek (Windows, GPL-3.0):
https://github.com/Zephkek/MIDIPlusPlus  -  esto NO es su código, es una copia funcional para macOS.

INSTALACIÓN (una vez, en Terminal):
    python3 -m pip install mido python-rtmidi pyobjc-framework-Quartz \
        pyobjc-framework-ApplicationServices pyobjc-framework-Cocoa tkinterdnd2
    (tkinterdnd2 es opcional: permite arrastrar .mid a la ventana)

EJECUTAR:
    python3 midiplusplus_mac.py

PERMISOS: Ajustes del Sistema > Privacidad y seguridad > Accesibilidad (y Monitorización de entrada)
          -> activa la app desde la que lo ejecutas (Terminal, iTerm, VS Code...).

CARPETAS (junto al script, se crean solas):
    midi/      tus .mid          vcurves/   curvas de velocity guardadas (.json)
    layouts/   mapas de teclas personalizados (.json)        midiplusplus_settings.json  ajustes

FUNCIONES
  Playback  : Load, Play/Pause, Restart, Stop, Skip +10, Rew -10, Speed++/--, barra clicable, Loop
  MidiConnect / Midi2Key : conecta un teclado MIDI (p. ej. tu Arduino) y lo convierte a teclas en vivo
  Advanced  : 88-Key, AutoVol, Velocity (32 pasos + curvas + editor), Sustain (+ Sustain Cutoff),
              Transpose (automático por análisis de rango/teclas negras, o manual), OutRange (plegar octavas)
  Config    : Always On Top, Legit Mode (humanización), Filter Drums, Opacity, Note Mode LIFO/FIFO,
              filtro de app / pausa si pierdes el foco, salida a teclas / puerto MIDI virtual
  Tracks    : M (mute), S (solo), instrumento GM, Solo Piano
  Atajos globales remapeables (funcionan con el foco en el navegador). Por defecto:
      ESC detener · Ctrl+Opción+P pausa · +R reiniciar · +→/← saltar ±10 s · +↑/↓ velocidad
      +. / +, transposición · +L legit · +M Midi2Key
"""

import os
import sys
import time
import glob
import json
import math
import queue
import bisect
import random
import threading
import datetime
from collections import defaultdict

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText

try:
    import mido
except ImportError:
    sys.exit("Falta 'mido'. Ejecuta:\n  python3 -m pip install mido python-rtmidi")

try:
    from Quartz import (
        CGEventCreateKeyboardEvent, CGEventSetFlags, CGEventPost,
        CGEventSourceCreate, CGEventSourceKeyState,
        kCGHIDEventTap, kCGEventSourceStatePrivate, kCGEventSourceStateHIDSystemState,
        kCGEventFlagMaskShift, kCGEventFlagMaskControl,
        kCGEventFlagMaskAlternate, kCGEventFlagMaskCommand,
    )
except ImportError:
    sys.exit("Falta pyobjc. Ejecuta:\n  python3 -m pip install pyobjc-framework-Quartz "
             "pyobjc-framework-ApplicationServices pyobjc-framework-Cocoa")

try:
    from AppKit import NSWorkspace

    def app_frontal():
        """(pid, nombre) de la app en primer plano."""
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        if app is None:
            return None, ""
        return app.processIdentifier(), str(app.localizedName() or "")
    FOCO_DISPONIBLE = True
except Exception:
    FOCO_DISPONIBLE = False

    def app_frontal():
        return None, ""

# El arrastre depende de tkinterdnd2, cuya extensión nativa no es compatible
# con algunas versiones Tcl/Tk de macOS. La carga por el botón Abrir sigue
# disponible y evita que la app falle al iniciar.
HAY_DND = False

if getattr(sys, "frozen", False):
    # En una app empaquetada el bundle puede estar en /Applications y no es
    # un lugar apropiado para escribir ajustes o archivos del usuario.
    BASE = os.path.join(os.path.expanduser("~"), "Library", "Application Support", "MIDI++")
else:
    BASE = os.path.dirname(os.path.abspath(__file__))
DIR_MIDI = os.path.join(BASE, "midi")
DIR_CURVAS = os.path.join(BASE, "vcurves")
DIR_LAYOUTS = os.path.join(BASE, "layouts")
ARCH_AJUSTES = os.path.join(BASE, "midiplusplus_settings.json")
for _d in (DIR_MIDI, DIR_CURVAS, DIR_LAYOUTS):
    try:
        os.makedirs(_d, exist_ok=True)
    except OSError:
        pass

# ============================================================================
# Teclado de macOS
# ============================================================================
SHIFT, CTRL = kCGEventFlagMaskShift, kCGEventFlagMaskControl
ALT, CMD = kCGEventFlagMaskAlternate, kCGEventFlagMaskCommand
NINGUNO = 0

KEYCODES = {
    'a': 0, 's': 1, 'd': 2, 'f': 3, 'h': 4, 'g': 5, 'z': 6, 'x': 7, 'c': 8, 'v': 9,
    'b': 11, 'q': 12, 'w': 13, 'e': 14, 'r': 15, 'y': 16, 't': 17,
    '1': 18, '2': 19, '3': 20, '4': 21, '6': 22, '5': 23, '9': 25, '7': 26, '8': 28,
    '0': 29, 'o': 31, 'u': 32, 'i': 34, 'p': 35, 'l': 37, 'j': 38, 'k': 40,
    'n': 45, 'm': 46,
}
ESPECIALES = {
    'space': 49, 'esc': 53, 'return': 36, 'tab': 48, 'delete': 51, 'fwddelete': 117,
    'left': 123, 'right': 124, 'down': 125, 'up': 126, 'home': 115, 'end': 119,
    'pageup': 116, 'pagedown': 121, ',': 43, '.': 47, '/': 44, ';': 41, "'": 39,
    '[': 33, ']': 30, '\\': 42, '-': 27, '=': 24, '`': 50,
    'f1': 122, 'f2': 120, 'f3': 99, 'f4': 118, 'f5': 96, 'f6': 97, 'f7': 98, 'f8': 100,
    'f9': 101, 'f10': 109, 'f11': 103, 'f12': 111,
}
NOMBRE_A_CODIGO = dict(KEYCODES)
NOMBRE_A_CODIGO.update(ESPECIALES)
CODIGO_A_NOMBRE = {v: k for k, v in NOMBRE_A_CODIGO.items()}
KEY_SPACE, KEY_ESC = 49, 53

MOD_CODIGOS = {
    'cmd': (54, 55), 'shift': (56, 60), 'opt': (58, 61), 'ctrl': (59, 62),
}
TODOS_MOD = {c for t in MOD_CODIGOS.values() for c in t} | {57, 63}
MOD_SIMBOLO = {'ctrl': '⌃', 'opt': '⌥', 'shift': '⇧', 'cmd': '⌘'}

_SRC = CGEventSourceCreate(kCGEventSourceStatePrivate)

# Teclas físicas de modificador de macOS. Se mantienen presionadas mientras
# haya al menos una nota generada que dependa de ellas.
MOD_EVENTOS = ((SHIFT, 56), (CTRL, 59), (ALT, 58), (CMD, 55))


def enviar(keycode, abajo, flags):
    ev = CGEventCreateKeyboardEvent(_SRC, keycode, abajo)
    CGEventSetFlags(ev, flags)          # los modificadores van dentro del evento
    CGEventPost(kCGHIDEventTap, ev)


def tecla_abajo(code):
    try:
        return bool(CGEventSourceKeyState(kCGEventSourceStateHIDSystemState, code))
    except Exception:
        return False


def mods_actuales():
    return frozenset(n for n, cods in MOD_CODIGOS.items() if any(tecla_abajo(c) for c in cods))


def texto_atajo(b):
    if not b:
        return "(sin asignar)"
    mods = "".join(MOD_SIMBOLO[m] for m in ('ctrl', 'opt', 'shift', 'cmd') if m in b['mods'])
    return mods + CODIGO_A_NOMBRE.get(b['code'], f"#{b['code']}").upper()


# ============================================================================
# Layouts (mapa nota MIDI -> tecla)
# ============================================================================
def layout_vp88():
    """Mapa de 88 teclas de Virtual Piano.

    En el tramo central C2–C7, las blancas usan la tecla normal y las negras
    usan Shift + esa tecla. Las extensiones inferior y superior asignan un
    carácter distinto a cada nota, todas con Ctrl; allí no se usa Shift.
    """
    km = {}
    naturales = {0, 2, 4, 5, 7, 9, 11}
    chars_centro = "1234567890qwertyuiopasdfghjklzxcvbnm"
    chars_bajos = "1234567890qwert"       # 15 notas: A0–B1
    chars_altos = "yuiopasdfghj"           # 12 notas: C#7–C8

    idx, ultima = -1, None
    for midi in range(36, 97):
        if midi % 12 in naturales:
            idx += 1
            ultima = chars_centro[idx]
            km[midi] = (KEYCODES[ultima], NINGUNO)
        else:
            km[midi] = (KEYCODES[ultima], SHIFT)

    for i, char in enumerate(chars_bajos):
        km[21 + i] = (KEYCODES[char], CTRL)
    for i, char in enumerate(chars_altos):
        km[97 + i] = (KEYCODES[char], CTRL)
    return km


def layout_vp61():
    return {n: v for n, v in layout_vp88().items() if 36 <= n <= 96}


LAYOUTS_INTERNOS = {"Virtual Piano 88": layout_vp88, "Virtual Piano 61": layout_vp61}


def layout_a_json(km):
    out = {}
    for n, (kc, fl) in sorted(km.items()):
        mods = [m for m, f in (("ctrl", CTRL), ("shift", SHIFT), ("alt", ALT), ("cmd", CMD)) if fl & f]
        out[str(n)] = {"key": CODIGO_A_NOMBRE.get(kc, str(kc)), "mods": mods}
    return {"name": "Mi layout", "keys": out}


def layout_desde_json(ruta):
    with open(ruta, "r", encoding="utf-8") as f:
        data = json.load(f)
    km = {}
    for k, v in data["keys"].items():
        kc = NOMBRE_A_CODIGO.get(str(v["key"]).lower())
        if kc is None:
            kc = int(v["key"])
        fl = 0
        for m in v.get("mods", []):
            fl |= {"ctrl": CTRL, "shift": SHIFT, "alt": ALT, "opt": ALT, "cmd": CMD}[m.lower()]
        km[int(k)] = (kc, fl)
    if not km:
        raise ValueError("El layout está vacío")
    return km


# ============================================================================
# Velocity: 32 pasos, curvas, AutoVol
# ============================================================================
PASOS = 32


def _curva(f):
    return [max(0, min(31, int(round(f(i / 31.0) * 31)))) for i in range(PASOS)]


CURVAS_BASE = {
    "Linear Coarse": lambda x: x,
    "Soft": lambda x: x ** 0.6,
    "Hard": lambda x: x ** 1.6,
    "Exponential": lambda x: (math.exp(2 * x) - 1) / (math.exp(2) - 1),
    "Logarithmic": lambda x: math.log1p(9 * x) / math.log(10),
    "S-Curve": lambda x: 0.5 - 0.5 * math.cos(math.pi * x),
    "Flat (max)": lambda x: 1.0,
}


class Curvas:
    def __init__(self, carpeta):
        self.carpeta = carpeta
        self.custom = {}
        self.refrescar()

    def refrescar(self):
        self.custom = {}
        for p in glob.glob(os.path.join(self.carpeta, "*.json")):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    d = json.load(f)
                pasos = [max(0, min(31, int(x))) for x in d["steps"]]
                if len(pasos) == PASOS:
                    self.custom[d.get("name") or os.path.splitext(os.path.basename(p))[0]] = pasos
            except Exception:
                continue

    def nombres(self):
        return list(CURVAS_BASE) + sorted(self.custom)

    def get(self, nombre):
        if nombre in CURVAS_BASE:
            return _curva(CURVAS_BASE[nombre])
        return list(self.custom.get(nombre, _curva(CURVAS_BASE["Linear Coarse"])))

    def guardar(self, nombre, pasos):
        seguro = "".join(c for c in nombre if c.isalnum() or c in " _-") or "curva"
        with open(os.path.join(self.carpeta, seguro + ".json"), "w", encoding="utf-8") as f:
            json.dump({"name": nombre, "steps": list(pasos)}, f)
        self.custom[nombre] = list(pasos)


def nivel_a_vel(nivel):
    return max(1, min(127, int((nivel + 0.5) * 4)))


def autovol_params(notas):
    vs = sorted(n[5] for n in notas)
    if len(vs) < 8:
        return None
    a = vs[int(len(vs) * 0.05)]
    b = vs[max(0, int(len(vs) * 0.95) - 1)]
    if b - a < 4:
        return None
    return a, b


# ============================================================================
# Lectura del MIDI (con corrección de errores)
# ============================================================================
GM = ["Acoustic Grand Piano", "Bright Acoustic Piano", "Electric Grand Piano", "Honky-tonk Piano",
      "Electric Piano 1", "Electric Piano 2", "Harpsichord", "Clavinet", "Celesta", "Glockenspiel",
      "Music Box", "Vibraphone", "Marimba", "Xylophone", "Tubular Bells", "Dulcimer", "Drawbar Organ",
      "Percussive Organ", "Rock Organ", "Church Organ", "Reed Organ", "Accordion", "Harmonica",
      "Tango Accordion", "Acoustic Guitar (nylon)", "Acoustic Guitar (steel)", "Electric Guitar (jazz)",
      "Electric Guitar (clean)", "Electric Guitar (muted)", "Overdriven Guitar", "Distortion Guitar",
      "Guitar Harmonics", "Acoustic Bass", "Electric Bass (finger)", "Electric Bass (pick)",
      "Fretless Bass", "Slap Bass 1", "Slap Bass 2", "Synth Bass 1", "Synth Bass 2", "Violin", "Viola",
      "Cello", "Contrabass", "Tremolo Strings", "Pizzicato Strings", "Orchestral Harp", "Timpani",
      "String Ensemble 1", "String Ensemble 2", "Synth Strings 1", "Synth Strings 2", "Choir Aahs",
      "Voice Oohs", "Synth Voice", "Orchestra Hit", "Trumpet", "Trombone", "Tuba", "Muted Trumpet",
      "French Horn", "Brass Section", "Synth Brass 1", "Synth Brass 2", "Soprano Sax", "Alto Sax",
      "Tenor Sax", "Baritone Sax", "Oboe", "English Horn", "Bassoon", "Clarinet", "Piccolo", "Flute",
      "Recorder", "Pan Flute", "Blown Bottle", "Shakuhachi", "Whistle", "Ocarina", "Lead 1 (square)",
      "Lead 2 (sawtooth)", "Lead 3 (calliope)", "Lead 4 (chiff)", "Lead 5 (charang)", "Lead 6 (voice)",
      "Lead 7 (fifths)", "Lead 8 (bass+lead)", "Pad 1 (new age)", "Pad 2 (warm)", "Pad 3 (polysynth)",
      "Pad 4 (choir)", "Pad 5 (bowed)", "Pad 6 (metallic)", "Pad 7 (halo)", "Pad 8 (sweep)",
      "FX 1 (rain)", "FX 2 (soundtrack)", "FX 3 (crystal)", "FX 4 (atmosphere)", "FX 5 (brightness)",
      "FX 6 (goblins)", "FX 7 (echoes)", "FX 8 (sci-fi)", "Sitar", "Banjo", "Shamisen", "Koto",
      "Kalimba", "Bagpipe", "Fiddle", "Shanai", "Tinkle Bell", "Agogo", "Steel Drums", "Woodblock",
      "Taiko Drum", "Melodic Tom", "Synth Drum", "Reverse Cymbal", "Guitar Fret Noise", "Breath Noise",
      "Seashore", "Bird Tweet", "Telephone Ring", "Helicopter", "Applause", "Gunshot"]


class Cancion:
    pass


def cargar_cancion(ruta, modo_notas="LIFO"):
    # clip=True corrige bytes de datos fuera de rango (archivos dañados)
    mid = mido.MidiFile(ruta, clip=True)
    if mid.type == 2:
        raise ValueError("Los MIDI de tipo 2 no están soportados")
    tpb = mid.ticks_per_beat or 480
    errores = 0

    tempos = {0: 500000}
    n_tempos = 0
    compas = None
    for tr in mid.tracks:
        tick = 0
        for m in tr:
            tick += m.time
            if m.type == 'set_tempo' and m.tempo > 0:
                tempos[tick] = m.tempo
                n_tempos += 1
            elif m.type == 'time_signature' and compas is None:
                compas = f"{m.numerator}/{m.denominator}"
    ticks_l = sorted(tempos)
    tempo_l = [tempos[k] for k in ticks_l]
    sec_l = [0.0]
    for i in range(1, len(ticks_l)):
        sec_l.append(sec_l[-1] + (ticks_l[i] - ticks_l[i - 1]) * tempo_l[i - 1] / 1e6 / tpb)

    def t2s(tick):
        i = bisect.bisect_right(ticks_l, tick) - 1
        return sec_l[i] + (tick - ticks_l[i]) * tempo_l[i] / 1e6 / tpb

    pop_idx = -1 if modo_notas == "LIFO" else 0
    c = Cancion()
    c.ruta, c.nombre = ruta, os.path.basename(ruta)
    c.formato, c.bpm0, c.n_tempos = mid.type, 60e6 / tempo_l[0], n_tempos
    c.compas = compas or "4/4"
    c.modo_notas = modo_notas
    c.notas, c.pedal, c.pistas = [], [], []     # notas: (ini, fin, nota, pista, canal, vel)

    for ti, tr in enumerate(mid.tracks):
        nombre, programa, tick = None, None, 0
        activas = defaultdict(list)
        ln = []
        for m in tr:
            tick += m.time
            if m.is_meta:
                if m.type == 'track_name' and nombre is None:
                    nombre = m.name.strip()
                continue
            if m.type == 'program_change' and programa is None:
                programa = m.program
            elif m.type == 'note_on' and m.velocity > 0:
                activas[(m.channel, m.note)].append((tick, m.velocity))
            elif m.type in ('note_off', 'note_on'):
                lista = activas[(m.channel, m.note)]
                if lista:
                    ini, vel = lista.pop(pop_idx)
                    ln.append((t2s(ini), t2s(tick), m.note, m.channel, vel))
                else:
                    errores += 1                       # note_off huérfano: se ignora
            elif m.type == 'control_change' and m.control == 64:
                c.pedal.append((t2s(tick), m.value))
        for (ch, nota), lista in activas.items():      # notas que nunca se cerraron
            for ini, vel in lista:
                ln.append((t2s(ini), t2s(tick), nota, ch, vel))
                errores += 1
        if ln:
            pi = len(c.pistas)
            canales = {x[3] for x in ln}
            bateria = canales == {9}
            gm = "Drums" if bateria else (GM[programa] if programa is not None and programa < 128
                                          else "Acoustic Grand Piano")
            c.pistas.append({'nombre': nombre or f"Pista {ti + 1}", 'notas': len(ln),
                             'bateria': bateria, 'gm': gm, 'piano': (not bateria) and
                             (programa is None or programa < 8)})
            for ini, fin, nota, ch, vel in ln:
                if fin < ini:
                    ini, fin = fin, ini
                    errores += 1
                c.notas.append((ini, fin, nota, pi, ch, vel))

    c.pedal.sort()
    c.errores = errores
    c.duracion = max((n[1] for n in c.notas), default=0.0)
    return c


# ============================================================================
# Compilación: canción + ajustes -> eventos
# ============================================================================
MIN_PULSACION = 0.030
HUECO = 0.004
NEGRAS = {1, 3, 6, 8, 10}


def rango_teclas(cfg):
    km = cfg['keymap']
    lo, hi = min(km), max(km)
    if not cfg['k88']:
        lo, hi = max(lo, 36), min(hi, 96)
    return lo, hi


def notas_filtradas(c, cfg):
    solo, mute = cfg['solo'], cfg['mute']
    out = []
    for n in c.notas:
        if cfg['drums'] and n[4] == 9:
            continue
        if solo:
            if n[3] not in solo:
                continue
        elif n[3] in mute:
            continue
        out.append(n)
    return out


def auto_transponer(notas, cfg):
    """Elige el desplazamiento (-11..+11) que deja menos notas fuera de rango y menos teclas negras
    (menos Shift), penalizando desplazamientos grandes."""
    lo, hi = rango_teclas(cfg)
    hist = defaultdict(int)
    for n in notas:
        hist[n[2]] += 1
    if not hist:
        return 0
    total = sum(hist.values())
    mejor, mejor_s = 0, None
    for t in range(-11, 12):
        s = 0.0
        for nota, k in hist.items():
            n = nota + t
            if n < lo or n > hi:
                s += 4 * k
                if hi - lo >= 11:
                    while n < lo:
                        n += 12
                    while n > hi:
                        n -= 12
            if n % 12 in NEGRAS:
                s += k
        s += abs(t) * total * 0.02
        if mejor_s is None or s < mejor_s - 1e-9:
            mejor, mejor_s = t, s
    return mejor


def mapear(cfg, nota, t, lo, hi):
    """nota MIDI -> ((nota_final, keycode, flags) | None, fuera_de_rango)"""
    n = nota + t
    fuera = False
    if n < lo or n > hi:
        fuera = True
        if not cfg['fold'] or hi - lo < 11:
            return None, True
        while n < lo:
            n += 12
        while n > hi:
            n -= 12
    m = cfg['keymap'].get(n)
    if m is None:
        return None, fuera
    return (n, m[0], m[1]), fuera


def compilar(c, cfg):
    """-> (eventos, notas_a_tocar, fuera_de_rango, transposicion_efectiva)
    evento = (tiempo, orden, tipo, abajo, keycode, flags, nota, vel)   tipo 0=nota 1=pedal"""
    lo, hi = rango_teclas(cfg)
    notas = notas_filtradas(c, cfg)
    t_eff = auto_transponer(notas, cfg) if cfg['auto'] else cfg['transp']
    av = autovol_params(notas) if cfg['autovol'] else None
    rng = random.Random(1337)
    legit = cfg['legit']
    jit, spread = cfg['jitter'] / 1000.0, cfg['spread'] / 1000.0

    offs = {}
    if legit and spread > 0:                         # los acordes no suenan exactamente a la vez
        orden = sorted(range(len(notas)), key=lambda i: notas[i][0])
        i = 0
        while i < len(orden):
            j = i
            while j + 1 < len(orden) and notas[orden[j + 1]][0] - notas[orden[i]][0] < 0.012:
                j += 1
            grupo = sorted(orden[i:j + 1], key=lambda k: notas[k][2])
            m = len(grupo)
            if m > 1:
                for r, k in enumerate(grupo):
                    offs[k] = r * spread / (m - 1) * rng.uniform(0.6, 1.0)
            i = j + 1

    por_tecla = defaultdict(list)
    fuera = 0
    for idx, (ini, fin, nota, pi, ch, vel) in enumerate(notas):
        res, f = mapear(cfg, nota, t_eff, lo, hi)
        if f:
            fuera += 1
        if res is None:
            continue
        n, kc, fl = res
        v = vel
        if av:
            a, b = av
            v = int(max(1, min(127, 24 + (vel - a) / float(b - a) * (127 - 24))))
        if cfg['velocity']:
            nivel = cfg['curva'][min(31, max(0, v // 4))]
            vout = nivel_a_vel(nivel)
            if cfg['vel_mod'] == 'alt' and nivel < cfg['vel_thr']:
                fl |= ALT
        else:
            vout = v
        if legit:
            dur = fin - ini
            ini = max(0.0, ini + rng.uniform(-jit, jit) + offs.get(idx, 0.0))
            fin = ini + dur * rng.uniform(0.85, 1.1)
        por_tecla[(kc, fl)].append([ini, fin, n, vout])

    eventos, total = [], 0
    for (kc, fl), lista in por_tecla.items():
        lista.sort()
        for i, (ini, fin, n, vout) in enumerate(lista):
            if i + 1 < len(lista):
                sig = lista[i + 1][0]
                if sig - ini < 0.002:
                    continue
                fin = min(max(fin, ini + MIN_PULSACION), sig - HUECO)
                if fin <= ini:
                    fin = ini + 0.001
            else:
                fin = max(fin, ini + MIN_PULSACION)
            eventos.append((ini, 1, 0, True, kc, fl, n, vout))
            eventos.append((fin, 0, 0, False, kc, fl, n, 0))
            total += 1

    if cfg['pedal']:
        estado = False
        for t, valor in c.pedal:
            abajo = valor >= cfg['cutoff']
            if abajo != estado:
                estado = abajo
                eventos.append((t, 1 if abajo else 0, 1, abajo, 0, 0, 64, 127 if abajo else 0))

    eventos.sort(key=lambda e: (e[0], e[1]))
    return eventos, total, fuera, t_eff


# ============================================================================
# Salida (teclas y/o puerto MIDI virtual)
# ============================================================================
class Salida:
    def __init__(self, log):
        self.log = log
        self.lock = threading.RLock()
        self.modo = 'keys'                 # keys | midi | both
        self.port = None
        self.sustain_key = KEY_SPACE
        self.held_keys, self.held_notes = set(), set()
        self.pedal_abajo = False
        self.bloqueado = False             # lo actualiza la UI (foco)

    def set_modo(self, modo):
        with self.lock:
            self.soltar_todo()
            self.modo = modo
            if modo in ('midi', 'both'):
                if self.port is None:
                    try:
                        self.port = mido.open_output("MIDI++ Out", virtual=True)
                        self.log("[MIDI] Puerto virtual 'MIDI++ Out' creado (elígelo en tu sintetizador/DAW)")
                    except Exception as e:
                        self.log(f"⚠ No pude crear el puerto MIDI virtual: {e}  (¿python-rtmidi instalado?)")
                        self.modo = 'keys'
            elif self.port is not None:
                try:
                    self.port.close()
                except Exception:
                    pass
                self.port = None

    def nota(self, abajo, kc, fl, nota, vel):
        with self.lock:
            if abajo and self.bloqueado and self.modo != 'midi':
                return
            if self.modo in ('keys', 'both'):
                ident = (kc, fl)
                if abajo:
                    # Un note-on repetido para la misma tecla cierra primero
                    # la pulsación anterior para evitar teclas atascadas.
                    if ident in self.held_keys:
                        self._soltar_tecla(kc, fl)
                        self._modificadores_tap(kc, fl)
                        self.held_keys.add(ident)
                    else:
                        # La blanca y su sostenido comparten keycode: hacer
                        # handoff a la última nota evita volver a disparar la
                        # anterior. El pedal puede sostener su sonido acústico.
                        en_misma_tecla = [par for par in self.held_keys if par[0] == kc]
                        for anterior in en_misma_tecla:
                            _, flags_anteriores = anterior
                            enviar(kc, False, flags_anteriores)
                            self.held_keys.discard(anterior)
                        self._modificadores_tap(kc, fl)
                        self.held_keys.add(ident)
                else:
                    self._soltar_tecla(kc, fl)
            if self.modo in ('midi', 'both') and self.port is not None:
                try:
                    if abajo:
                        self.port.send(mido.Message('note_on', note=int(nota), velocity=int(vel)))
                        self.held_notes.add(nota)
                    else:
                        self.port.send(mido.Message('note_off', note=int(nota)))
                        self.held_notes.discard(nota)
                except Exception:
                    pass

    def _modificadores_tap(self, kc, flags):
        """Pulsa modificadores solo durante el key-down de la nota.

        La nota principal queda sostenida hasta su note-off; Ctrl/Shift/Alt/Cmd
        se liberan de inmediato para permitir acordes con teclas modificadas y
        normales a la vez.
        """
        activos = [(flag, keycode) for flag, keycode in MOD_EVENTOS if flags & flag]
        for flag, keycode in activos:
            enviar(keycode, True, flag)
        enviar(kc, True, flags)
        for flag, keycode in reversed(activos):
            enviar(keycode, False, 0)

    def _soltar_tecla(self, kc, fl):
        ident = (kc, fl)
        if ident not in self.held_keys:
            return
        # El modificador ya fue liberado tras el key-down; solo termina aquí
        # la duración de la tecla principal.
        enviar(kc, False, fl)
        self.held_keys.discard(ident)

    def pedal(self, abajo):
        with self.lock:
            if abajo == self.pedal_abajo:
                return
            self.pedal_abajo = abajo
            if self.modo in ('keys', 'both'):
                enviar(self.sustain_key, abajo, 0)
            if self.modo in ('midi', 'both') and self.port is not None:
                try:
                    self.port.send(mido.Message('control_change', control=64, value=127 if abajo else 0))
                except Exception:
                    pass

    def soltar_todo(self):
        with self.lock:
            for kc, fl in list(self.held_keys):
                self._soltar_tecla(kc, fl)
            self.held_keys.clear()
            if self.pedal_abajo:
                self.pedal(False)
            if self.port is not None:
                for n in list(self.held_notes):
                    try:
                        self.port.send(mido.Message('note_off', note=int(n)))
                    except Exception:
                        pass
            self.held_notes.clear()

    def hay_algo(self):
        return bool(self.held_keys or self.held_notes or self.pedal_abajo)


# ============================================================================
# Reproductor (hilo)
# ============================================================================
class Player(threading.Thread):
    def __init__(self, out, log):
        super().__init__(daemon=True)
        self.out, self.log = out, log
        self.lock = threading.RLock()
        self.song = None
        self.cfg = dict(
            transp=0, auto=False, k88=True, fold=True, pedal=False, cutoff=64, drums=True,
            mute=set(), solo=set(), guard=True, legit=False, jitter=12, spread=8,
            velocity=False, autovol=False, curva=_curva(CURVAS_BASE["Linear Coarse"]),
            vel_mod='alt', vel_thr=12, keymap=layout_vp88(), loop=False)
        self.speed = 1.0
        self.state = 'stopped'          # stopped | playing | paused
        self.events, self.times, self.idx = [], [], 0
        self.dirty = True
        self.a_pos, self.a_wall, self.running = 0.0, time.perf_counter(), False
        self.blocked = False
        self.countdown_until = 0.0
        self.t_eff = 0
        self._quit = False

    # ---- reloj ----
    def _pos(self):
        if self.running:
            return self.a_pos + (time.perf_counter() - self.a_wall) * self.speed
        return self.a_pos

    def get_pos(self):
        with self.lock:
            return min(self._pos(), self.song.duracion) if self.song else 0.0

    def _reanchor(self):
        self.a_pos = self._pos()
        self.a_wall = time.perf_counter()

    # ---- API ----
    def load(self, cancion):
        self.stop(silencioso=True)
        with self.lock:
            self.song = cancion
            self.cfg['mute'], self.cfg['solo'] = set(), set()
            self.a_pos, self.dirty = 0.0, True

    def update_cfg(self, **kw):
        with self.lock:
            self.cfg.update(kw)
            self.dirty = True

    def set_speed(self, v):
        with self.lock:
            self._reanchor()
            self.speed = max(0.1, min(4.0, v))

    def play_pause(self):
        with self.lock:
            if not self.song:
                return
            if self.state == 'playing':
                self._reanchor()
                self.running = False
                self.state = 'paused'
                self.out.soltar_todo()
                self.log("⏸ Pausa")
            else:
                self.dirty = True
                msg = "▶ Play" if self.state == 'stopped' else "▶ Reanudar"
                self.state = 'playing'
                if not FOCO_DISPONIBLE:
                    self.countdown_until = time.perf_counter() + 3.0
                    self.log(f"{msg} — empieza en 3 s, cliquea Virtual Piano")
                else:
                    self.log(f"{msg} — cliquea Virtual Piano para que suene")

    def stop(self, silencioso=False):
        with self.lock:
            if self.state != 'stopped' and not silencioso:
                self.log("■ Detenido")
            self.state = 'stopped'
            self.running = False
            self.a_pos = 0.0
            self.dirty = True
            self.out.soltar_todo()

    def restart(self):
        with self.lock:
            if not self.song:
                return
            self.running = False
            self.a_pos = 0.0
            self.dirty = True
            self.out.soltar_todo()
            if self.state != 'playing':
                self.play_pause()
            else:
                self.log("↺ Restart")

    def seek(self, delta):
        with self.lock:
            if not self.song:
                return
            nuevo = max(0.0, min(self.song.duracion, self._pos() + delta))
            self.a_pos, self.a_wall = nuevo, time.perf_counter()
            self.dirty = True
            self.out.soltar_todo()

    def seek_abs(self, seg):
        with self.lock:
            if not self.song:
                return
            self.a_pos, self.a_wall = max(0.0, min(self.song.duracion, seg)), time.perf_counter()
            self.dirty = True
            self.out.soltar_todo()

    def stats(self):
        with self.lock:
            if not self.song:
                return 0, 0, 0
            _, total, fuera, t = compilar(self.song, self.cfg)
            self.t_eff = t
            return total, fuera, t

    def quit(self):
        self._quit = True
        self.out.soltar_todo()

    # ---- internos ----
    def _rebuild(self):
        pos = self._pos()
        ev, _, _, t = compilar(self.song, self.cfg)
        self.t_eff = t
        self.events = ev
        self.times = [e[0] for e in ev]
        self.idx = bisect.bisect_left(self.times, pos)
        self.dirty = False
        self.out.soltar_todo()

    def _finish(self):
        with self.lock:
            self.out.soltar_todo()
            if self.cfg['loop']:
                self.a_pos, self.a_wall, self.dirty = 0.0, time.perf_counter(), True
                self.log("↻ Loop")
                return
            self.state, self.running, self.a_pos, self.dirty = 'stopped', False, 0.0, True
        self.log("✔ Terminó")

    def _paso(self):
        now = time.perf_counter()
        bloqueado = (self.blocked and self.cfg['guard']) or now < self.countdown_until
        with self.lock:
            if self.state != 'playing' or not self.song:
                return
            if bloqueado == self.running:
                self._reanchor()
                self.running = not bloqueado
            if not self.running:
                if self.out.hay_algo():
                    self.out.soltar_todo()
                time.sleep(0.02)
                return
            if self.dirty:
                self._rebuild()
            if self.idx >= len(self.events):
                fin, resta, ev = True, 0, None
            else:
                fin = False
                ev = self.events[self.idx]
                resta = (ev[0] - self._pos()) / self.speed
        if fin:
            self._finish()
            return
        if resta > 0.004:
            time.sleep(min(resta - 0.002, 0.02))
            return
        if resta > 0:
            return                     # espera activa los últimos ms
        with self.lock:
            if self.state != 'playing' or self.dirty or not self.running:
                return
            _, _, tipo, abajo, kc, fl, nota, vel = ev
            if tipo == 0:
                self.out.nota(abajo, kc, fl, nota, vel)
            else:
                self.out.pedal(abajo)
            self.idx += 1

    def run(self):
        while not self._quit:
            try:
                if self.state != 'playing':
                    time.sleep(0.02)
                    continue
                self._paso()
            except Exception as e:
                self.log(f"⚠ Error: {e}")
                self.state, self.running = 'stopped', False
                self.out.soltar_todo()


# ============================================================================
# Entrada MIDI en vivo (MidiConnect / Midi2Key)
# ============================================================================
class EntradaMidi:
    def __init__(self, player, out, log):
        self.player, self.out, self.log = player, out, log
        self.port = None
        self.midi2key = False
        self.canal = None                 # None = todos
        self.activas = {}                 # nota entrante -> (n, kc, fl)
        self._aviso = False

    def dispositivos(self):
        try:
            return list(mido.get_input_names())
        except Exception as e:
            if not self._aviso:
                self._aviso = True
                self.log(f"⚠ No puedo listar dispositivos MIDI ({e}). Instala: python3 -m pip install python-rtmidi")
            return []

    def conectar(self, nombre):
        self.desconectar()
        try:
            self.port = mido.open_input(nombre, callback=self._cb)
            self.log(f"[MidiConnect] Conectado a: {nombre}")
            return True
        except Exception as e:
            self.log(f"⚠ No pude abrir '{nombre}': {e}")
            self.port = None
            return False

    def desconectar(self):
        if self.port is not None:
            try:
                self.port.close()
            except Exception:
                pass
            self.port = None
            self.log("[MidiConnect] Desconectado")
        self.soltar_todo()

    def soltar_todo(self):
        for n, (nn, kc, fl) in list(self.activas.items()):
            self.out.nota(False, kc, fl, nn, 0)
        self.activas.clear()

    def _cb(self, msg):
        if not self.midi2key:
            return
        try:
            if self.canal is not None and getattr(msg, 'channel', None) != self.canal:
                return
            cfg = self.player.cfg
            if msg.type == 'note_on' and msg.velocity > 0:
                lo, hi = rango_teclas(cfg)
                t = cfg['transp'] if not cfg['auto'] else 0
                res, _ = mapear(cfg, msg.note, t, lo, hi)
                if res is None:
                    return
                n, kc, fl = res
                if cfg['velocity']:
                    nivel = cfg['curva'][min(31, msg.velocity // 4)]
                    vout = nivel_a_vel(nivel)
                    if cfg['vel_mod'] == 'alt' and nivel < cfg['vel_thr']:
                        fl |= ALT
                else:
                    vout = msg.velocity
                if msg.note in self.activas:
                    _, okc, ofl = self.activas[msg.note]
                    self.out.nota(False, okc, ofl, n, 0)
                self.activas[msg.note] = (n, kc, fl)
                self.out.nota(True, kc, fl, n, vout)
            elif msg.type in ('note_off', 'note_on'):
                a = self.activas.pop(msg.note, None)
                if a:
                    self.out.nota(False, a[1], a[2], a[0], 0)
            elif msg.type == 'control_change' and msg.control == 64 and cfg['pedal']:
                self.out.pedal(msg.value >= cfg['cutoff'])
        except Exception as e:
            self.log(f"⚠ Midi2Key: {e}")


# ============================================================================
# Atajos globales (sondeo del teclado)
# ============================================================================
ACCIONES = [
    ("play_pause", "Play / Pause", {"mods": ["ctrl", "opt"], "code": 35}),
    ("stop", "Stop", {"mods": [], "code": 53}),
    ("restart", "Restart", {"mods": ["ctrl", "opt"], "code": 15}),
    ("skip", "Skip +10 s", {"mods": ["ctrl", "opt"], "code": 124}),
    ("rew", "Rew −10 s", {"mods": ["ctrl", "opt"], "code": 123}),
    ("speed_up", "Speed ++", {"mods": ["ctrl", "opt"], "code": 126}),
    ("speed_down", "Speed −−", {"mods": ["ctrl", "opt"], "code": 125}),
    ("transp_up", "Transpose +1", {"mods": ["ctrl", "opt"], "code": 47}),
    ("transp_down", "Transpose −1", {"mods": ["ctrl", "opt"], "code": 43}),
    ("legit", "Legit Mode on/off", {"mods": ["ctrl", "opt"], "code": 37}),
    ("midi2key", "Midi2Key on/off", {"mods": ["ctrl", "opt"], "code": 46}),
]


class Atajos(threading.Thread):
    def __init__(self, get_bindings, disparar):
        super().__init__(daemon=True)
        self.get_bindings, self.disparar = get_bindings, disparar
        self.prev = {}
        self._quit = False
        self.pausado = False         # se pausa mientras se captura un atajo

    def run(self):
        while not self._quit:
            time.sleep(0.015)
            if self.pausado:
                continue
            try:
                b = self.get_bindings()
                mods = None
                for nombre, bind in b.items():
                    if not bind:
                        continue
                    if not tecla_abajo(bind['code']):
                        self.prev[nombre] = False
                        continue
                    if mods is None:
                        mods = mods_actuales()
                    ok = (mods == frozenset(bind['mods']))
                    if ok and not self.prev.get(nombre):
                        self.disparar(nombre)
                    self.prev[nombre] = ok
            except Exception:
                pass


def capturar_combinacion(root, titulo, atajos, callback):
    win = tk.Toplevel(root)
    win.title(titulo)
    win.transient(root)
    ttk.Label(win, text="Suelta todas las teclas y pulsa la nueva combinación…\n(se cancela solo en 10 s)",
              padding=16, justify="center").pack()
    ttk.Button(win, text="Cancelar", command=win.destroy).pack(pady=(0, 12))
    atajos.pausado = True
    est = {'soltar': True, 'fin': time.time() + 10}

    def cerrar():
        atajos.pausado = False
        if win.winfo_exists():
            win.destroy()

    def sondeo():
        if not win.winfo_exists():
            atajos.pausado = False
            return
        pres = [c for c in range(128) if tecla_abajo(c)]
        if est['soltar']:
            if not pres:
                est['soltar'] = False
        else:
            normales = [c for c in pres if c not in TODOS_MOD]
            if normales:
                mods = sorted(mods_actuales())
                cerrar()
                callback(mods, normales[0])
                return
        if time.time() > est['fin']:
            cerrar()
            return
        win.after(30, sondeo)

    win.protocol("WM_DELETE_WINDOW", cerrar)
    sondeo()


# ============================================================================
# Ajustes
# ============================================================================
AJ_DEF = dict(
    k88=True, fold=True, pedal=False, drums=True, auto=False, transp=0, cutoff=64,
    legit=False, jitter=12, spread=8, velocity=False, autovol=False, curva="Linear Coarse",
    vel_mod='alt', vel_thr=12, guard=True, app_filtro="", top=True, alpha=1.0, loop=False,
    salida='keys', layout="Virtual Piano 88", speed=1.0, modo_notas="LIFO",
    hotkeys={n: b for n, _, b in ACCIONES}, sustain_key=KEY_SPACE,
    last_file="", midi_in="", midi_canal=0, midi2key=False, midi_dirs=[])


def cargar_ajustes():
    aj = json.loads(json.dumps(AJ_DEF))
    try:
        with open(ARCH_AJUSTES, "r", encoding="utf-8") as f:
            d = json.load(f)
        for k, v in d.items():
            if k == 'hotkeys' and isinstance(v, dict):
                aj['hotkeys'].update(v)
            elif k in aj:
                aj[k] = v
    except Exception:
        pass
    return aj


def guardar_ajustes(aj):
    try:
        with open(ARCH_AJUSTES, "w", encoding="utf-8") as f:
            json.dump(aj, f, indent=1)
    except Exception:
        pass


# ============================================================================
# Interfaz
# ============================================================================
def fmt(seg):
    seg = int(seg)
    return f"{seg // 60}:{seg % 60:02d}"


SALIDAS = {"Teclas (Virtual Piano)": "keys", "Puerto MIDI virtual": "midi", "Teclas + Puerto MIDI": "both"}


class App:
    def __init__(self, root):
        self.root = root
        root.title("MIDI++ para macOS")
        self._configurar_ventana()

        self.aj = cargar_ajustes()
        self.logq, self.accionq = queue.Queue(), queue.Queue()
        self.curvas = Curvas(DIR_CURVAS)
        self.out = Salida(self.log_t)
        self.player = Player(self.out, self.log_t)
        self.entrada = EntradaMidi(self.player, self.out, self.log_t)
        self.atajos = Atajos(lambda: self.aj['hotkeys'], self._disparar)
        self.archivos, self.track_vars = [], []
        self.dispositivos = []
        self.editor_curva = None

        self._construir()
        self._aplicar_ajustes_iniciales()

        self.player.start()
        self.atajos.start()
        self.refrescar_lista()
        self.refrescar_midi()

        self.log("===== MIDI++ para macOS =====")
        self.log("Inspirado en MIDI++ de Zephkek · ESC = detener · Ctrl+Opción+P = pausa")
        if not FOCO_DISPONIBLE:
            self.log("(sin pyobjc-framework-Cocoa: se usa cuenta atrás de 3 s en vez de detectar el foco)")
        if not HAY_DND:
            self.log("(para arrastrar archivos: python3 -m pip install tkinterdnd2)")
        self._chequear_accesibilidad()

        ult = self.aj.get('last_file')
        if ult and os.path.isfile(ult):
            self.cargar_ruta(ult, silencioso=True)

        root.protocol("WM_DELETE_WINDOW", self.cerrar)
        self.tick()

    def _configurar_ventana(self):
        """Abre en proporción 12:10, dentro del área visible sobre el Dock."""
        self.root.update_idletasks()
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        margin_x = max(12, int(screen_w * 0.015))
        top = max(24, int(screen_h * 0.035))
        dock = max(72, int(screen_h * 0.10))
        bottom = max(16, int(screen_h * 0.025))
        available_w = max(1, screen_w - 2 * margin_x)
        available_h = max(1, screen_h - top - dock - bottom)

        # Relación 12:10: un poco más ancha que alta.
        height = min(available_h, int(available_w * 10 / 12))
        width = min(available_w, int(height * 12 / 10))
        x = max(0, (screen_w - width) // 2)
        self.root.geometry(f"{width}x{height}+{x}+{top}")
        min_h = max(1, int(height * 0.70))
        self.root.minsize(int(min_h * 12 / 10), min_h)
        self._ancho_maximo = available_w
        self._alto_maximo = available_h
        self._ajustando_aspecto = False
        try:
            self.root.wm_aspect(6, 5, 6, 5)
        except tk.TclError:
            pass
        # Refuerzo para gestores de ventanas que no respeten wm_aspect.
        self.root.bind("<Configure>", self._mantener_ventana_12_10, add="+")

    def _mantener_ventana_12_10(self, event):
        if event.widget is not self.root or self._ajustando_aspecto:
            return
        width, height = event.width, event.height
        if abs(width * 5 - height * 6) <= 6:
            return

        if width * 5 > height * 6:
            height = int(width * 5 / 6)
        else:
            width = int(height * 6 / 5)
        escala = min(1.0, self._ancho_maximo / max(1, width),
                     self._alto_maximo / max(1, height))
        width, height = max(1, int(width * escala)), max(1, int(height * escala))
        self._ajustando_aspecto = True

        def aplicar_geometria():
            # No fijar x/y: así el usuario puede redimensionar sin que la
            # ventana salte de su posición actual.
            self.root.geometry(f"{width}x{height}")
            self._ajustando_aspecto = False

        self.root.after_idle(aplicar_geometria)

    # ---------- construcción ----------
    def _construir(self):
        r = self.root
        pad = dict(padx=6, pady=3)
        # Desplazamiento vertical para conservar la interfaz clásica de dos
        # columnas cuando el contenido supera la altura visible sobre el Dock.
        contenedor = ttk.Frame(r)
        contenedor.pack(fill="both", expand=True, padx=8, pady=8)
        lienzo = tk.Canvas(contenedor, highlightthickness=0)
        barra_vertical = ttk.Scrollbar(contenedor, orient="vertical", command=lienzo.yview)
        lienzo.configure(yscrollcommand=barra_vertical.set)
        barra_vertical.pack(side="right", fill="y")
        lienzo.pack(side="left", fill="both", expand=True)
        main = ttk.Frame(lienzo)
        ventana_main = lienzo.create_window((0, 0), window=main, anchor="nw")
        main.columnconfigure(0, weight=0, minsize=260)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(3, weight=1)

        def ajustar_scroll(_event=None):
            lienzo.configure(scrollregion=lienzo.bbox("all"))

        def ajustar_ancho(event):
            lienzo.itemconfigure(ventana_main, width=event.width)

        main.bind("<Configure>", ajustar_scroll)
        lienzo.bind("<Configure>", ajustar_ancho)

        def rueda_principal(event):
            widget = self.root.winfo_containing(event.x_root, event.y_root)
            if widget is not None and widget.winfo_class() in {"Listbox", "Text"}:
                return  # conserva el desplazamiento propio de MIDI Files y Log
            lienzo.yview_scroll(-1 if event.delta > 0 else 1, "units")
            return "break"

        lienzo.bind_all("<MouseWheel>", rueda_principal)

        # --- MIDI Files ---
        fr_files = ttk.LabelFrame(main, text="MIDI Files")
        # Se extiende hasta la fila de Details; el panel de Details queda
        # únicamente en la columna derecha y no ocupa todo el ancho.
        fr_files.grid(row=0, column=0, rowspan=4, sticky="nsew", padx=(0, 8))
        top = ttk.Frame(fr_files)
        top.pack(fill="x", **pad)
        self.orden = ttk.Combobox(top, values=["Name (A-Z)", "Recent first"], state="readonly", width=12)
        self.orden.current(0)
        self.orden.pack(side="left")
        self.orden.bind("<<ComboboxSelected>>", lambda e: self.refrescar_lista())
        ttk.Button(top, text="Refresh", command=self.refrescar_lista).pack(side="left", padx=(6, 0))
        lf = ttk.Frame(fr_files)
        lf.pack(fill="both", expand=True, padx=6, pady=(0, 4))
        sb = ttk.Scrollbar(lf)
        sb.pack(side="right", fill="y")
        self.lista = tk.Listbox(lf, width=26, height=14, exportselection=False, yscrollcommand=sb.set)
        self.lista.pack(side="left", fill="both", expand=True)
        sb.config(command=self.lista.yview)
        self.lista.bind("<Double-Button-1>", lambda e: self.cargar_seleccion())
        ttk.Button(fr_files, text="Añadir carpeta…", command=self.anadir_carpeta_midi).pack(fill="x", padx=6, pady=(0, 6))
        if HAY_DND:
            for w in (self.lista, fr_files, r):
                w.drop_target_register(DND_FILES)
                w.dnd_bind("<<Drop>>", self._on_drop)

        # --- Playback ---
        fr_pb = ttk.LabelFrame(main, text="Playback")
        fr_pb.grid(row=0, column=1, sticky="ew")
        for c in range(6):
            fr_pb.columnconfigure(c, weight=1)
        ttk.Button(fr_pb, text="Load", command=self.cargar_seleccion).grid(row=0, column=0, sticky="ew", **pad)
        ttk.Button(fr_pb, text="Play/Pause", command=self.player.play_pause).grid(row=0, column=1, sticky="ew", **pad)
        ttk.Button(fr_pb, text="Restart", command=self.player.restart).grid(row=0, column=2, sticky="ew", **pad)
        self.btn_conectar = ttk.Button(fr_pb, text="MidiConnect", command=self.toggle_conexion)
        self.btn_conectar.grid(row=0, column=3, sticky="ew", **pad)
        self.v_m2k = tk.BooleanVar(value=False)
        ttk.Checkbutton(fr_pb, text="Midi2Key", style="Toolbutton", variable=self.v_m2k,
                        command=self.aplicar_m2k).grid(row=0, column=4, sticky="ew", **pad)
        self.cb_disp = ttk.Combobox(fr_pb, state="readonly", values=["No Devices"], width=22)
        self.cb_disp.current(0)
        self.cb_disp.grid(row=0, column=5, sticky="ew", **pad)

        ttk.Button(fr_pb, text="Skip +10", command=lambda: self.player.seek(10)).grid(row=1, column=0, sticky="ew", **pad)
        ttk.Button(fr_pb, text="Rew −10", command=lambda: self.player.seek(-10)).grid(row=1, column=1, sticky="ew", **pad)
        ttk.Button(fr_pb, text="Speed ++", command=lambda: self.cambiar_vel(0.05)).grid(row=1, column=2, sticky="ew", **pad)
        ttk.Button(fr_pb, text="Speed −−", command=lambda: self.cambiar_vel(-0.05)).grid(row=1, column=3, sticky="ew", **pad)
        self.lbl_tiempo = ttk.Label(fr_pb, text="0:00 / 0:00", font=("Menlo", 14, "bold"))
        self.lbl_tiempo.grid(row=1, column=4, **pad)
        self.cb_canal = ttk.Combobox(fr_pb, state="readonly", width=22,
                                     values=["All Channels"] + [f"Channel {i}" for i in range(1, 17)])
        self.cb_canal.current(0)
        self.cb_canal.grid(row=1, column=5, sticky="ew", **pad)
        self.cb_canal.bind("<<ComboboxSelected>>", self.aplicar_canal)

        self.barra = ttk.Progressbar(fr_pb, maximum=1000)
        self.barra.grid(row=2, column=0, columnspan=4, sticky="ew", **pad)
        self.barra.bind("<Button-1>", self._click_barra)
        self.lbl_vel = ttk.Label(fr_pb, text="x1.00", font=("Menlo", 12))
        self.lbl_vel.grid(row=2, column=4, **pad)
        self.lbl_estado = ttk.Label(fr_pb, text="■ Detenido")
        self.lbl_estado.grid(row=2, column=5, **pad)

        # --- Advanced ---
        fr_adv = ttk.LabelFrame(main, text="Advanced")
        fr_adv.grid(row=1, column=1, sticky="ew", pady=5)
        self.v = {k: tk.BooleanVar() for k in ('k88', 'autovol', 'velocity', 'pedal', 'auto', 'fold')}
        fila = ttk.Frame(fr_adv)
        fila.pack(fill="x", **pad)
        for clave, texto in (('k88', '88-Key'), ('autovol', 'AutoVol'), ('velocity', 'Velocity'),
                             ('pedal', 'Sustain'), ('auto', 'Transpose'), ('fold', 'OutRange')):
            ttk.Checkbutton(fila, text=texto, style="Toolbutton", variable=self.v[clave],
                            command=self.aplicar_cfg).pack(side="left", padx=3, expand=True, fill="x")
        fila2 = ttk.Frame(fr_adv)
        fila2.pack(fill="x", **pad)
        ttk.Label(fila2, text="Sustain Cutoff:").pack(side="left")
        self.esc_cut = ttk.Scale(fila2, from_=0, to=127, length=150, command=self._cambia_cutoff)
        self.esc_cut.pack(side="left", padx=6)
        self.lbl_cut = ttk.Label(fila2, text="64", width=4, relief="sunken", anchor="center")
        self.lbl_cut.pack(side="left")
        ttk.Label(fila2, text="   VelCurve:").pack(side="left")
        self.cb_curva = ttk.Combobox(fila2, state="readonly", width=16, values=self.curvas.nombres())
        self.cb_curva.pack(side="left", padx=6)
        self.cb_curva.bind("<<ComboboxSelected>>", self.aplicar_curva)
        fila3 = ttk.Frame(fr_adv)
        fila3.pack(fill="x", **pad)
        ttk.Label(fila3, text="Transpose manual:").pack(side="left")
        ttk.Button(fila3, text="−", width=3, command=lambda: self.cambiar_transp(-1)).pack(side="left", padx=(6, 2))
        self.lbl_transp = ttk.Label(fila3, text="+0", width=10, anchor="center", font=("Menlo", 13, "bold"))
        self.lbl_transp.pack(side="left")
        ttk.Button(fila3, text="+", width=3, command=lambda: self.cambiar_transp(1)).pack(side="left", padx=(2, 6))
        ttk.Button(fila3, text="0", width=3, command=lambda: self.cambiar_transp(0, reset=True)).pack(side="left")
        ttk.Label(fila3, text="  semitonos (con «Transpose» activo se elige solo)").pack(side="left")

        # --- Config ---
        fr_cfg = ttk.LabelFrame(main, text="Config")
        fr_cfg.grid(row=2, column=1, sticky="ew")
        for c in range(4):
            fr_cfg.columnconfigure(c, weight=1)
        self.vc = {k: tk.BooleanVar() for k in ('top', 'legit', 'drums', 'guard', 'loop')}
        ttk.Checkbutton(fr_cfg, text="Always On Top", variable=self.vc['top'], command=self.aplicar_ventana).grid(row=0, column=0, sticky="w", **pad)
        ttk.Checkbutton(fr_cfg, text="Legit Mode", variable=self.vc['legit'], command=self.aplicar_cfg).grid(row=0, column=1, sticky="w", **pad)
        ttk.Checkbutton(fr_cfg, text="Filter Drums", variable=self.vc['drums'], command=self.aplicar_cfg).grid(row=0, column=2, sticky="w", **pad)
        ttk.Checkbutton(fr_cfg, text="Loop", variable=self.vc['loop'], command=self.aplicar_cfg).grid(row=0, column=3, sticky="w", **pad)
        gchk = ttk.Checkbutton(fr_cfg, text="Pausar si pierdo el foco", variable=self.vc['guard'], command=self.aplicar_cfg)
        gchk.grid(row=1, column=0, columnspan=2, sticky="w", **pad)
        if not FOCO_DISPONIBLE:
            gchk.state(["disabled"])
        f_app = ttk.Frame(fr_cfg)
        f_app.grid(row=1, column=2, columnspan=2, sticky="ew", **pad)
        ttk.Label(f_app, text="Solo en app:").pack(side="left")
        self.v_app = tk.StringVar()
        ent = ttk.Entry(f_app, textvariable=self.v_app, width=16)
        ent.pack(side="left", padx=4)
        ent.bind("<KeyRelease>", lambda e: self.aplicar_cfg())
        ttk.Label(f_app, text="(p. ej. Chrome; vacío = cualquiera)").pack(side="left")
        f_op = ttk.Frame(fr_cfg)
        f_op.grid(row=2, column=0, columnspan=2, sticky="ew", **pad)
        ttk.Label(f_op, text="Opacity:").pack(side="left")
        self.esc_op = ttk.Scale(f_op, from_=0.3, to=1.0, length=150, command=lambda v: self.aplicar_ventana())
        self.esc_op.pack(side="left", padx=6)
        f_nm = ttk.Frame(fr_cfg)
        f_nm.grid(row=2, column=2, columnspan=2, sticky="w", **pad)
        ttk.Label(f_nm, text="Note Mode:").pack(side="left")
        self.cb_nm = ttk.Combobox(f_nm, state="readonly", values=["LIFO", "FIFO"], width=6)
        self.cb_nm.pack(side="left", padx=4)
        self.cb_nm.bind("<<ComboboxSelected>>", self.cambiar_note_mode)
        f_o = ttk.Frame(fr_cfg)
        f_o.grid(row=3, column=0, columnspan=2, sticky="ew", **pad)
        ttk.Label(f_o, text="Salida:").pack(side="left")
        self.cb_salida = ttk.Combobox(f_o, state="readonly", values=list(SALIDAS), width=22)
        self.cb_salida.pack(side="left", padx=4)
        self.cb_salida.bind("<<ComboboxSelected>>", self.cambiar_salida)
        f_l = ttk.Frame(fr_cfg)
        f_l.grid(row=3, column=2, columnspan=2, sticky="ew", **pad)
        ttk.Label(f_l, text="Layout:").pack(side="left")
        self.cb_layout = ttk.Combobox(f_l, state="readonly", width=18)
        self.cb_layout.pack(side="left", padx=4)
        self.cb_layout.bind("<<ComboboxSelected>>", self.cambiar_layout)
        ttk.Button(f_l, text="Settings…", command=self.abrir_ajustes).pack(side="left", padx=4)

        # --- Details ---
        fr_det = ttk.LabelFrame(main, text="Details")
        fr_det.grid(row=3, column=1, sticky="nsew", pady=5)
        self.txt_det = tk.Text(fr_det, height=8, font=("Menlo", 10), state="disabled", wrap="word")
        self.txt_det.pack(fill="both", expand=True, padx=6, pady=6)

        # --- Tracks ---
        fr_tr = ttk.LabelFrame(main, text="Tracks  (M = mute · S = solo)")
        fr_tr.grid(row=4, column=0, columnspan=2, sticky="ew")
        cab = ttk.Frame(fr_tr)
        cab.pack(fill="x", padx=6, pady=(4, 0))
        ttk.Button(cab, text="Solo Piano", command=self.solo_piano).pack(side="left")
        ttk.Button(cab, text="Reset M/S", command=self.reset_pistas).pack(side="left", padx=6)
        cv = tk.Canvas(fr_tr, height=84, highlightthickness=0)
        sbt = ttk.Scrollbar(fr_tr, orient="vertical", command=cv.yview)
        self.tr_inner = ttk.Frame(cv)
        self.tr_inner.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))
        cv.create_window((0, 0), window=self.tr_inner, anchor="nw")
        cv.configure(yscrollcommand=sbt.set)
        cv.pack(side="left", fill="both", expand=True, padx=6, pady=6)
        sbt.pack(side="right", fill="y")

        # --- Log ---
        fr_log = ttk.LabelFrame(main, text="Log")
        fr_log.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(5, 0))
        self.txt_log = ScrolledText(fr_log, height=4, font=("Menlo", 10), state="disabled")
        self.txt_log.pack(side="left", fill="both", expand=True, padx=6, pady=6)
        bt = ttk.Frame(fr_log)
        bt.pack(side="right", padx=6, pady=6, anchor="n")
        for texto, cmd in (("Clear Log", self.limpiar_log), ("Refresh MIDI", self.refrescar_midi),
                           ("Edit V-Curve", self.abrir_editor_curva), ("Ref V-List", self.refrescar_curvas)):
            ttk.Button(bt, text=texto, command=cmd).pack(fill="x", pady=2)

    def _aplicar_ajustes_iniciales(self):
        a = self.aj
        for k in self.v:
            self.v[k].set(bool(a[k]))
        for k in self.vc:
            self.vc[k].set(bool(a[k]))
        self.v_app.set(a['app_filtro'])
        self.v_m2k.set(False)
        self.esc_cut.set(a['cutoff'])
        self.lbl_cut.config(text=str(int(a['cutoff'])))
        self.esc_op.set(a['alpha'])
        self.cb_nm.set(a['modo_notas'])
        nombre_salida = next((k for k, v in SALIDAS.items() if v == a['salida']), list(SALIDAS)[0])
        self.cb_salida.set(nombre_salida)
        self.cb_curva.set(a['curva'] if a['curva'] in self.curvas.nombres() else "Linear Coarse")
        self.refrescar_layouts()
        self.out.sustain_key = int(a['sustain_key'])
        self.player.speed = float(a['speed'])
        self.lbl_vel.config(text=f"x{self.player.speed:.2f}")
        self.lbl_transp.config(text=f"{int(a['transp']):+d}")
        self.cargar_layout_nombre(a['layout'], silencioso=True)
        self.aplicar_cfg(guardar=False)
        self.aplicar_ventana()
        self.cambiar_salida(None, silencioso=True)
        if a['midi_canal']:
            self.cb_canal.current(int(a['midi_canal']))
            self.aplicar_canal()

    # ---------- utilidades ----------
    def log_t(self, msg):
        self.logq.put(msg)

    def log(self, msg):
        hora = datetime.datetime.now().strftime("%H:%M:%S")
        self.txt_log.config(state="normal")
        self.txt_log.insert("end", f"[{hora}] {msg}\n")
        self.txt_log.see("end")
        self.txt_log.config(state="disabled")

    def limpiar_log(self):
        self.txt_log.config(state="normal")
        self.txt_log.delete("1.0", "end")
        self.txt_log.config(state="disabled")

    def _chequear_accesibilidad(self):
        try:
            from ApplicationServices import AXIsProcessTrustedWithOptions, kAXTrustedCheckOptionPrompt
            if not AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True}):
                self.log("⚠ Sin permiso de Accesibilidad: Ajustes del Sistema > Privacidad y seguridad >")
                permiso_app = "MIDI++" if getattr(sys, "frozen", False) else "Terminal/iTerm/VS Code"
                self.log(f"  Accesibilidad (y Monitorización de entrada) -> activa {permiso_app}.")
        except Exception:
            pass

    # ---------- archivos ----------
    def refrescar_lista(self):
        encontrados = set()
        carpetas = [BASE, DIR_MIDI]
        carpetas.extend(self.aj.get('midi_dirs', []))
        for carpeta in carpetas:
            if not isinstance(carpeta, str) or not os.path.isdir(carpeta):
                continue
            try:
                for entrada in os.scandir(carpeta):
                    if entrada.is_file() and entrada.name.lower().endswith((".mid", ".midi")):
                        encontrados.add(os.path.abspath(entrada.path))
            except OSError:
                continue
        if self.orden.get().startswith("Recent"):
            self.archivos = sorted(encontrados, key=os.path.getmtime, reverse=True)
        else:
            self.archivos = sorted(encontrados, key=lambda p: os.path.basename(p).lower())
        self.lista.delete(0, "end")
        for p in self.archivos:
            self.lista.insert("end", os.path.basename(p))
        ult = self.aj.get('last_file')
        if ult in self.archivos:
            i = self.archivos.index(ult)
            self.lista.selection_set(i)
            self.lista.see(i)

    def anadir_carpeta_midi(self):
        carpeta = filedialog.askdirectory(title="Añadir carpeta con archivos MIDI", mustexist=True)
        if not carpeta:
            return
        carpeta = os.path.abspath(carpeta)
        carpetas = self.aj.get('midi_dirs', [])
        if not isinstance(carpetas, list):
            carpetas = []
        normalizadas = {os.path.normcase(os.path.abspath(p)) for p in carpetas if isinstance(p, str)}
        if os.path.normcase(carpeta) not in normalizadas:
            carpetas.append(carpeta)
        self.aj['midi_dirs'] = carpetas
        guardar_ajustes(self.aj)
        self.refrescar_lista()
        cantidad = sum(1 for p in self.archivos if os.path.dirname(p) == carpeta)
        self.log(f"[MIDI] Carpeta añadida: {carpeta} ({cantidad} archivos MIDI)")

    def _on_drop(self, event):
        for p in self.root.tk.splitlist(event.data):
            if p.lower().endswith((".mid", ".midi")):
                self.cargar_ruta(p)
                break

    def cargar_seleccion(self):
        sel = self.lista.curselection()
        if not sel:
            ruta = filedialog.askopenfilename(title="Elige un archivo MIDI", filetypes=[("MIDI", "*.mid *.midi *.MID *.MIDI")])
            if ruta:
                self.cargar_ruta(ruta)
            return
        self.cargar_ruta(self.archivos[sel[0]])

    def cargar_ruta(self, ruta, silencioso=False):
        try:
            c = cargar_cancion(ruta, self.cb_nm.get() or "LIFO")
        except Exception as e:
            if not silencioso:
                messagebox.showerror("Error", f"No pude leer el archivo:\n{e}")
            self.log(f"⚠ No pude leer {os.path.basename(ruta)}: {e}")
            return
        self.player.load(c)
        self.aj['last_file'] = ruta
        self.log(f"[Load] Cargado: {c.nombre}")
        if c.errores:
            self.log(f"[Fix] Se corrigieron {c.errores} anomalías del MIDI (notas huérfanas/sin cerrar)")
        self._pintar_pistas(c)
        self.aplicar_cfg(guardar=False)
        self.refrescar_lista()

    def cambiar_note_mode(self, _=None):
        self.aj['modo_notas'] = self.cb_nm.get()
        if self.player.song:
            self.cargar_ruta(self.player.song.ruta)

    def _pintar_pistas(self, c):
        for w in self.tr_inner.winfo_children():
            w.destroy()
        self.track_vars = []
        for i, p in enumerate(c.pistas):
            vm, vs = tk.BooleanVar(), tk.BooleanVar()
            self.track_vars.append((vm, vs))
            ttk.Checkbutton(self.tr_inner, text="M", width=2, style="Toolbutton", variable=vm,
                            command=self.aplicar_pistas).grid(row=i, column=0, padx=2, pady=1)
            ttk.Checkbutton(self.tr_inner, text="S", width=2, style="Toolbutton", variable=vs,
                            command=self.aplicar_pistas).grid(row=i, column=1, padx=2, pady=1)
            ttk.Label(self.tr_inner, text=f"{p['nombre']} (notes: {p['notas']}) - {p['gm']}").grid(
                row=i, column=2, sticky="w", padx=6)

    def solo_piano(self):
        c = self.player.song
        if not c:
            return
        for i, (vm, vs) in enumerate(self.track_vars):
            vs.set(c.pistas[i]['piano'])
            vm.set(False)
        if not any(vs.get() for _, vs in self.track_vars):
            self.log("[Tracks] No hay pistas de piano; se deja todo activo")
        self.aplicar_pistas()

    def reset_pistas(self):
        for vm, vs in self.track_vars:
            vm.set(False)
            vs.set(False)
        self.aplicar_pistas()

    # ---------- MidiConnect / Midi2Key ----------
    def refrescar_midi(self):
        self.dispositivos = self.entrada.dispositivos()
        vals = self.dispositivos or ["No Devices"]
        self.cb_disp.config(values=vals)
        pref = self.aj.get('midi_in')
        if pref in self.dispositivos:
            self.cb_disp.set(pref)
        elif self.cb_disp.get() not in vals:
            self.cb_disp.current(0)
        self.log(f"[MIDI] Dispositivos: {', '.join(self.dispositivos) if self.dispositivos else 'ninguno'}")

    def toggle_conexion(self):
        if self.entrada.port is not None:
            self.entrada.desconectar()
            self.btn_conectar.config(text="MidiConnect")
            return
        nombre = self.cb_disp.get()
        if nombre not in self.dispositivos:
            self.log("⚠ Elige un dispositivo MIDI (o pulsa Refresh MIDI)")
            return
        if self.entrada.conectar(nombre):
            self.aj['midi_in'] = nombre
            self.btn_conectar.config(text="Disconnect")
            if not self.v_m2k.get():
                self.v_m2k.set(True)
                self.aplicar_m2k()

    def aplicar_m2k(self):
        self.entrada.midi2key = self.v_m2k.get()
        if not self.entrada.midi2key:
            self.entrada.soltar_todo()
        self.log(f"[Midi2Key] {'ACTIVADO' if self.entrada.midi2key else 'desactivado'}")

    def aplicar_canal(self, _=None):
        i = self.cb_canal.current()
        self.entrada.canal = None if i <= 0 else i - 1
        self.aj['midi_canal'] = i

    # ---------- controles ----------
    def aplicar_cfg(self, guardar=True):
        v, vc = self.v, self.vc
        self.player.update_cfg(
            k88=v['k88'].get(), autovol=v['autovol'].get(), velocity=v['velocity'].get(),
            pedal=v['pedal'].get(), auto=v['auto'].get(), fold=v['fold'].get(),
            legit=vc['legit'].get(), drums=vc['drums'].get(), guard=vc['guard'].get(),
            loop=vc['loop'].get(), jitter=self.aj['jitter'], spread=self.aj['spread'],
            vel_mod=self.aj['vel_mod'], vel_thr=self.aj['vel_thr'],
            cutoff=int(self.esc_cut.get()), transp=int(self.aj['transp']),
            curva=self.curvas.get(self.cb_curva.get() or "Linear Coarse"))
        for k in self.v:
            self.aj[k] = self.v[k].get()
        for k in self.vc:
            self.aj[k] = self.vc[k].get()
        self.aj['app_filtro'] = self.v_app.get().strip()
        self.aj['curva'] = self.cb_curva.get()
        self.refrescar_detalles()

    def _cambia_cutoff(self, valor):
        n = int(float(valor))
        self.lbl_cut.config(text=str(n))
        self.aj['cutoff'] = n
        self.player.update_cfg(cutoff=n)

    def aplicar_curva(self, _=None):
        self.aplicar_cfg()
        self.log(f"[VelCurve] {self.cb_curva.get()}")

    def refrescar_curvas(self):
        self.curvas.refrescar()
        actual = self.cb_curva.get()
        self.cb_curva.config(values=self.curvas.nombres())
        if actual not in self.curvas.nombres():
            self.cb_curva.set("Linear Coarse")
        self.log(f"[V-List] {len(self.curvas.nombres())} curvas disponibles")

    def aplicar_pistas(self):
        mute = {i for i, (m, s) in enumerate(self.track_vars) if m.get()}
        solo = {i for i, (m, s) in enumerate(self.track_vars) if s.get()}
        self.player.update_cfg(mute=mute, solo=solo)
        self.refrescar_detalles()

    def aplicar_ventana(self):
        self.aj['top'] = self.vc['top'].get()
        self.aj['alpha'] = round(float(self.esc_op.get()), 2)
        self.root.attributes("-topmost", self.aj['top'])
        self.root.attributes("-alpha", self.aj['alpha'])

    def cambiar_transp(self, d, reset=False):
        t = 0 if reset else max(-36, min(36, int(self.aj['transp']) + d))
        self.aj['transp'] = t
        self.player.update_cfg(transp=t)
        self.refrescar_detalles()

    def cambiar_vel(self, d):
        self.player.set_speed(round(self.player.speed + d, 2))
        self.aj['speed'] = self.player.speed
        self.lbl_vel.config(text=f"x{self.player.speed:.2f}")

    def cambiar_salida(self, _=None, silencioso=False):
        modo = SALIDAS.get(self.cb_salida.get(), 'keys')
        self.aj['salida'] = modo
        self.out.set_modo(modo)
        if self.out.modo != modo:
            self.cb_salida.set(next(k for k, v in SALIDAS.items() if v == self.out.modo))
            self.aj['salida'] = self.out.modo

    def _click_barra(self, e):
        c = self.player.song
        if c and c.duracion:
            self.player.seek_abs(c.duracion * e.x / max(1, self.barra.winfo_width()))

    # ---------- layouts ----------
    def refrescar_layouts(self):
        vals = list(LAYOUTS_INTERNOS) + sorted(
            "📄 " + os.path.splitext(os.path.basename(p))[0] for p in glob.glob(os.path.join(DIR_LAYOUTS, "*.json")))
        self.cb_layout.config(values=vals)
        self.cb_layout.set(self.aj['layout'] if self.aj['layout'] in vals else vals[0])

    def cargar_layout_nombre(self, nombre, silencioso=False):
        try:
            if nombre in LAYOUTS_INTERNOS:
                km = LAYOUTS_INTERNOS[nombre]()
            else:
                base = nombre.replace("📄 ", "")
                km = layout_desde_json(os.path.join(DIR_LAYOUTS, base + ".json"))
        except Exception as e:
            self.log(f"⚠ Layout '{nombre}' inválido: {e}")
            km, nombre = layout_vp88(), "Virtual Piano 88"
        self.aj['layout'] = nombre
        self.cb_layout.set(nombre)
        self.player.update_cfg(keymap=km)
        if not silencioso:
            self.log(f"[Layout] {nombre} ({len(km)} teclas)")
            self.refrescar_detalles()

    def cambiar_layout(self, _=None):
        self.cargar_layout_nombre(self.cb_layout.get())

    def exportar_layout(self):
        ruta = os.path.join(DIR_LAYOUTS, "mi_layout.json")
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(layout_a_json(self.player.cfg['keymap']), f, indent=1)
        self.refrescar_layouts()
        self.log(f"[Layout] Exportado a {ruta} — edítalo y elígelo en «Layout»")

    # ---------- detalles ----------
    def refrescar_detalles(self):
        c = self.player.song
        self.txt_det.config(state="normal")
        self.txt_det.delete("1.0", "end")
        t_manual = int(self.aj['transp'])
        if c:
            total, fuera, t = self.player.stats()
            cfg = self.player.cfg
            lo, hi = rango_teclas(cfg)
            if cfg['solo']:
                activas = len(cfg['solo'])
            else:
                activas = len(c.pistas) - len(cfg['mute'])
            fmtn = {0: "0 (single)", 1: "1 (multi)", 2: "2 (async)"}.get(c.formato, str(c.formato))
            acc = "plegadas" if cfg['fold'] else "descartadas"
            self.txt_det.insert("end",
                f"File:      {c.nombre}\n"
                f"Format:    {fmtn}\n"
                f"Tracks:    {activas}/{len(c.pistas)} ({len(c.notas)} notes)\n"
                f"Tempo:     {c.bpm0:.1f} BPM ({c.n_tempos} changes)\n"
                f"Time Sig:  {c.compas}\n"
                f"Note Mode: {c.modo_notas}\n"
                f"Range:     MIDI {lo}–{hi} ({hi - lo + 1} teclas) · fuera de rango: {fuera} ({acc})\n"
                f"Transpose: {t:+d} {'(auto)' if cfg['auto'] else '(manual)'} · a tocar: {total} notas")
            self.lbl_transp.config(text=f"{t:+d}" + (" auto" if cfg['auto'] else ""))
        else:
            self.lbl_transp.config(text=f"{t_manual:+d}")
        self.txt_det.config(state="disabled")

    # ---------- editor de curva de velocity ----------
    def abrir_editor_curva(self):
        if self.editor_curva is not None and self.editor_curva.winfo_exists():
            self.editor_curva.lift()
            return
        win = tk.Toplevel(self.root)
        win.title("Velocity Curve Editor (32 pasos)")
        self.editor_curva = win
        W, H = 640, 300
        pasos = self.curvas.get(self.cb_curva.get() or "Linear Coarse")
        cv = tk.Canvas(win, width=W, height=H, bg="#1e1e1e", highlightthickness=0)
        cv.pack(padx=10, pady=10)
        bw = W / PASOS

        def dibujar():
            cv.delete("all")
            for i, nivel in enumerate(pasos):
                y = H - (nivel + 1) / 32.0 * H
                cv.create_rectangle(i * bw + 2, y, (i + 1) * bw - 2, H, fill="#4aa3ff", outline="")
            cv.create_text(6, 6, anchor="nw", fill="#aaa", text="entrada (velocity MIDI) →   alto = más fuerte")

        def pintar(e):
            i = max(0, min(PASOS - 1, int(e.x / bw)))
            nivel = max(0, min(31, int(round((1 - e.y / H) * 32)) - 1 if e.y < H else 0))
            pasos[i] = nivel
            dibujar()

        cv.bind("<Button-1>", pintar)
        cv.bind("<B1-Motion>", pintar)
        dibujar()
        fila = ttk.Frame(win)
        fila.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Label(fila, text="Nombre:").pack(side="left")
        nombre = tk.StringVar(value="Mi curva")
        ttk.Entry(fila, textvariable=nombre, width=18).pack(side="left", padx=6)

        def aplicar_y_guardar():
            n = nombre.get().strip() or "Mi curva"
            self.curvas.guardar(n, pasos)
            self.cb_curva.config(values=self.curvas.nombres())
            self.cb_curva.set(n)
            self.aplicar_cfg()
            self.log(f"[V-Curve] Guardada y aplicada: {n}")

        def reset():
            pasos[:] = _curva(CURVAS_BASE["Linear Coarse"])
            dibujar()
        ttk.Button(fila, text="Guardar y aplicar", command=aplicar_y_guardar).pack(side="left", padx=4)
        ttk.Button(fila, text="Reset (lineal)", command=reset).pack(side="left", padx=4)
        ttk.Button(fila, text="Cerrar", command=win.destroy).pack(side="right")

    # ---------- ajustes ----------
    def abrir_ajustes(self):
        win = tk.Toplevel(self.root)
        win.title("Settings")
        win.transient(self.root)
        nb = ttk.Notebook(win)
        nb.pack(fill="both", expand=True, padx=8, pady=8)

        # Hotkeys
        f1 = ttk.Frame(nb, padding=10)
        nb.add(f1, text="Hotkeys")
        etiquetas = {}

        def refrescar_etq():
            for n, _, _ in ACCIONES:
                etiquetas[n].config(text=texto_atajo(self.aj['hotkeys'].get(n)))
            etq_sus.config(text=CODIGO_A_NOMBRE.get(self.out.sustain_key, f"#{self.out.sustain_key}").upper())

        def asignar(nombre):
            def cb(mods, code):
                self.aj['hotkeys'][nombre] = {"mods": mods, "code": code}
                refrescar_etq()
            capturar_combinacion(win, "Nuevo atajo", self.atajos, cb)

        def quitar(nombre):
            self.aj['hotkeys'][nombre] = None
            refrescar_etq()

        def restaurar():
            self.aj['hotkeys'] = {n: dict(b) for n, _, b in ACCIONES}
            refrescar_etq()

        for r, (n, desc, _) in enumerate(ACCIONES):
            ttk.Label(f1, text=desc, width=20).grid(row=r, column=0, sticky="w", pady=2)
            etiquetas[n] = ttk.Label(f1, text="", width=14, relief="sunken", anchor="center")
            etiquetas[n].grid(row=r, column=1, padx=6)
            ttk.Button(f1, text="Cambiar", command=lambda n=n: asignar(n)).grid(row=r, column=2)
            ttk.Button(f1, text="Quitar", command=lambda n=n: quitar(n)).grid(row=r, column=3, padx=4)
        r = len(ACCIONES)
        ttk.Label(f1, text="Tecla de Sustain", width=20).grid(row=r, column=0, sticky="w", pady=(10, 2))
        etq_sus = ttk.Label(f1, text="", width=14, relief="sunken", anchor="center")
        etq_sus.grid(row=r, column=1, padx=6, pady=(10, 2))

        def cambiar_sustain():
            def cb(mods, code):
                self.out.sustain_key = code
                self.aj['sustain_key'] = code
                refrescar_etq()
            capturar_combinacion(win, "Tecla de Sustain", self.atajos, cb)
        ttk.Button(f1, text="Cambiar", command=cambiar_sustain).grid(row=r, column=2, pady=(10, 2))
        ttk.Button(f1, text="Restaurar atajos", command=restaurar).grid(row=r + 1, column=0, columnspan=2, pady=10, sticky="w")
        refrescar_etq()

        # Legit
        f2 = ttk.Frame(nb, padding=10)
        nb.add(f2, text="Legit Mode")
        ttk.Label(f2, text="Humaniza la interpretación (se aplica con «Legit Mode» activo):",
                  wraplength=380).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        vj, vs = tk.IntVar(value=self.aj['jitter']), tk.IntVar(value=self.aj['spread'])
        ttk.Label(f2, text="Variación de tiempo (± ms)").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Spinbox(f2, from_=0, to=80, textvariable=vj, width=6).grid(row=1, column=1)
        ttk.Label(f2, text="Dispersión de acordes (ms)").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Spinbox(f2, from_=0, to=60, textvariable=vs, width=6).grid(row=2, column=1)

        # Velocity
        f3 = ttk.Frame(nb, padding=10)
        nb.add(f3, text="Velocity")
        ttk.Label(f3, text="La velocity se reduce a 32 pasos y pasa por la curva elegida (VelCurve).\n"
                           "Virtual Piano web NO distingue fuerza: déjala desactivada ahí.\n"
                           "Para juegos con velocity, las notas suaves se envían con ⌥ (Alt).",
                  wraplength=400, justify="left").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        vmod = tk.StringVar(value=self.aj['vel_mod'])
        ttk.Radiobutton(f3, text="Notas suaves con ⌥+tecla", variable=vmod, value='alt').grid(row=1, column=0, sticky="w")
        ttk.Radiobutton(f3, text="Sin modificador (solo puerto MIDI)", variable=vmod, value='none').grid(row=2, column=0, sticky="w")
        vthr = tk.IntVar(value=self.aj['vel_thr'])
        ttk.Label(f3, text="Umbral suave (0–31)").grid(row=3, column=0, sticky="w", pady=6)
        ttk.Spinbox(f3, from_=0, to=31, textvariable=vthr, width=6).grid(row=3, column=1)

        # Layout
        f4 = ttk.Frame(nb, padding=10)
        nb.add(f4, text="Layout")
        ttk.Label(f4, text="Exporta el mapa actual (nota MIDI → tecla + modificadores) a layouts/mi_layout.json,\n"
                           "edítalo y elígelo en «Layout» para adaptar cualquier piano virtual.",
                  wraplength=400, justify="left").pack(anchor="w", pady=(0, 8))
        ttk.Button(f4, text="Exportar layout actual", command=self.exportar_layout).pack(anchor="w")

        def cerrar():
            try:
                self.aj['jitter'], self.aj['spread'] = int(vj.get()), int(vs.get())
                self.aj['vel_thr'] = int(vthr.get())
            except (tk.TclError, ValueError):
                pass
            self.aj['vel_mod'] = vmod.get()
            self.aplicar_cfg()
            win.destroy()
        ttk.Button(win, text="Aplicar y cerrar", command=cerrar).pack(pady=(0, 10))
        win.protocol("WM_DELETE_WINDOW", cerrar)

    # ---------- bucle de UI ----------
    def _disparar(self, nombre):
        if nombre == 'stop':
            self.player.stop()
        else:
            self.accionq.put(nombre)

    def accion(self, nombre):
        p = self.player
        if nombre == 'play_pause':
            p.play_pause()
        elif nombre == 'restart':
            p.restart()
        elif nombre == 'skip':
            p.seek(10)
        elif nombre == 'rew':
            p.seek(-10)
        elif nombre == 'speed_up':
            self.cambiar_vel(0.05)
        elif nombre == 'speed_down':
            self.cambiar_vel(-0.05)
        elif nombre == 'transp_up':
            self.cambiar_transp(1)
        elif nombre == 'transp_down':
            self.cambiar_transp(-1)
        elif nombre == 'legit':
            self.vc['legit'].set(not self.vc['legit'].get())
            self.aplicar_cfg()
            self.log(f"[Legit] {'ON' if self.vc['legit'].get() else 'OFF'}")
        elif nombre == 'midi2key':
            self.v_m2k.set(not self.v_m2k.get())
            self.aplicar_m2k()

    def tick(self):
        while True:
            try:
                self.log(self.logq.get_nowait())
            except queue.Empty:
                break
        while True:
            try:
                self.accion(self.accionq.get_nowait())
            except queue.Empty:
                break

        p = self.player
        bloqueado = False
        if FOCO_DISPONIBLE:
            pid, nombre = app_frontal()
            filtro = self.aj['app_filtro'].lower()
            propia = (pid == os.getpid())
            bloqueado = propia or (bool(filtro) and filtro not in nombre.lower())
        p.blocked = bloqueado
        self.out.bloqueado = bloqueado and self.aj['guard']

        dur = p.song.duracion if p.song else 0.0
        pos = p.get_pos()
        self.lbl_tiempo.config(text=f"{fmt(pos)} / {fmt(dur)}")
        self.barra["value"] = (pos / dur * 1000) if dur else 0
        if p.state == 'playing':
            esperando = (p.blocked and p.cfg['guard']) or time.perf_counter() < p.countdown_until
            self.lbl_estado.config(text="⏳ Esperando foco" if esperando else "▶ Tocando")
        elif p.state == 'paused':
            self.lbl_estado.config(text="⏸ Pausado")
        else:
            self.lbl_estado.config(text="■ Detenido")
        self.root.after(50, self.tick)

    def cerrar(self):
        self.aj['speed'] = self.player.speed
        guardar_ajustes(self.aj)
        self.atajos._quit = True
        self.entrada.desconectar()
        self.player.quit()
        self.out.soltar_todo()
        self.root.destroy()


def main():
    # Usar siempre Tk estándar: tkinterdnd2 carga una extensión nativa
    # incompatible con ciertas versiones Tcl/Tk y puede causar segfault.
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
