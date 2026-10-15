#!/usr/bin/env python3
"""
GPIO-Button Steuerung für Raspberry Pi (Raspberry Pi OS)
Zuordnungen:
- GPIO 17 = Bildschirm skalieren (-5%)
- GPIO 27 = Bildschirm skalieren (+5%)
- GPIO 22 = Bildschirmtastatur ein-/ausschalten (onboard)
- GPIO 23 = Lautstärke (-5%)
- GPIO 24 = Lautstärke (+5%)
- GPIO 25 = Mute toggle
LEDs:
- GPIO 5: leuchtet, wenn Bildschirmtastatur deaktiviert ist
- GPIO 6: leuchtet, wenn Lautstärke gemuted ist

Hinweis: Script im Benutzer-X-Session ausführen (DISPLAY gesetzt), oder DISPLAY=":0" in der Umgebung setzen.

Benötigt: python3-gpiozero, xrandr, amixer, onboard (optional)
"""

import os
import subprocess
import logging
import time
import signal
from gpiozero import Button, LED
from threading import Lock

# --- Konfiguration GPIO ---
PIN_SCALE_DOWN = 17
PIN_SCALE_UP = 27
PIN_TOGGLE_KBD = 22
PIN_VOL_DOWN = 23
PIN_VOL_UP = 24
PIN_MUTE = 25
PIN_LED_KBD_OFF = 5   # leuchtet, wenn Tastatur deaktiviert
PIN_LED_MUTED = 6     # leuchtet, wenn gemuted

# Skalierungsparameter
SCALE_STEP = 0.05
SCALE_MIN = 0.5
SCALE_MAX = 2.0

# Debounce (sekunden)
BOUNCE_TIME = 0.08

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')
log = logging.getLogger('gpio-buttons')

state_lock = Lock()
current_scale = 1.0

# Buttons und LEDs
btn_scale_down = Button(PIN_SCALE_DOWN, pull_up=True, bounce_time=BOUNCE_TIME)
btn_scale_up = Button(PIN_SCALE_UP, pull_up=True, bounce_time=BOUNCE_TIME)
btn_toggle_kbd = Button(PIN_TOGGLE_KBD, pull_up=True, bounce_time=BOUNCE_TIME)
btn_vol_down = Button(PIN_VOL_DOWN, pull_up=True, bounce_time=BOUNCE_TIME)
btn_vol_up = Button(PIN_VOL_UP, pull_up=True, bounce_time=BOUNCE_TIME)
btn_mute = Button(PIN_MUTE, pull_up=True, bounce_time=BOUNCE_TIME)

led_kbd_off = LED(PIN_LED_KBD_OFF)
led_muted = LED(PIN_LED_MUTED)


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
    update_leds()


def vol_change(delta_percent):
    # delta_percent positive or negative like 5 or -5
    sign = '+' if delta_percent > 0 else '-'
    amt = abs(delta_percent)
    cmd = f"amixer set Master {amt}%{sign}"
    log.info('Ändere Lautstärke: %s', cmd)
    run_cmd(cmd)
    time.sleep(0.05)
    update_leds()


def toggle_mute():
    log.info('Toggele Mute')
    run_cmd('amixer set Master toggle')
    time.sleep(0.05)
    update_leds()


def is_muted():
    try:
        res = subprocess.run(['amixer', 'get', 'Master'], check=True, stdout=subprocess.PIPE, text=True)
        out = res.stdout
        # Suche nach [off]
        return '[off]' in out
    except Exception as e:
        log.warning('amixer nicht verfügbar oder Fehler: %s', e)
    return False


def update_leds():
    # LED für Tastatur: soll leuchten, wenn die Bildschirmtastatur deaktiviert ist
    try:
        kbd_running = is_onboard_running()
        if kbd_running:
            led_kbd_off.off()
        else:
            led_kbd_off.on()
    except Exception:
        pass

    # LED für Mute
    try:
        if is_muted():
            led_muted.on()
        else:
            led_muted.off()
    except Exception:
        pass


def on_scale_down():
    log.debug('Scale down pressed')
    change_scale(-SCALE_STEP)


def on_scale_up():
    log.debug('Scale up pressed')
    change_scale(SCALE_STEP)


def on_toggle_kbd():
    log.debug('Toggle keyboard pressed')
    toggle_onboard()


def on_vol_down():
    log.debug('Volume down pressed')
    vol_change(-5)


def on_vol_up():
    log.debug('Volume up pressed')
    vol_change(5)


def on_mute():
    log.debug('Mute pressed')
    toggle_mute()


def cleanup(signum=None, frame=None):
    log.info('Beende, schalte LEDs aus')
    try:
        led_kbd_off.off()
        led_muted.off()
    except Exception:
        pass
    raise SystemExit


def main():
    global current_scale
    log.info('Starte GPIO-Button Dienst')

    # Setze initialen Scale Wert (falls vorhanden)
    # Versuche aktuellen Scale aus xrandr zu lesen (vereinfachte Annahme)
    current_scale = 1.0

    # Event-Handler
    btn_scale_down.when_pressed = on_scale_down
    btn_scale_up.when_pressed = on_scale_up
    btn_toggle_kbd.when_pressed = on_toggle_kbd
    btn_vol_down.when_pressed = on_vol_down
    btn_vol_up.when_pressed = on_vol_up
    btn_mute.when_pressed = on_mute

    update_leds()

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
