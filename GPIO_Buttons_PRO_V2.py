#!/usr/bin/env python3
"""
GPIO_Buttons_PRO_V2.py

A professional GPIO button control system for Raspberry Pi 5 with Raspberry Pi OS.
Supports two independent button groups with multiple modes and LED status indicators.

Left Group (ML):  GPIO 5, 17, 27, 22 → Modes: ML_1, ML_2
Right Group (MR): GPIO 6, 23, 24, 25 → Modes: MR_1, MR_2, MR_3

Author: GPIO_Buttons_PRO_V2
License: MIT
"""

import os
import subprocess
import logging
import time
import signal
import shutil
import sys
import threading
from enum import Enum

try:
    from gpiozero import Button, LED
except Exception:
    Button = None
    LED = None

from threading import Lock, Thread, Event

# ============================================================================
# CONFIGURATION SECTION - CUSTOMIZE THESE VALUES
# ============================================================================

# Logging
LOG_LEVEL = logging.INFO

# GPIO Pin Definitions
PIN_ACTION_1_1 = 17          # Left group action button
PIN_MODE_SWITCH_1 = 27       # Left group mode switch (also Squeekboard toggle)
PIN_ACTION_1_2 = 22          # Left group action button
PIN_ACTION_2_1 = 23          # Right group action button
PIN_MODE_SWITCH_2 = 24       # Right group mode switch
PIN_ACTION_2_2 = 25          # Right group action button
PIN_STATUS_1 = 5             # Left group status LED
PIN_STATUS_2 = 6             # Right group status LED

# Button Debounce Time (seconds)
BUTTON_DEBOUNCE_TIME = 0.02

# Hold Detection Threshold (seconds)
HOLD_THRESHOLD = 2.0

# Repeat Delay when button is held (seconds)
REPEAT_DELAY = 0.2

# LED Blink Frequency for ML_2 and MR_3 (Hz)
BLINK_FREQUENCY = 0.5
BLINK_ON_TIME = 1.0 / (2.0 * BLINK_FREQUENCY)
BLINK_OFF_TIME = 1.0 / (2.0 * BLINK_FREQUENCY)

# Zoom Configuration
ZOOM_FACTOR = 10  # Percentage per zoom action

# Volume Configuration
VOLUME_STEP = 5   # Percentage per volume action

# Screen Scale Configuration
SCALE_STEP = 0.05  # Scale factor per action
SCALE_MIN = 0.5
SCALE_MAX = 2.0

# Squeekboard Toggle
SQUEEKBOARD_BIN = "squeekboard"

# ============================================================================
# LOGGER SETUP
# ============================================================================

logging.basicConfig(
    level=LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
log = logging.getLogger('GPIO_Buttons_PRO_V2')

# ============================================================================
# MODE ENUMS
# ============================================================================

class ModeLeftGroup(Enum):
    """Left group modes: ML_1 (normal), ML_2 (extended)"""
    ML_1 = 1  # Normal mode
    ML_2 = 2  # Extended mode (LED blinks)

class ModeRightGroup(Enum):
    """Right group modes: MR_1 (volume), MR_2 (zoom), MR_3 (scale)"""
    MR_1 = 1  # Volume mode
    MR_2 = 2  # Zoom mode
    MR_3 = 3  # Screen scale mode (LED blinks)

# ============================================================================
# DEPENDENCY CHECK AND AUTO-INSTALL
# ============================================================================

def ensure_dependencies():
    """Check and install missing system packages and Python modules."""
    pkgs = []
    if Button is None or LED is None:
        pkgs.append('python3-gpiozero')

    cmd_pkg = {
        'xrandr': 'x11-xserver-utils',
        'xdotool': 'xdotool',
        'amixer': 'alsa-utils',
        'squeekboard': 'squeekboard'
    }
    for cmd, pkg in cmd_pkg.items():
        if shutil.which(cmd) is None:
            pkgs.append(pkg)

    pkgs = list(dict.fromkeys(pkgs))
    if not pkgs:
        if Button is None or LED is None:
            try:
                from gpiozero import Button as _B, LED as _L
                globals()['Button'] = _B
                globals()['LED'] = _L
            except Exception:
                log.error('gpiozero not installed and could not be imported')
                sys.exit(1)
        return

    log.info('Missing packages detected, attempting installation: %s', ', '.join(pkgs))
    try:
        subprocess.run(['sudo', 'apt-get', 'update'], check=False)
        subprocess.run(['sudo', 'apt-get', 'install', '-y'] + pkgs, check=False)
    except Exception as e:
        log.warning('Error during package installation: %s', e)

    if Button is None or LED is None:
        try:
            from gpiozero import Button as _B, LED as _L
            globals()['Button'] = _B
            globals()['LED'] = _L
        except Exception as e:
            log.error('gpiozero could not be imported after installation: %s', e)
            sys.exit(1)

# ============================================================================
# GLOBAL STATE
# ============================================================================

# Left Group State
mode_left = ModeLeftGroup.ML_1
led_status_1 = None
squeekboard_active = False
blink_thread_ml_2 = None
blink_stop_ml_2 = Event()
lr_mode_switch_triggered = False  # Prevent repeated mode switches during hold

# Right Group State
mode_right = ModeRightGroup.MR_1
mode_right_previous = None  # Store previous mode for MR_3 toggle
led_status_2 = None
blink_thread_mr_3 = None
blink_stop_mr_3 = Event()
mr_mode_switch_triggered = False  # Prevent repeated mode switches during hold

# State locks
state_lock_left = Lock()
state_lock_right = Lock()

# Button objects
btn_action_1_1 = None
btn_mode_switch_1 = None
btn_action_1_2 = None
btn_action_2_1 = None
btn_mode_switch_2 = None
btn_action_2_2 = None

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def run_cmd(cmd, shell=True, check=False):
    """Execute a shell command and return the result."""
    try:
        return subprocess.run(cmd, shell=shell, check=check,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except Exception as e:
        log.error('Error executing command "%s": %s', cmd, e)
        return None

def detect_display():
    """Detect the X display environment variable."""
    return os.environ.get('DISPLAY', ':0')

def detect_primary_output():
    """Detect the primary display output for xrandr commands."""
    try:
        res = subprocess.run(['xrandr', '--query'], check=True,
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        for line in res.stdout.splitlines():
            if ' connected primary' in line:
                return line.split()[0]
        for line in res.stdout.splitlines():
            if ' connected ' in line:
                return line.split()[0]
    except Exception as e:
        log.warning('xrandr not available or error: %s', e)
    return None

# ============================================================================
# SQUEEKBOARD CONTROL
# ============================================================================

def is_squeekboard_running():
    """Check if Squeekboard (on-screen keyboard) is running."""
    try:
        res = subprocess.run(['pgrep', '-x', 'squeekboard'],
                           stdout=subprocess.DEVNULL)
        return res.returncode == 0
    except Exception:
        return False

def toggle_squeekboard():
    """Toggle Squeekboard on/off."""
    global squeekboard_active
    display = detect_display()
    env = os.environ.copy()
    env['DISPLAY'] = display

    if is_squeekboard_running():
        log.info('Stopping Squeekboard (on-screen keyboard)')
        squeekboard_active = False
        run_cmd('killall squeekboard', shell=True)
    else:
        log.info('Starting Squeekboard (on-screen keyboard)')
        squeekboard_active = True
        try:
            subprocess.Popen([SQUEEKBOARD_BIN], env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            log.error('Could not start Squeekboard: %s', e)
            squeekboard_active = False

    time.sleep(0.2)
    update_led_status_1()

# ============================================================================
# LED CONTROL AND BLINKING
# ============================================================================

def update_led_status_1():
    """Update LED Status 1 based on left group mode and Squeekboard status."""
    global blink_thread_ml_2, blink_stop_ml_2

    if mode_left == ModeLeftGroup.ML_1:
        # Normal mode: LED reflects Squeekboard status
        if is_squeekboard_running():
            led_status_1.on()
        else:
            led_status_1.off()

        # Stop blinking thread if active
        if blink_thread_ml_2 and blink_thread_ml_2.is_alive():
            blink_stop_ml_2.set()
            blink_thread_ml_2.join(timeout=1)
            blink_thread_ml_2 = None

    elif mode_left == ModeLeftGroup.ML_2:
        # Extended mode: LED blinks
        if not (blink_thread_ml_2 and blink_thread_ml_2.is_alive()):
            blink_stop_ml_2.clear()
            blink_thread_ml_2 = Thread(target=blink_led, args=(led_status_1, blink_stop_ml_2))
            blink_thread_ml_2.daemon = True
            blink_thread_ml_2.start()

def update_led_status_2():
    """Update LED Status 2 based on right group mode."""
    global blink_thread_mr_3, blink_stop_mr_3

    if mode_right == ModeRightGroup.MR_1:
        # Volume mode: LED off
        led_status_2.off()

        # Stop blinking thread if active
        if blink_thread_mr_3 and blink_thread_mr_3.is_alive():
            blink_stop_mr_3.set()
            blink_thread_mr_3.join(timeout=1)
            blink_thread_mr_3 = None

    elif mode_right == ModeRightGroup.MR_2:
        # Zoom mode: LED on
        led_status_2.on()

        # Stop blinking thread if active
        if blink_thread_mr_3 and blink_thread_mr_3.is_alive():
            blink_stop_mr_3.set()
            blink_thread_mr_3.join(timeout=1)
            blink_thread_mr_3 = None

    elif mode_right == ModeRightGroup.MR_3:
        # Scale mode: LED blinks
        if not (blink_thread_mr_3 and blink_thread_mr_3.is_alive()):
            blink_stop_mr_3.clear()
            blink_thread_mr_3 = Thread(target=blink_led, args=(led_status_2, blink_stop_mr_3))
            blink_thread_mr_3.daemon = True
            blink_thread_mr_3.start()

def blink_led(led, stop_event):
    """Make an LED blink at configured frequency until stop_event is set."""
    try:
        while not stop_event.is_set():
            led.on()
            stop_event.wait(BLINK_ON_TIME)
            if stop_event.is_set():
                break
            led.off()
            stop_event.wait(BLINK_OFF_TIME)
    except Exception as e:
        log.error('Error in LED blink thread: %s', e)
    finally:
        led.off()

# ============================================================================
# SCROLL (MOUSE WHEEL) CONTROL
# ============================================================================

def scroll_up():
    """Simulate mouse wheel scroll up."""
    try:
        run_cmd('xdotool key Page_Up', shell=True)
    except Exception as e:
        log.error('Error scrolling up: %s', e)

def scroll_down():
    """Simulate mouse wheel scroll down."""
    try:
        run_cmd('xdotool key Page_Down', shell=True)
    except Exception as e:
        log.error('Error scrolling down: %s', e)

# ============================================================================
# ZOOM CONTROL
# ============================================================================

def zoom_in():
    """Zoom in using Ctrl++ keyboard shortcut."""
    try:
        run_cmd('xdotool key ctrl+plus', shell=True)
    except Exception as e:
        log.error('Error zooming in: %s', e)

def zoom_out():
    """Zoom out using Ctrl+- keyboard shortcut."""
    try:
        run_cmd('xdotool key ctrl+minus', shell=True)
    except Exception as e:
        log.error('Error zooming out: %s', e)

# ============================================================================
# VOLUME CONTROL
# ============================================================================

def volume_up():
    """Increase volume by VOLUME_STEP percent."""
    try:
        cmd = f"amixer set Master {VOLUME_STEP}%+"
        run_cmd(cmd, shell=True)
        log.info('Volume increased by %d%%', VOLUME_STEP)
    except Exception as e:
        log.error('Error increasing volume: %s', e)

def volume_down():
    """Decrease volume by VOLUME_STEP percent."""
    try:
        cmd = f"amixer set Master {VOLUME_STEP}%-"
        run_cmd(cmd, shell=True)
        log.info('Volume decreased by %d%%', VOLUME_STEP)
    except Exception as e:
        log.error('Error decreasing volume: %s', e)

# ============================================================================
# SCREEN SCALE CONTROL
# ============================================================================

def apply_scale(scale):
    """Apply screen scaling via xrandr."""
    output = detect_primary_output()
    if not output:
        log.warning('No display output found; skipping scale adjustment')
        return False

    try:
        cmd = f"xrandr --output {output} --scale {scale}x{scale}"
        run_cmd(cmd, shell=True)
        log.info('Screen scale set to: %.2f', scale)
        return True
    except Exception as e:
        log.error('Error applying scale: %s', e)
        return False

current_scale = 1.0
scale_lock = Lock()

def scale_screen_down():
    """Decrease screen scale by SCALE_STEP."""
    global current_scale
    with scale_lock:
        new_scale = max(SCALE_MIN, current_scale - SCALE_STEP)
        if new_scale != current_scale:
            current_scale = new_scale
            apply_scale(current_scale)

def scale_screen_up():
    """Increase screen scale by SCALE_STEP."""
    global current_scale
    with scale_lock:
        new_scale = min(SCALE_MAX, current_scale + SCALE_STEP)
        if new_scale != current_scale:
            current_scale = new_scale
            apply_scale(current_scale)

# ============================================================================
# APPLICATION LAUNCHERS
# ============================================================================

def open_terminal():
    """Open a terminal window."""
    try:
        display = detect_display()
        env = os.environ.copy()
        env['DISPLAY'] = display
        subprocess.Popen(['x-terminal-emulator'], env=env,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        log.info('Opened terminal')
    except Exception as e:
        log.error('Error opening terminal: %s', e)

def open_browser():
    """Open the default web browser."""
    try:
        display = detect_display()
        env = os.environ.copy()
        env['DISPLAY'] = display
        subprocess.Popen(['sensible-browser'], env=env,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        log.info('Opened web browser')
    except Exception as e:
        log.error('Error opening browser: %s', e)

# ============================================================================
# BUTTON PRESS HANDLERS - LEFT GROUP (ML)
# ============================================================================

def handle_action_1_1_press():
    """Handle GPIO 17 (Action_1_1) press."""
    with state_lock_left:
        # Check if right group is in MR_3 (scale/blink mode)
        if mode_right == ModeRightGroup.MR_3:
            log.warning('Action_1_1: Blocked - MR_3 (scale mode) is active')
            return

        if mode_left == ModeLeftGroup.ML_1:
            log.debug('Action_1_1: Scroll up')
            scroll_up()
        elif mode_left == ModeLeftGroup.ML_2:
            log.debug('Action_1_1: Open terminal')
            open_terminal()

def handle_action_1_1_hold(duration):
    """Handle GPIO 17 (Action_1_1) held for duration."""
    # Repeat action while held
    with state_lock_left:
        # Check if right group is in MR_3 (scale/blink mode)
        if mode_right == ModeRightGroup.MR_3:
            log.debug('Action_1_1 held: Blocked - MR_3 (scale mode) is active')
            return

        if mode_left == ModeLeftGroup.ML_1:
            log.debug('Action_1_1 held: Continuous scroll up')
        elif mode_left == ModeLeftGroup.ML_2:
            log.debug('Action_1_1 held: No repeat action in ML_2')

def handle_action_1_2_press():
    """Handle GPIO 22 (Action_1_2) press."""
    with state_lock_left:
        # Check if right group is in MR_3 (scale/blink mode)
        if mode_right == ModeRightGroup.MR_3:
            log.warning('Action_1_2: Blocked - MR_3 (scale mode) is active')
            return

        if mode_left == ModeLeftGroup.ML_1:
            log.debug('Action_1_2: Scroll down')
            scroll_down()
        elif mode_left == ModeLeftGroup.ML_2:
            log.debug('Action_1_2: Open browser')
            open_browser()

def handle_action_1_2_hold(duration):
    """Handle GPIO 22 (Action_1_2) held for duration."""
    # Repeat action while held
    with state_lock_left:
        # Check if right group is in MR_3 (scale/blink mode)
        if mode_right == ModeRightGroup.MR_3:
            log.debug('Action_1_2 held: Blocked - MR_3 (scale mode) is active')
            return

        if mode_left == ModeLeftGroup.ML_1:
            log.debug('Action_1_2 held: Continuous scroll down')
        elif mode_left == ModeLeftGroup.ML_2:
            log.debug('Action_1_2 held: No repeat action in ML_2')

def handle_mode_switch_1_press():
    """Handle GPIO 27 (Mode_Switch_1) short press."""
    global squeekboard_active, lr_mode_switch_triggered
    log.debug('Mode_Switch_1: Short press - toggle Squeekboard')
    lr_mode_switch_triggered = False  # Reset flag for next hold
    toggle_squeekboard()

def handle_mode_switch_1_hold(duration):
    """Handle GPIO 27 (Mode_Switch_1) long press (2+ seconds)."""
    global mode_left, lr_mode_switch_triggered

    # Only trigger mode switch once per hold
    if lr_mode_switch_triggered:
        return

    lr_mode_switch_triggered = True

    # Check if MR_3 is active (other group in blink mode)
    if mode_right == ModeRightGroup.MR_3:
        log.warning('Mode_Switch_1: Cannot switch ML when MR_3 (scale mode) is active')
        return

    with state_lock_left:
        if mode_left == ModeLeftGroup.ML_1:
            mode_left = ModeLeftGroup.ML_2
            log.info('Mode_Switch_1: Switched to ML_2 (Extended mode)')
        else:
            mode_left = ModeLeftGroup.ML_1
            log.info('Mode_Switch_1: Switched to ML_1 (Normal mode)')

        update_led_status_1()

# ============================================================================
# BUTTON PRESS HANDLERS - RIGHT GROUP (MR)
# ============================================================================

def handle_action_2_1_press():
    """Handle GPIO 23 (Action_2_1) press."""
    with state_lock_right:
        # Check if left group is in ML_2 (blink mode)
        if mode_left == ModeLeftGroup.ML_2:
            log.warning('Action_2_1: Blocked - ML_2 (extended mode) is active')
            return

        if mode_right == ModeRightGroup.MR_1:
            log.debug('Action_2_1: Volume up')
            volume_up()
        elif mode_right == ModeRightGroup.MR_2:
            log.debug('Action_2_1: Zoom in')
            zoom_in()
        elif mode_right == ModeRightGroup.MR_3:
            log.debug('Action_2_1: Scale screen down')
            scale_screen_down()

def handle_action_2_1_hold(duration):
    """Handle GPIO 23 (Action_2_1) held for duration."""
    # Repeat action while held
    with state_lock_right:
        # Check if left group is in ML_2 (blink mode)
        if mode_left == ModeLeftGroup.ML_2:
            log.debug('Action_2_1 held: Blocked - ML_2 is active')
            return

        if mode_right == ModeRightGroup.MR_1:
            log.debug('Action_2_1 held: Continuous volume up')
            volume_up()
        elif mode_right == ModeRightGroup.MR_2:
            log.debug('Action_2_1 held: Continuous zoom in')
            zoom_in()
        elif mode_right == ModeRightGroup.MR_3:
            log.debug('Action_2_1 held: Continuous scale screen down')
            scale_screen_down()

def handle_action_2_2_press():
    """Handle GPIO 25 (Action_2_2) press."""
    with state_lock_right:
        # Check if left group is in ML_2 (blink mode)
        if mode_left == ModeLeftGroup.ML_2:
            log.warning('Action_2_2: Blocked - ML_2 (extended mode) is active')
            return

        if mode_right == ModeRightGroup.MR_1:
            log.debug('Action_2_2: Volume down')
            volume_down()
        elif mode_right == ModeRightGroup.MR_2:
            log.debug('Action_2_2: Zoom out')
            zoom_out()
        elif mode_right == ModeRightGroup.MR_3:
            log.debug('Action_2_2: Scale screen up')
            scale_screen_up()

def handle_action_2_2_hold(duration):
    """Handle GPIO 25 (Action_2_2) held for duration."""
    # Repeat action while held
    with state_lock_right:
        # Check if left group is in ML_2 (blink mode)
        if mode_left == ModeLeftGroup.ML_2:
            log.debug('Action_2_2 held: Blocked - ML_2 is active')
            return

        if mode_right == ModeRightGroup.MR_1:
            log.debug('Action_2_2 held: Continuous volume down')
            volume_down()
        elif mode_right == ModeRightGroup.MR_2:
            log.debug('Action_2_2 held: Continuous zoom out')
            zoom_out()
        elif mode_right == ModeRightGroup.MR_3:
            log.debug('Action_2_2 held: Continuous scale screen up')
            scale_screen_up()

def handle_mode_switch_2_press():
    """Handle GPIO 24 (Mode_Switch_2) short press."""
    global mode_right, mr_mode_switch_triggered

    # Check if left group is in ML_2 (blink mode)
    if mode_left == ModeLeftGroup.ML_2:
        log.warning('Mode_Switch_2: Cannot switch MR when ML_2 (extended mode) is active')
        return

    mr_mode_switch_triggered = False  # Reset flag for next hold

    with state_lock_right:
        if mode_right == ModeRightGroup.MR_1:
            mode_right = ModeRightGroup.MR_2
            log.info('Mode_Switch_2: Switched to MR_2 (Zoom mode)')
        elif mode_right == ModeRightGroup.MR_2:
            mode_right = ModeRightGroup.MR_1
            log.info('Mode_Switch_2: Switched to MR_1 (Volume mode)')
        elif mode_right == ModeRightGroup.MR_3:
            # In MR_3, short press does nothing
            log.debug('Mode_Switch_2: Short press ignored in MR_3')
            return

        update_led_status_2()

def handle_mode_switch_2_hold(duration):
    """Handle GPIO 24 (Mode_Switch_2) long press (2+ seconds)."""
    global mode_right, mode_right_previous, mr_mode_switch_triggered

    # Only trigger mode switch once per hold
    if mr_mode_switch_triggered:
        return

    mr_mode_switch_triggered = True

    # Check if left group is in ML_2 (blink mode)
    if mode_left == ModeLeftGroup.ML_2:
        log.warning('Mode_Switch_2: Cannot switch MR when ML_2 (extended mode) is active')
        return

    with state_lock_right:
        if mode_right == ModeRightGroup.MR_3:
            # Return to previous mode (MR_1 or MR_2)
            if mode_right_previous:
                mode_right = mode_right_previous
                log.info('Mode_Switch_2: Disabled MR_3 (Scale mode), returned to %s', mode_right.name)
            else:
                mode_right = ModeRightGroup.MR_1
                log.info('Mode_Switch_2: Disabled MR_3 (Scale mode), switched to MR_1')
        else:
            # Store current mode and switch to MR_3
            mode_right_previous = mode_right
            mode_right = ModeRightGroup.MR_3
            log.info('Mode_Switch_2: Activated MR_3 (Scale mode)')

        update_led_status_2()

# ============================================================================
# BUTTON HOLD DETECTION WRAPPER
# ============================================================================

def create_button_handler(on_press, on_hold):
    """Create a button press handler that detects holds."""
    def handler():
        press_time = time.time()

        # Call press handler immediately
        on_press()

        # Wait a bit and then check if button is still held
        time.sleep(HOLD_THRESHOLD)

        # If button is still held, call hold handler
        if btn_mode_switch_1.is_pressed or btn_mode_switch_2.is_pressed or \
           btn_action_1_1.is_pressed or btn_action_1_2.is_pressed or \
           btn_action_2_1.is_pressed or btn_action_2_2.is_pressed:
            on_hold(time.time() - press_time)

            # Continue repeating action while button is held
            while btn_mode_switch_1.is_pressed or btn_mode_switch_2.is_pressed or \
                  btn_action_1_1.is_pressed or btn_action_1_2.is_pressed or \
                  btn_action_2_1.is_pressed or btn_action_2_2.is_pressed:
                time.sleep(REPEAT_DELAY)
                on_hold(time.time() - press_time)

    return handler

# Actually, gpiozero Button has is_held, but we need to implement a proper handler
# Let me refactor this to use threading for better hold detection

class ButtonHandler(Thread):
    """Thread-based button handler with hold detection."""

    # Distinguishes action buttons (repeat hold) from mode-switch buttons (single hold)
    IS_MODE_SWITCH = False

    def __init__(self, button, on_press, on_hold, is_mode_switch=False):
        super().__init__()
        self.button = button
        self.on_press = on_press
        self.on_hold = on_hold
        self.is_mode_switch = is_mode_switch
        self.daemon = True
        self.running = True

    def run(self):
        """Monitor button state and call appropriate handlers."""
        last_state = False
        press_time = 0.0
        hold_triggered = False

        while self.running:
            current_state = self.button.is_pressed

            # Button pressed (transition from not pressed to pressed)
            if current_state and not last_state:
                press_time = time.time()
                hold_triggered = False
                last_state = True

            # Button held
            if current_state and last_state:
                duration = time.time() - press_time

                # Trigger hold handler after HOLD_THRESHOLD
                if duration >= HOLD_THRESHOLD and not hold_triggered:
                    hold_triggered = True
                    try:
                        self.on_hold(duration)
                    except Exception as e:
                        log.error('Error in hold handler: %s', e)

                # Continue repeating hold action ONLY for action buttons, NOT mode switches
                if hold_triggered and not self.is_mode_switch:
                    try:
                        self.on_hold(duration)
                    except Exception as e:
                        log.error('Error in hold handler: %s', e)
                    time.sleep(REPEAT_DELAY)

            # Button released (transition from pressed to not pressed)
            if not current_state and last_state:
                duration = time.time() - press_time
                last_state = False

                # If hold was not triggered, it was a short press
                if not hold_triggered and duration < HOLD_THRESHOLD:
                    try:
                        self.on_press()
                    except Exception as e:
                        log.error('Error in press handler: %s', e)

            time.sleep(0.01)  # Small sleep to prevent busy-waiting

    def stop(self):
        """Stop the handler thread."""
        self.running = False

# ============================================================================
# MAIN INITIALIZATION AND CLEANUP
# ============================================================================

def setup_buttons():
    """Initialize GPIO buttons."""
    global btn_action_1_1, btn_mode_switch_1, btn_action_1_2
    global btn_action_2_1, btn_mode_switch_2, btn_action_2_2

    log.info('Setting up GPIO buttons...')

    btn_action_1_1 = Button(PIN_ACTION_1_1, pull_up=True, bounce_time=BUTTON_DEBOUNCE_TIME)
    btn_mode_switch_1 = Button(PIN_MODE_SWITCH_1, pull_up=True, bounce_time=BUTTON_DEBOUNCE_TIME)
    btn_action_1_2 = Button(PIN_ACTION_1_2, pull_up=True, bounce_time=BUTTON_DEBOUNCE_TIME)
    btn_action_2_1 = Button(PIN_ACTION_2_1, pull_up=True, bounce_time=BUTTON_DEBOUNCE_TIME)
    btn_mode_switch_2 = Button(PIN_MODE_SWITCH_2, pull_up=True, bounce_time=BUTTON_DEBOUNCE_TIME)
    btn_action_2_2 = Button(PIN_ACTION_2_2, pull_up=True, bounce_time=BUTTON_DEBOUNCE_TIME)

    log.info('GPIO buttons initialized successfully')

def setup_leds():
    """Initialize GPIO LEDs."""
    global led_status_1, led_status_2

    log.info('Setting up GPIO LEDs...')

    led_status_1 = LED(PIN_STATUS_1)
    led_status_2 = LED(PIN_STATUS_2)

    # Initial state
    led_status_1.off()
    led_status_2.off()

    log.info('GPIO LEDs initialized successfully')

def setup_button_handlers():
    """Set up button event handlers."""
    log.info('Setting up button event handlers...')

    # Create handler threads
    # Action buttons: repeat hold (is_mode_switch=False)
    # Mode-switch buttons: single trigger on hold (is_mode_switch=True)
    handlers = [
        ButtonHandler(btn_action_1_1, handle_action_1_1_press, handle_action_1_1_hold, is_mode_switch=False),
        ButtonHandler(btn_action_1_2, handle_action_1_2_press, handle_action_1_2_hold, is_mode_switch=False),
        ButtonHandler(btn_mode_switch_1, handle_mode_switch_1_press, handle_mode_switch_1_hold, is_mode_switch=True),
        ButtonHandler(btn_action_2_1, handle_action_2_1_press, handle_action_2_1_hold, is_mode_switch=False),
        ButtonHandler(btn_action_2_2, handle_action_2_2_press, handle_action_2_2_hold, is_mode_switch=False),
        ButtonHandler(btn_mode_switch_2, handle_mode_switch_2_press, handle_mode_switch_2_hold, is_mode_switch=True),
    ]

    # Start all handler threads
    for handler in handlers:
        handler.start()

    log.info('Button event handlers started')

    return handlers

def cleanup(signum=None, frame=None):
    """Clean up resources and exit gracefully."""
    log.info('Shutting down...')

    try:
        if led_status_1:
            led_status_1.off()
        if led_status_2:
            led_status_2.off()

        # Stop blink threads
        if blink_stop_ml_2:
            blink_stop_ml_2.set()
        if blink_stop_mr_3:
            blink_stop_mr_3.set()

    except Exception as e:
        log.error('Error during cleanup: %s', e)

    log.info('Shutdown complete')
    sys.exit(0)

# ============================================================================
# MAIN
# ============================================================================

def main():
    """Main function."""
    log.info('GPIO_Buttons_PRO_V2 starting...')

    # Ensure dependencies
    ensure_dependencies()

    # Set up GPIO
    setup_buttons()
    setup_leds()

    # Initialize Squeekboard status
    global squeekboard_active
    squeekboard_active = is_squeekboard_running()
    update_led_status_1()

    # Set up button handlers with hold detection
    handlers = setup_button_handlers()

    # Register signal handlers
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    log.info('GPIO_Buttons_PRO_V2 ready and running')

    # Keep the main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        cleanup()

if __name__ == '__main__':
    main()
