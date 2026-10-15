#!/usr/bin/env python3
"""
GPIO-Button Steuerung für Raspberry Pi (Raspberry Pi OS)
Konfiguration für 4 Buttons, ohne LED-Ausgänge.
Zuordnungen aktuell:
- GPIO 17 = Bildschirm skalieren (-5%)
- GPIO 27 = Bildschirm skalieren (+5%)
- GPIO 22 = Bildschirmtastatur ein-/ausschalten (onboard)
- GPIO 23 = Touchscreen ein-/ausschalten (xinput)

GPIO 24 und GPIO 25 werden nicht benutzt.

Hinweis: Script in der Benutzer-X-Session ausführen (DISPLAY gesetzt), oder DISPLAY=":0" in der Umgebung setzen.

Benötigt: python3-gpiozero, xrandr, xinput, onboard (optional)
"""

import os
import subprocess
import logging
import time
import signal
import shutil
import sys
try:
    from gpiozero import Button
except Exception:
    Button = None
from threading import Lock

# --- Konfiguration GPIO ---
PIN_SCALE_DOWN = 17
PIN_SCALE_UP = 27
PIN_TOGGLE_KBD = 22
# GPIO 23 wird jetzt verwendet, um den Touchscreen ein-/auszuschalten
PIN_TOUCH_TOGGLE = 23
# GPIO 24 und 25 werden nicht mehr benutzt

# Skalierungsparameter
SCALE_STEP = 0.05
SCALE_MIN = 0.5
SCALE_MAX = 2.0

# Debounce (sekunden)
BOUNCE_TIME = 0.08

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')
log = logging.getLogger('gpio-buttons')


def ensure_dependencies():
    """Überprüft und installiert fehlende Systempakete und Python-Module (apt-get).
    Führt 'sudo apt-get update' und 'sudo apt-get install -y' aus, falls Pakete fehlen.
    """
    pkgs = []
    # python Modul
    if Button is None:
        pkgs.append('python3-gpiozero')

    # Befehle und zugehörige apt-Pakete
    cmd_pkg = {
        'xrandr': 'x11-xserver-utils',
        'xinput': 'xinput',
        'amixer': 'alsa-utils',
        'onboard': 'onboard'
    }
    for cmd, pkg in cmd_pkg.items():
        if shutil.which(cmd) is None:
            pkgs.append(pkg)

    # eindeutige Paketliste
    pkgs = list(dict.fromkeys(pkgs))
    if not pkgs:
        # keine Installation nötig, versuche ggf. Import erneut
        if Button is None:
            try:
                from gpiozero import Button as _B
                globals()['Button'] = _B
            except Exception:
                log.error('gpiozero nicht installiert und konnte nicht importiert werden')
                sys.exit(1)
        return

    log.info('Fehlende Pakete detected, versuche Installation: %s', ', '.join(pkgs))
    try:
        subprocess.run(['sudo', 'apt-get', 'update'], check=False)
        subprocess.run(['sudo', 'apt-get', 'install', '-y'] + pkgs, check=False)
    except Exception as e:
        log.warning('Fehler bei Paketinstallation: %s', e)

    # versuche Import nach Installation
    if Button is None:
        try:
            from gpiozero import Button as _B
            globals()['Button'] = _B
        except Exception as e:
            log.error('gpiozero konnte nach Installation nicht importiert werden: %s', e)
            sys.exit(1)

state_lock = Lock()
current_scale = 1.0


def run_cmd(cmd, check=False, capture_output=False, env=None):
    try:
        return subprocess.run(cmd, shell=True, check=check, stdout=subprocess.PIPE if capture_output else None, stderr=subprocess.PIPE if capture_output else None, env=env)
    except Exception as e:
        log.error('Fehler beim Ausführen von "%s": %s', cmd, e)
        return None


def detect_primary_output():
    # Liefert den Namen des ersten verbundenen Displays (z.B. HDMI-1, DSI-1, eDP-1)
    try:
        res = subprocess.run(['xrandr', '--query'], check=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        for line in res.stdout.splitlines():
            if ' connected primary' in line:
                return line.split()[0]
        for line in res.stdout.splitlines():
            if ' connected ' in line:
                return line.split()[0]
    except Exception as e:
        log.warning('xrandr nicht verfügbar oder Fehler: %s', e)
    return None


def apply_scale(scale):
    output = detect_primary_output()
    if not output:
        log.warning('Kein Display gefunden; Skaliereinstellung übersprungen')
        return False
    # xrandr --output OUT --scale SxS
    cmd = f"xrandr --output {output} --scale {scale}x{scale}"
    log.info('Setze Skalierung auf %.2f%% mit: %s', scale * 100, cmd)
    res = run_cmd(cmd)
    return res is not None


def change_scale(delta):
    global current_scale
    with state_lock:
        new_scale = round(max(SCALE_MIN, min(SCALE_MAX, current_scale + delta)), 2)
        if new_scale == current_scale:
            log.info('Skalierung bleibt bei %.2f', current_scale)
            return
        current_scale = new_scale
        success = apply_scale(current_scale)
        if not success:
            log.warning('Skalierung konnte nicht angewendet werden')


def is_onboard_running():
    res = subprocess.run(['pgrep', '-x', 'onboard'], stdout=subprocess.DEVNULL)
    return res.returncode == 0


def toggle_onboard():
    display = os.environ.get('DISPLAY', ':0')
    env = os.environ.copy()
    env.setdefault('DISPLAY', display)
    if is_onboard_running():
        log.info('Beende onboard (Bildschirmtastatur)')
        run_cmd('killall onboard', env=env)
    else:
        log.info('Starte onboard (Bildschirmtastatur)')
        # Starte im Hintergrund
        try:
            subprocess.Popen(['onboard'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            log.error('Konnte onboard nicht starten: %s', e)
    time.sleep(0.2)


def find_touch_ids():
    """Finde xinput-Geräte, deren Name 'touch' (case-insensitive) enthält und gib deren IDs zurück."""
    try:
        res = subprocess.run(['xinput', '--list'], check=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        ids = []
        for line in res.stdout.splitlines():
            if 'touch' in line.lower():
                parts = line.split('id=')
                if len(parts) >= 2:
                    try:
                        idpart = parts[1].split()[0]
                        ids.append(idpart)
                    except Exception:
                        continue
        return ids
    except Exception as e:
        log.warning('xinput nicht verfügbar oder Fehler beim Auflisten: %s', e)
        return []


def toggle_touchscreen():
    ids = find_touch_ids()
    if not ids:
        log.warning('Kein Touchscreen-Gerät gefunden (xinput)')
        return
    for id in ids:
        try:
            res = subprocess.run(['xinput', 'list-props', id], check=True, stdout=subprocess.PIPE, text=True)
            enabled = None
            for l in res.stdout.splitlines():
                if 'Device Enabled' in l:
                    # Versuche, den letzten Token als Enabled-Flag zu interpretieren (robuster gegen Formatvarianten).
                    try:
                        last = l.strip().split()[-1]
                        enabled = (last == '1' or last.endswith('1'))
                    except Exception:
                        # Fallback auf vorherige Heuristik
                        if '\t1' in l or l.strip().endswith('1'):
                            enabled = True
                        else:
                            enabled = False
                    break
            if enabled is None:
                log.debug('Konnte Enabled-Status für id %s nicht ermitteln', id)
                continue
            if enabled:
                log.info('Deaktiviere Touchscreen id=%s', id)
                run_cmd(f'xinput --disable {id}')
            else:
                log.info('Aktiviere Touchscreen id=%s', id)
                run_cmd(f'xinput --enable {id}')
        except Exception as e:
            log.warning('Fehler beim Umschalten des Touchscreens id=%s: %s', id, e)


def on_scale_down():
    log.debug('Scale down pressed')
    change_scale(-SCALE_STEP)


def on_scale_up():
    log.debug('Scale up pressed')
    change_scale(SCALE_STEP)


def on_toggle_kbd():
    log.debug('Toggle keyboard pressed')
    toggle_onboard()


def on_touch_toggle():
    log.debug('Touchscreen toggle pressed')
    toggle_touchscreen()


def cleanup(signum=None, frame=None):
    log.info('Beende')
    raise SystemExit


def main():
    global current_scale
    log.info('Starte GPIO-Button Dienst')

    # Setze initialen Scale Wert (falls vorhanden)
    # Versuche aktuellen Scale aus xrandr zu lesen (vereinfachte Annahme)
    current_scale = 1.0

    # Stelle sicher, dass Abhängigkeiten vorhanden sind (installiert falls nötig)
    ensure_dependencies()

    # Buttons erstellen (erst nach sicherer gpiozero-Import)
    btn_scale_down = Button(PIN_SCALE_DOWN, pull_up=True, bounce_time=BOUNCE_TIME)
    btn_scale_up = Button(PIN_SCALE_UP, pull_up=True, bounce_time=BOUNCE_TIME)
    btn_toggle_kbd = Button(PIN_TOGGLE_KBD, pull_up=True, bounce_time=BOUNCE_TIME)
    # Touchscreen-Button
    btn_touch_toggle = Button(PIN_TOUCH_TOGGLE, pull_up=True, bounce_time=BOUNCE_TIME)

    # Event-Handler
    btn_scale_down.when_pressed = on_scale_down
    btn_scale_up.when_pressed = on_scale_up
    btn_toggle_kbd.when_pressed = on_toggle_kbd
    btn_touch_toggle.when_pressed = on_touch_toggle

    # Signale abfangen
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    # Laufende Schleife
    try:
        while True:
            time.sleep(1)
    except SystemExit:
        pass
    except Exception as e:
        log.exception('Unerwarteter Fehler: %s', e)
    finally:
        cleanup()


if __name__ == '__main__':
    main()
