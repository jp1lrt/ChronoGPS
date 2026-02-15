# ChronoGPS

**GPS / NTP Time Synchronization Tool for Windows**

A tool to accurately synchronize your Windows PC clock using a GPS receiver or NTP server.  
Designed for high-precision time alignment required for FT8 and other digital amateur radio modes.  
Runs safely in "Monitor-Only" mode even without administrator privileges.

🌐 [日本語 README](README.md)

![ChronoGPS](icon.png)

---

## Features

- 🌐 **NTP Sync (RFC 5905)** — 64-bit timestamps, offset/delay calculation via t1/t2/t3/t4, millisecond-level precision
- 🛰️ **GPS Sync** — Off / Instant / Scheduled modes, RMC-based UTC acquisition, duplicate sync prevention
- ⏱️ **FT8 Time Offset** — Fine-tune clock in ±0.1s steps, designed for digital mode operation
- 📡 **Satellite View** — Real-time display of GPS / GLONASS / BeiDou / Galileo / SBAS
- 🔒 **Non-Admin Support** — Choose "Restart as Admin" or "Monitor-Only" at launch
- 🧵 **Thread-Safe GUI** — Worker thread + Queue + main thread updates prevent Tkinter freezes
- 🌍 **15 Languages** — Japanese, English, French, Spanish, German, Chinese (Simplified/Traditional), Korean, Portuguese, Italian, Dutch, Russian, Polish, Turkish, Swedish
- 🖥️ **Windows-Native UX** — System tray support, × button minimizes to tray, taskbar icon

---

## Operation Modes

### With Administrator Privileges
- Full GPS / NTP time synchronization available

### Without Administrator Privileges
Choose at startup:
- **Restart as Administrator** → Elevate via UAC, unlock all features
- **Continue in Monitor-Only** → GPS reception, satellite view, NTP display only (no clock write)

---

## Requirements

- Windows 10 / 11
- Python 3.11+ (for script execution)
- GPS receiver (for GPS sync)
- Administrator privileges (for time synchronization)

---

## Installation & Launch

### Using the exe (Recommended)

1. Place `ChronoGPS.exe`, `icon.png`, and `icon.ico` in the same folder
2. Right-click `ChronoGPS.exe` → "Run as administrator"

### Running from source

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

### Building the exe

```powershell
pyinstaller --onefile --windowed --icon=icon.ico --name=ChronoGPS main.py
```

Output: `dist\ChronoGPS.exe`

---

## Usage

### GPS Sync

1. Connect your GPS receiver to the PC
2. Select the COM port and baud rate (usually 9600)
3. Click "Start" to begin receiving
4. Set GPS sync mode to "Instant" or "Scheduled"

### NTP Sync

1. Enter an NTP server (default: `pool.ntp.org`)
   - Recommended for Japan: `ntp.nict.jp`
2. Click "NTP Sync" for immediate sync, or enable auto-sync

### FT8 Offset

If your FT8 timing is slightly off, enter an offset value (seconds) and click "Apply".  
Quick ±0.1s adjustment buttons are also available.

---

## About Satellite Information

| Display | Meaning |
|---|---|
| In Use (GNSS) | GPS / GLONASS / BeiDou / Galileo primary satellites — used directly for time and position |
| In Use (SBAS) | WAAS / MSAS / EGNOS augmentation satellites — used for correction, not as a time source |
| Tracked | Received but not used in the time/position solution |

SBAS satellites (MSAS in Japan) may be tracked but not appear as "In Use" — this is normal behavior.  
SBAS provides augmentation corrections, not a primary clock signal.  
ChronoGPS uses GNSS primary satellites and NTP for time sync, a design comparable to professional GNSS timing receivers.

---

## Notes

- On first launch, Windows may ask "Allow this app to make changes?" — click Yes
- **The × button minimizes to the system tray.** To fully exit, right-click the tray icon → "Quit"
- Default NTP server is `pool.ntp.org`. Change to any preferred server (e.g. `time.windows.com`)

---

## Known Limitations

- "Start with Windows" option is not yet functional (planned for next version)

---

## File Structure

```
ChronoGPS/
├── main.py               # Entry point
├── gui.py                # Main GUI
├── config.py             # Settings (JSON)
├── locales.py            # Localization
├── locales_override.py   # Localization overrides
├── nmea_parser.py        # NMEA parser
├── ntp_client.py         # NTP client
├── time_sync.py          # Time synchronization
├── autostart.py          # Auto-start management
├── tray_icon.py          # System tray
├── requirements.txt      # Dependencies
├── icon.png              # App icon (PNG)
├── icon.ico              # App icon (ICO)
└── gps_time_sync_config.json  # Config file (auto-generated)
```

---

## License

MIT License — © 2026 Yoshiharu Tsukuura (JP1LRT)

See [LICENSE](LICENSE) for details.

---

## Author

**Yoshiharu Tsukuura / 津久浦 慶治**  
Amateur Radio Station **JP1LRT** / [@jp1lrt](https://github.com/jp1lrt/gps-time-sync)

---

## Donate

If you find ChronoGPS useful, a small donation would be greatly appreciated  
and help support future development ☕

[![Donate](https://img.shields.io/badge/Donate-PayPal-blue)](https://www.paypal.me/jp1lrt)
[![Coffee](https://img.shields.io/badge/Coffee-☕-yellow)](https://www.paypal.me/jp1lrt)
