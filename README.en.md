> **Note**  
> This project was formerly known as `gps-time-sync`.

# ChronoGPS

**GPS / NTP Time Synchronization Tool for Windows**

A tool to accurately synchronize your Windows PC clock using a GPS receiver or NTP server.  
Designed for high-precision time alignment required for FT8 and other digital amateur radio modes.  
Runs safely in "Monitor-Only" mode even without administrator privileges.

🌐 [日本語 README](README.md)

![ChronoGPS](icon.png)

---

## Design Philosophy

ChronoGPS is designed with one simple goal:
**to provide accurate time with minimal user intervention.**

- Use GPS or NTP depending on availability and environment
- Perform synchronization safely in the background while keeping the UI stable
- Provide a reliable time reference for FT8 and measurement use cases

Rather than visual effects, the focus is on **accuracy, stability, and long-term operation**.

---

## Why ChronoGPS?

If you are interested in the design philosophy behind ChronoGPS —  
including transparency, how administrator privileges are handled, and the idea of a “monitor-only mode” —  
please see the detailed discussion below:

- 🔗 **Why ChronoGPS (Discussion)**: <URL>https://github.com/jp1lrt/ChronoGPS/discussions/3

---

## Features

- 🌐 **NTP Sync (RFC 5905)** — 64-bit timestamps, offset/delay calculation via t1/t2/t3/t4, millisecond-level precision
- 🛰️ **GPS Sync** — Off / Instant / Scheduled modes, RMC-based UTC acquisition, duplicate sync prevention  
Scheduled mode uses a GPS-reception-triggered approach with median jitter filtering, maintaining ±0.1s accuracy
- ⏱️ **FT8 Time Offset** — Fine-tune clock in ±0.1s steps, designed for digital mode operation
- 📡 **Satellite View** — Real-time display of GPS / GLONASS / BeiDou / Galileo / SBAS / QZSS
- 🔒 **Non-Admin Support** — Choose "Restart as Admin" or "Monitor-Only" at launch
- 🧵 **Thread-Safe GUI** — Worker thread + Queue + main thread updates prevent Tkinter freezes
- 🌍 **16 Languages** — Japanese, English, French, Spanish, German, Chinese (Simplified/Traditional), Korean, Portuguese, Italian, Dutch, Russian, Polish, Turkish, Swedish, Indonesian
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

1. Place `ChronoGPS.exe`, and `icon.ico` in the same folder
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

### GNSS Sync Recommendation

For FT8 / FT4 operation, **Instant Sync** is usually sufficient and recommended.  
GNSS provides an absolute UTC reference, so a single calibration before operation
is enough to achieve accurate system time.

**Periodic Sync** is intended for:
- Monitoring clock drift during long sessions
- Checking GPS reception stability
- Diagnostic and verification purposes

For everyday FT8 / FT4 operation, **Instant Sync is recommended**.

### NTP Sync

1. Enter an NTP server (default: `pool.ntp.org`)
   - Recommended for Japan: `ntp.nict.jp`
2. Click "NTP Sync" for immediate sync, or enable auto-sync

### FT8 Offset

If your FT8 timing is slightly off, enter an offset value (seconds) and click "Apply".  
Quick ±0.1s adjustment buttons are also available.

---

## About Displayed Time Differences

You may occasionally see small differences between the displayed
System Time, GPS Time, and NTP Time.

These differences are caused by update timing and display refresh intervals.
They do **not** indicate an error in actual time synchronization.

The internal synchronization logic maintains millisecond-level accuracy.

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

QZSS (Quasi-Zenith Satellite System / Michibiki) is Japan's regional satellite navigation system. It will appear in the satellite view tab if your receiver supports NMEA output for QZSS.  
Some receivers disable QZSS NMEA output by default — an empty QZSS panel is normal behavior.

---

## Notes

- On first launch, Windows may ask "Allow this app to make changes?" — click Yes
- **The × button minimizes to the system tray.** To fully exit, right-click the tray icon → "Quit"
- Default NTP server is `pool.ntp.org`. Change to any preferred server (e.g. `time.windows.com`)

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

## Download

Official binaries are distributed via GitHub Releases. Always check the "Latest" release.

- Latest release: https://github.com/jp1lrt/ChronoGPS/releases/latest
- [ChronoGPS.exe](https://github.com/jp1lrt/ChronoGPS/releases/latest/download/ChronoGPS.exe) — Windows executable
- [icon.ico](https://github.com/jp1lrt/ChronoGPS/releases/latest/download/icon.ico) — Application icon

Included files:
- ChronoGPS.exe — Windows executable (PyInstaller build)
- icon.ico — Application icon
- checksums.txt — SHA256 checksums for release files

Verify downloaded binary (PowerShell):
```powershell
Get-FileHash .\ChronoGPS.exe -Algorithm SHA256
```
Compare the printed hash with the corresponding line in `checksums.txt` attached to the release.

All releases are signed with GPG (`checksums.txt.asc`).
Note: Windows Authenticode signing (which suppresses SmartScreen warnings) is not currently implemented.

## Usage
See README.md for detailed instructions (Japanese).

---

## False Positive Warnings from Antivirus Software

Some antivirus software may flag ChronoGPS.exe as suspicious.
This is a known false positive caused by heuristic detection of PyInstaller-built executables.
The application contains no malicious code.

All source code is publicly available and you can build the exe yourself.

- VirusTotal scan results: https://www.virustotal.com/gui/file/392673eab8d9a4bf72e3e34505bdaf11e9b10b2b70df614be8a6e95f7ae64db3/detection
- This has been reported to Microsoft as an incorrect detection

---

### English — Verify downloaded release files

1. Import the maintainer's public key from GitHub:
   ```bash
   # Linux / macOS
   curl -s https://github.com/jp1lrt.gpg | gpg --import

   # Windows (PowerShell)
   Invoke-WebRequest -Uri https://github.com/jp1lrt.gpg -OutFile mypubkey.asc
   gpg --import mypubkey.asc
   ```

2. Verify the detached signature on `checksums.txt`:
   ```bash
   gpg --verify checksums.txt.asc checksums.txt
   ```
   You should see a "Good signature" (or 日本語環境で「正しい署名"). Confirm the key id and UID:
   - Key ID: `864FA6445EE4D4E3`
   - UID: `Yoshiharu Tsukuura <jp1lrt@jarl.com>`

3. Compute the SHA256 of the downloaded asset and compare with `checksums.txt`:
   ```powershell
   # Windows PowerShell
   Get-FileHash ChronoGPS.exe -Algorithm SHA256

   # Linux / macOS
   sha256sum ChronoGPS.exe
   ```
   Ensure the printed hash exactly matches the corresponding line in `checksums.txt`.

4. If the signature is invalid or the key/UID differs, do NOT trust the files and contact the project maintainer.

---

## License

MIT License — © 2026 Yoshiharu Tsukuura (JP1LRT)

See [LICENSE](LICENSE) for details.

---

## Author

**Yoshiharu Tsukuura / 津久浦 慶治**  
Amateur Radio Station **JP1LRT** / [@jp1lrt](https://github.com/jp1lrt/ChronoGPS)

---

## Donate

If you find ChronoGPS useful, a small donation would be greatly appreciated  
and help support future development ☕

[![Donate](https://img.shields.io/badge/Donate-PayPal-blue)](https://www.paypal.me/jp1lrt)
[![Coffee](https://img.shields.io/badge/Coffee-☕-yellow)](https://www.paypal.me/jp1lrt)

---

## Why ChronoGPS?
- 🔗 **Why ChronoGPS (Discussion)**: <URL>https://github.com/jp1lrt/ChronoGPS/discussions/3

Note: This project was formerly known as gps-time-sync.
