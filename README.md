# GPIO_Buttons_PRO_V2 — Installation Guide (English)

## Overview

GPIO_Buttons_PRO_V2 is a professional GPIO button control system for Raspberry Pi 5 with Raspberry Pi OS. It enables control of 6 buttons and 2 status LEDs, organized in two independent groups, each with their own modes.

**Left Group (ML):**
- GPIO 17: Action_1_1 (Scroll)
- GPIO 27: Mode_Switch_1 (On-Screen Keyboard + Mode Switching)
- GPIO 22: Action_1_2 (Scroll)
- GPIO 5: Status_1 LED

**Right Group (MR):**
- GPIO 23: Action_2_1 (Volume/Zoom/Scale)
- GPIO 24: Mode_Switch_2 (Mode Switching)
- GPIO 25: Action_2_2 (Volume/Zoom/Scale)
- GPIO 6: Status_2 LED

## Requirements

- **Hardware:** Raspberry Pi 5 with Raspberry Pi OS
- **Display:** Touchscreen (Raspberry Touch 2) recommended
- **Network:** Internet access for package installation
- **Permissions:** sudo rights for package installation and systemd services

## Step 1: Clone Repository (if not already done)

```bash
cd ~
git clone https://github.com/LagartijaMuerta/RaspberryNetworkTester.git
cd RaspberryNetworkTester
```

## Step 2: Install Dependencies

The script attempts to install missing dependencies automatically. However, it is recommended to install the required packages manually:

```bash
sudo apt update
sudo apt install -y python3-gpiozero xdotool x11-xserver-utils alsa-utils squeekboard wlr-randr
```

### Package Explanation:
- `python3-gpiozero`: GPIO control
- `xdotool`: Keyboard and mouse commands (scroll, zoom)
- `x11-xserver-utils`: xrandr for screen scaling (X11)
- `wlr-randr`: Screen scaling for Wayland (modern systems)
- `alsa-utils`: amixer for volume control
- `squeekboard`: On-screen keyboard

## Step 3: Run the Script

### Manually (for testing):

The script must be run in an X session (with DISPLAY set):

```bash
DISPLAY=:0 python3 ~/RaspberryNetworkTester/GPIO_Buttons_PRO_V2.py
```

Or, if you're already in a graphical session:

```bash
python3 ~/RaspberryNetworkTester/GPIO_Buttons_PRO_V2.py
```

### With systemd service (Autostart in background):

#### 3a. Create service file

Create `/etc/systemd/system/gpio-buttons-pro-v2.service`:

```bash
sudo nano /etc/systemd/system/gpio-buttons-pro-v2.service
```

Enter the following content (**Adjust user and paths for your installation**):

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

**Important points:**
- Replace `pi` with your username
- Adjust the path `/home/pi/RaspberryNetworkTester/...` accordingly
- Adjust `DISPLAY=:0` if needed (run `echo $DISPLAY` in your X session)

#### 3b. Enable and start service

```bash
sudo systemctl daemon-reload
sudo systemctl enable gpio-buttons-pro-v2.service
sudo systemctl start gpio-buttons-pro-v2.service
```

#### 3c. Check service status

```bash
sudo systemctl status gpio-buttons-pro-v2.service
```

View logs:

```bash
sudo journalctl -u gpio-buttons-pro-v2.service -b
# or for live logs:
sudo journalctl -u gpio-buttons-pro-v2.service -f
```

## Configuration

Open `GPIO_Buttons_PRO_V2.py` and adjust the configuration section at the top of the script:

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

After changes:

```bash
# Restart service
sudo systemctl restart gpio-buttons-pro-v2.service
```

## Mode Description

### Left Group (ML)

**ML_1 (Normal Mode):**
- GPIO 17: Scroll up
- GPIO 22: Scroll down
- GPIO 5 LED: Shows Squeekboard status (On = active, Off = inactive)

**ML_2 (Extended Mode):**
- GPIO 17: Open terminal
- GPIO 22: Open browser
- GPIO 5 LED: Blinks (0.5 Hz)

**Mode Switching:**
- Short press GPIO 27: Toggle Squeekboard on/off
- Hold GPIO 27 for 2 seconds: Switch between ML_1 and ML_2

### Right Group (MR)

**MR_1 (Volume Mode):**
- GPIO 23: Volume +5%
- GPIO 25: Volume -5%
- GPIO 6 LED: Off

**MR_2 (Zoom Mode):**
- GPIO 23: Zoom In (Ctrl++)
- GPIO 25: Zoom Out (Ctrl+-)
- GPIO 6 LED: On

**MR_3 (Scale Mode):**
- GPIO 23: Screen scale -5%
- GPIO 25: Screen scale +5%
- GPIO 6 LED: Blinks (0.5 Hz)

**Mode Switching:**
- Short press GPIO 24: Switch between MR_1 and MR_2
  - MR_1 → MR_2 → MR_1 → ...
- Hold GPIO 24 for 2 seconds: Activate/deactivate MR_3
  - In MR_3, short presses have no effect
  - Hold GPIO 24 again for 2 seconds: Return to MR_1

## Additional Features and Restrictions

### Mutual Group Blocking

When **ML_2 (Extended Mode)** is activated:
- The entire right group (MR) is **locked**
- GPIO 23, 25, 24 are unavailable
- Only GPIO 27 can deactivate ML_2
- The on-screen keyboard (Squeekboard) continues to work

When **MR_3 (Scale Mode)** is activated:
- The entire left group (ML) is **locked**
- GPIO 17, 22, 27 are unavailable
- Only GPIO 24 can deactivate MR_3
- Screen scaling is active

**Why this blocking?** This prevents accidental inputs from one group while the other is in an extended/blinking mode.

### Hold Behavior (2+ seconds hold)

**Important:** When holding GPIO 27 or GPIO 24 for 2+ seconds:
- Mode switching is triggered **only once**
- You must release and press again for subsequent mode changes
- This prevents rapid mode switching while holding the button

## Troubleshooting

### Service won't start
```bash
# Check logs
sudo journalctl -u gpio-buttons-pro-v2.service -n 50

# Run manually for error output
DISPLAY=:0 python3 ~/RaspberryNetworkTester/GPIO_Buttons_PRO_V2.py
```

### Buttons not responding
- Check GPIO pins with: `gpio readall` (from wiringpi)
- Verify wiring and pull-up resistors
- Check if `python3-gpiozero` is correctly installed: `python3 -c "from gpiozero import Button, LED; print('OK')"`

### X Display not recognized
```bash
# In your graphical session:
echo $DISPLAY  # Should output :0 or similar
echo $XAUTHORITY  # Should show path to ~/.Xauthority

# Enter these values in your service file
```

### Squeekboard not working
```bash
# Check if Squeekboard is installed
which squeekboard

# Start manually
DISPLAY=:0 squeekboard
```

### xdotool commands not working
```bash
# Check xdotool installation
xdotool --version

# Test manually
DISPLAY=:0 xdotool key Page_Up
```

## Performance

The script is optimized for minimal resource consumption:
- **No Polling:** Uses gpiozero/GPIO interrupt-based event handlers
- **Threading:** Button detection runs in separate threads
- **Debouncing:** Prevents multiple triggers
- **Efficient LED Control:** Separate threads for blink effects

## Security

- Script runs with user permissions (not root), but requires sudo for systemd service
- Commands like `xdotool` and `amixer` are executed only with the user who owns the X session
- Ensure only trusted users can run this script

## Support and Debugging

Enable debug logging:

```python
LOG_LEVEL = logging.DEBUG  # in the configuration section
```

Then view logs:

```bash
sudo journalctl -u gpio-buttons-pro-v2.service -f
```

Or run manually with debug output:

```bash
DISPLAY=:0 python3 ~/RaspberryNetworkTester/GPIO_Buttons_PRO_V2.py
```

## License

MIT

---

**Created with:** GitHub Copilot
**Last Update:** 2024
