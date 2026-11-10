# GPIO_Buttons_PRO_V2 — Installationsanleitung (Deutsch)

## Überblick

GPIO_Buttons_PRO_V2 ist ein professionelles GPIO-Button-Steuerungssystem für den Raspberry Pi 5 mit Raspberry Pi OS. Es ermöglicht die Steuerung von 6 Buttons und 2 Status-LEDs, organisiert in zwei unabhängigen Gruppen mit jeweils eigenen Modi.

**Linke Gruppe (ML):**
- GPIO 17: Action_1_1 (Bildlauf)
- GPIO 27: Mode_Switch_1 (Bildschirmtastatur + Modus-Umschaltung)
- GPIO 22: Action_1_2 (Bildlauf)
- GPIO 5: Status_1 LED

**Rechte Gruppe (MR):**
- GPIO 23: Action_2_1 (Lautstärke/Zoom/Skalierung)
- GPIO 24: Mode_Switch_2 (Modus-Umschaltung)
- GPIO 25: Action_2_2 (Lautstärke/Zoom/Skalierung)
- GPIO 6: Status_2 LED

## Anforderungen

- **Hardware:** Raspberry Pi 5 mit Raspberry Pi OS
- **Display:** Touchscreen (Raspberry Touch 2) empfohlen
- **Netzwerk:** Internetzugang zur Paketinstallation
- **Berechtigungen:** sudo-Rechte zum Installieren von Paketen und Systemd-Services

## Schritt 1: Repository klonen (falls noch nicht geschehen)

```bash
cd ~
git clone https://github.com/LagartijaMuerta/RaspberryNetworkTester.git
cd RaspberryNetworkTester
```

## Schritt 2: Abhängigkeiten installieren

Das Skript versucht, fehlende Abhängigkeiten automatisch zu installieren. Es wird jedoch empfohlen, die erforderlichen Pakete manuell zu installieren:

```bash
sudo apt update
sudo apt install -y python3-gpiozero xdotool x11-xserver-utils alsa-utils squeekboard
```

### Erklärung der Pakete:
- `python3-gpiozero`: GPIO-Steuerung
- `xdotool`: Tastatur- und Maus-Befehle (Scroll, Zoom)
- `x11-xserver-utils`: xrandr für Bildschirm-Skalierung
- `alsa-utils`: amixer für Lautstärkensteuerung
- `squeekboard`: On-Screen-Tastatur

## Schritt 3: Skript starten

### Manuell (für Tests):

Das Skript muss in der X-Session ausgeführt werden (DISPLAY gesetzt):

```bash
DISPLAY=:0 python3 ~/RaspberryNetworkTester/GPIO_Buttons_PRO_V2.py
```

Oder, wenn du bereits in einer grafischen Sitzung bist:

```bash
python3 ~/RaspberryNetworkTester/GPIO_Buttons_PRO_V2.py
```

### Mit systemd-Service (Autostart im Hintergrund):

#### 3a. Service-Datei erstellen

Erstelle `/etc/systemd/system/gpio-buttons-pro-v2.service`:

```bash
sudo nano /etc/systemd/system/gpio-buttons-pro-v2.service
```

Trage folgende Inhalte ein (**Passe User und Pfade deiner Installation an**):

```ini
[Unit]
Description=GPIO Buttons PRO V2 - Button Control System
After=graphical.target

[Service]
Type=simple
User=pi
Environment=DISPLAY=:0
Environment=XAUTHORITY=/home/pi/.Xauthority
ExecStart=/usr/bin/python3 /home/pi/RaspberryNetworkTester/GPIO_Buttons_PRO_V2.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=graphical.target
```

**Wichtige Punkte:**
- Ersetze `pi` durch deinen Benutzernamen
- Passe den Pfad `/home/pi/RaspberryNetworkTester/...` an
- `DISPLAY=:0` auf deinen Display-Server anpassen (falls nötig `echo $DISPLAY` in der X-Session ausführen)

#### 3b. Service aktivieren und starten

```bash
sudo systemctl daemon-reload
sudo systemctl enable gpio-buttons-pro-v2.service
sudo systemctl start gpio-buttons-pro-v2.service
```

#### 3c. Service-Status prüfen

```bash
sudo systemctl status gpio-buttons-pro-v2.service
```

Logs anschauen:

```bash
sudo journalctl -u gpio-buttons-pro-v2.service -b
# oder für live-Logs:
sudo journalctl -u gpio-buttons-pro-v2.service -f
```

## Konfiguration

Öffne `GPIO_Buttons_PRO_V2.py` und passe die Konfigurationssection oben im Skript an:

```python
# ============================================================================
# CONFIGURATION SECTION - CUSTOMIZE THESE VALUES
# ============================================================================

LOG_LEVEL = logging.INFO

# Button Debounce Time (seconds)
BUTTON_DEBOUNCE_TIME = 0.02

# Hold Detection Threshold (seconds)
HOLD_THRESHOLD = 2.0

# Repeat Delay when button is held (seconds)
REPEAT_DELAY = 0.2

# LED Blink Frequency for ML_2 and MR_3 (Hz)
BLINK_FREQUENCY = 0.5

# Zoom Configuration
ZOOM_FACTOR = 10  # Percentage per zoom action

# Volume Configuration
VOLUME_STEP = 5   # Percentage per volume action

# Screen Scale Configuration
SCALE_STEP = 0.05  # Scale factor per action
SCALE_MIN = 0.5
SCALE_MAX = 2.0
```

Nach Änderungen:

```bash
# Service neu starten
sudo systemctl restart gpio-buttons-pro-v2.service
```

## Modi-Beschreibung

### Linke Gruppe (ML)

**ML_1 (Normal-Modus):**
- GPIO 17: Bildlauf nach oben
- GPIO 22: Bildlauf nach unten
- GPIO 5 LED: Zeigt Squeekboard-Status (An = Squeekboard aktiv, Aus = inaktiv)

**ML_2 (Erweiterter Modus):**
- GPIO 17: Terminal öffnen
- GPIO 22: Browser öffnen
- GPIO 5 LED: Blinkt (0,5 Hz)

**Modus-Wechsel:**
- Kurz GPIO 27 drücken: Squeekboard ein-/ausschalten
- GPIO 27 für 2 Sekunden halten: Zwischen ML_1 und ML_2 wechseln

### Rechte Gruppe (MR)

**MR_1 (Lautstärke-Modus):**
- GPIO 23: Lautstärke +5%
- GPIO 25: Lautstärke -5%
- GPIO 6 LED: Aus

**MR_2 (Zoom-Modus):**
- GPIO 23: Zoom In (Ctrl++)
- GPIO 25: Zoom Out (Ctrl+-)
- GPIO 6 LED: An

**MR_3 (Skalierungs-Modus):**
- GPIO 23: Bildschirm-Skalierung -5%
- GPIO 25: Bildschirm-Skalierung +5%
- GPIO 6 LED: Blinkt (0,5 Hz)

**Modus-Wechsel:**
- Kurz GPIO 24 drücken: Zwischen MR_1 und MR_2 wechseln
  - MR_1 → MR_2 → MR_1 → ...
- GPIO 24 für 2 Sekunden halten: MR_3 aktivieren/deaktivieren
  - In MR_3 haben Kurz-Drücke keine Wirkung
  - GPIO 24 erneut für 2 Sekunden halten: Zurück zu MR_1

## Troubleshooting

### Service startet nicht
```bash
# Logs anschauen
sudo journalctl -u gpio-buttons-pro-v2.service -n 50

# Manuell ausführen für Fehlerausgabe
DISPLAY=:0 python3 ~/RaspberryNetworkTester/GPIO_Buttons_PRO_V2.py
```

### Buttons reagieren nicht
- Prüfe GPIO-Pins mit: `gpio readall` (aus wiringpi)
- Kontrolliere die Verkabelung und Pull-Up-Widerstände
- Überprüfe, ob `python3-gpiozero` korrekt installiert ist: `python3 -c "from gpiozero import Button, LED; print('OK')"`

### X Display nicht erkannt
```bash
# In der grafischen Sitzung laufen:
echo $DISPLAY  # Sollte :0 oder ähnlich ausgeben
echo $XAUTHORITY  # Sollte den Pfad à ~/.Xauthority zeigen

# Diese Werte in der Service-Datei eintragen
```

### Squeekboard funktioniert nicht
```bash
# Prüfe ob Squeekboard installiert ist
which squeekboard

# Starten Sie manuell
DISPLAY=:0 squeekboard
```

### xdotool-Befehle funktionieren nicht
```bash
# Prüfe xdotool-Installation
xdotool --version

# Teste manuell
DISPLAY=:0 xdotool key Page_Up
```

## Performance

Das Skript wurde für minimalen Ressourcenverbrauch optimiert:
- **Kein Polling:** Nutzt gpiozero/GPIO-Interrupt-basierte Event-Handler
- **Threading:** Button-Erkennung läuft in separaten Threads
- **Debouncing:** Verhindert Mehrfach-Auslösungen
- **Effiziente LED-Steuerung:** Separate Threads für Blink-Effekte

## Sicherheit

- Das Skript läuft mit Benutzer-Rechten (nicht Root), benötigt aber sudo für systemd-Service
- Befehle wie `xdotool` und `amixer` werden nur mit dem Benutzer ausgeführt, dem die X-Session gehört
- Stelle sicher, dass nur vertrauenswürdige Benutzer das Skript ausführen können

## Support und Debugging

Aktiviere Debug-Logging:

```python
LOG_LEVEL = logging.DEBUG  # in der Konfigurationssection
```

Dann Logs ansehen:

```bash
sudo journalctl -u gpio-buttons-pro-v2.service -f
```

Oder manuell starten mit Debug-Ausgabe:

```bash
DISPLAY=:0 python3 ~/RaspberryNetworkTester/GPIO_Buttons_PRO_V2.py
```

## Lizenz

MIT

---

**Erstellt mit:** GitHub Copilot
**Letztes Update:** 2024
