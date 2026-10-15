README — 6 Buttons + 2 LEDs (gpio_buttons_6B+2L.py)

Kurzbeschreibung

Dieses Skript steuert 6 GPIO-Buttons auf einem Raspberry Pi (Raspberry Pi OS) und zwei Status-LEDs.
Funktionen:
- GPIO 17: Bildschirm skalieren (-5%)
- GPIO 27: Bildschirm skalieren (+5%)
- GPIO 22: Bildschirmtastatur (onboard) ein-/ausschalten
- GPIO 23: Lautstärke (-5%)
- GPIO 24: Lautstärke (+5%)
- GPIO 25: Mute Toggle
- LED GPIO 5: leuchtet, wenn Bildschirmtastatur deaktiviert ist
- LED GPIO 6: leuchtet, wenn gemutet ist

Voraussetzungen

- Raspberry Pi mit Raspberry Pi OS und X-Server (Grafische Sitzung)
- Netzwerkzugang zum Installieren von Paketen (falls nicht bereits installiert)
- sudo-Rechte zum Installieren von Systempaketen

Benötigte Programme/Pakete

- python3
- python3-gpiozero
- x11-xserver-utils (xrandr)
- xinput
- alsa-utils (amixer)
- onboard (optionale Bildschirmtastatur)

Automatische Installation

Das Skript versucht fehlende Abhängigkeiten automatisch zu installieren (sudo apt-get install). Dabei werden folgende Pakete geprüft und ggf. installiert: python3-gpiozero, x11-xserver-utils, xinput, alsa-utils, onboard.
Hinweis: Die automatische Installation erfordert sudo und kann nach einem Passwort fragen. Es wird empfohlen, die Pakete einmal manuell zu installieren, um Installationsprobleme zu vermeiden.

Manuelle Installation (empfohlen)

```bash
sudo apt update
sudo apt install -y python3-gpiozero x11-xserver-utils xinput alsa-utils onboard
```

Ausführung

Wichtig: Das Skript muss in der X-Session ausgeführt werden (DISPLAY gesetzt), sonst funktionieren xrandr/xinput-Aufrufe nicht.

Beispiel (lokale X-Session auf Display :0):

DISPLAY=:0 python3 "Configurations/6 Buttons + 2 LEDs/gpio_buttons_6B+2L.py"

Wenn das Skript als systemd-Service gestartet werden soll, muss Environment=DISPLAY und ggf. XAUTHORITY korrekt gesetzt werden (siehe Service-Beispiel unten).

Systemd-Service (optional)

Erstelle /etc/systemd/system/gpio-buttons-6b.service (Passe User und Pfade an):

```bash
[Unit]
Description=GPIO Buttons (6B + 2L)
After=graphical.target

[Service]
Type=simple
User=pi
Environment=DISPLAY=:0
# Falls XAUTHORITY nötig: Environment=XAUTHORITY=/home/pi/.Xauthority
ExecStart=/usr/bin/python3 /home/pi/path/to/repo/Configurations/6 Buttons + 2 LEDs/gpio_buttons_6B+2L.py
Restart=on-failure

[Install]
WantedBy=graphical.target
```

Dann aktivieren und starten:

```bash
sudo systemctl daemon-reload
sudo systemctl enable gpio-buttons-6b.service
sudo systemctl start gpio-buttons-6b.service
```

Hinweise / Troubleshooting

- Prüfe mit `xinput --list`, ob Touch- oder Eingabegeräte erkannt werden.
- `amixer get Master` zeigt den aktuellen Mute-/Lautstärke-Status.
- Falls gpiozero nicht importiert werden kann, führt das Skript die automatische Installation aus (siehe oben).
- Das Skript muss mit einem Benutzer laufen, der Zugriff auf die X-Session hat (DISPLAY und ggf. XAUTHORITY).

Sicherheit

Das Skript ruft sudo apt-get auf, wenn Pakete fehlen. Stelle sicher, dass du dem System vertraust und prüfe die installierten Pakete vor dem Ausführen.

Support

Bei Problemen mit der Konfiguration oder beim Starten des Dienstes sende die Ausgabe von `journalctl -u gpio-buttons-6b.service -b` bzw. die Logausgabe, wenn du das Skript manuell startest.
