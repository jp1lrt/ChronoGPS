# FAQ (Frequently Asked Questions)

## Q1. I see “⏰ Time adjusted” very frequently. Is something wrong?

**A. No — this is normal behavior.**

ChronoGPS uses **GNSS (GPS / QZSS, etc.)** as a high-precision time reference directly tied to UTC.  
By contrast, the Windows system clock has an internal **time granularity / quantization** on the order of **a few to tens of milliseconds (environment-dependent)**.  
When compared against a precise GNSS reference, small differences can be detected continuously.

ChronoGPS does not hide this — it detects it and applies corrections **only when necessary**.

Typical correction amounts you may see in the log, such as:

- ±0.011s  
- ±0.013s  
- ±0.07–0.08s  

are within the normal range of Windows granularity and natural drift.

After corrections, ChronoGPS will often report:

- `✓ Time is accurate (error: 0.000–0.009s)`

For FT8 / FT4 (typically ±1 second tolerance), this provides **more than two orders of magnitude of margin**.

This does **not** mean the time is unstable — it means  
**small behavior that was previously invisible is now being made visible.**

---

## Q2. Why do I see repeated corrections even when using Instant Sync?

**A. Because Instant Sync is not a “rewrite every second” mode.**

Instant Sync is **not** “calibrate once and forget.”  
It is designed to **keep referencing GNSS during operation** and maintain a correct state while avoiding unnecessary writes.

Instant Sync is designed to:

- use GNSS as a reference, and  
- **calibrate the Windows system clock using a representative value**, then  
- **continue monitoring while respecting the OS time model**

Instant Sync **continuously references GNSS**,  
but it does **not** force continuous or second-by-second rewrites of system time.

When Windows-side quantization or natural drift is detected and a correction is justified,  
ChronoGPS applies **minimal and explainable corrections only when required**.

As a result:

- “Time adjusted” may appear repeatedly  
- while the effective error remains very small

This behavior is normal and indicates healthy GNSS-referenced operation.

### Recommended usage

- **Everyday FT8 / FT4 operation**
  - Keep **Instant Sync enabled**
  - ChronoGPS will monitor GNSS continuously and correct only when necessary
  - Occasional small adjustment logs are expected and normal

- **Long sessions / drift monitoring / verification**
  - Use **Weak Sync (Interval Sync)**

Instant Sync does not “pull the clock every second.”  
It is a mode designed to **maintain a correctly calibrated state without destabilizing the OS clock**.

---

## Q3. What does “Weak” in Weak Sync (Interval Sync) mean?

**A. It means corrections are intentionally suppressed by design.**

Weak Sync (Interval Sync) works as follows:

- continuously collect offset samples every second  
- evaluate only when the configured interval is reached  
- **if the offset is within the threshold, intentionally do not correct**

This does **not** mean lower accuracy.  
It is designed to avoid injecting **GNSS reception jitter** into the Windows system clock.

Weak Sync is intended for:

- long-term drift monitoring  
- observing GNSS reception stability  
- diagnostics / logging / verification  

The philosophy is:

**monitoring first, correction only as an exception (stability-first).**

---

## Q4. I see one-direction drift like `-0.03s → -0.05s`. Is that a problem?

**A. No — this is typically normal.**

In many cases, this represents natural drift of the PC system clock.

Correcting every tiny change would risk injecting GNSS jitter into OS time.  
ChronoGPS therefore uses a conservative, explainable policy:

- within threshold → **intentionally do nothing**  
- beyond threshold → **correct only when necessary**

---

## Q5. Which mode should I use for FT8 / FT4?

**A. For normal operation, Instant Sync is recommended.**

- **Everyday FT8 / FT4 operation**
  - → **Instant Sync**
  - It is safe to keep this mode enabled during operation
  - GNSS is continuously referenced, while corrections are minimized

- **Long sessions / verification / monitoring**
  - → **Weak Sync (Interval Sync)**

ChronoGPS is not a tool that continuously forces time.  
It is designed to **maintain a correct state without destabilizing the OS clock**.

---

## Q6. Should I use NTP Sync or GNSS (GPS) Sync?

**A. If possible, GNSS (GPS / QZSS) Sync is recommended.**

ChronoGPS treats GNSS as a first-class time source:

- **GNSS**
  - UTC-based absolute time
  - not affected by network delay
  - ideal for FT8 and measurement use

- **NTP**
  - depends on network quality
  - affected by routing / congestion / latency
  - useful when GNSS is unavailable

ChronoGPS implements NTP according to **RFC 5905** (t1/t2/t3/t4 for offset/delay).  
In general, because GNSS avoids network-delay variability, **GNSS tends to provide a more stable reference in many environments**  
(though behavior can vary with receiver quality and reception conditions).

---

## Q7. Is it OK that ChronoGPS runs NTP sync at startup and then GNSS sync afterward?

**A. Yes — this is normal and intended.**

Startup Sync is a two-step design:

1. NTP removes large offsets (hundreds of ms to seconds)  
2. GNSS performs high-precision recalibration

NTP acts as a “coarse alignment,” and GNSS acts as the “final reference.”  
Seeing an NTP correction followed by a smaller GNSS correction is expected and generally indicates improving accuracy.

---

## Q8. Displayed times sometimes differ slightly. Is that an issue?

**A. No — this is due to display timing differences.**

System Time, GNSS Time, and NTP Time are updated on different schedules.  
Small differences (ms to tens of ms) may appear temporarily.

This does **not** indicate a synchronization error.

---

## Q9. What can I do without administrator privileges (Monitor-Only mode)?

**A. You can monitor and verify time without modifying the system clock.**

Monitor-Only mode allows:

- GNSS reception  
- satellite view  
- NTP queries  
- offset visualization  

No system time writes occur.  
This is a deliberate safety and transparency feature.

---

## Q10. The “⏰ Time adjusted” messages feel noisy. Should I disable them?

**A. The messages are intentional, but their frequency can be reduced.**

ChronoGPS makes visible:

- when a correction happened  
- how large it was  
- and that the resulting time is accurate

This is not noise — it is proof of correct behavior.

If you want fewer messages:

- keep **Instant Sync enabled** (corrections occur only when necessary), or  
- use **Weak Sync (Interval Sync)** for monitoring-focused operation

ChronoGPS is designed to **show what is happening**, not hide it.

---

## Q11. Windows SmartScreen or antivirus flags ChronoGPS.exe. Is it safe?

**A. Yes — this is a known false positive, not malicious behavior.**

ChronoGPS.exe is built using **PyInstaller**.  
Executables produced by PyInstaller are sometimes flagged by SmartScreen or antivirus products due to heuristic detection.

ChronoGPS contains **no**:

- self-replication
- stealth behavior
- intrusion attempts
- resident malware-like activity

All source code is public, and you can build the executable yourself for verification.

---

## Q12. Why do I see “Time is accurate” and still get adjustment logs? Isn’t that contradictory?

**A. Not contradictory — it’s normal Windows time granularity.**

Windows system time is internally quantized (typically **a few to tens of milliseconds**, depending on environment).  
So you can have:

- a very small effective error, while  
- display/rounding and sampling timing make small adjustments appear

ChronoGPS honestly reports both:

- that a correction occurred, and  
- the resulting effective error

“An adjustment happened” and “time is accurate now” can both be true.

---

## Q13. Can I run ChronoGPS alongside other time sync tools (Windows Time / Meinberg NTP, etc.)?

**A. Not recommended. Use only one active time authority.**

Running multiple sync tools can cause:

- competing corrections
- jitter injection
- unexpected back-and-forth adjustments

If you use ChronoGPS, it is recommended to disable or stop:

- Windows Time Service (w32time)
- resident NTP clients

ChronoGPS is designed to be a self-contained time reference tool.

---

## Q14. If FT8 decoding is poor, can causes other than time be responsible?

**A. Yes — many factors besides time affect decoding.**

ChronoGPS provides accurate time, but FT8 decoding is also affected by:

- CPU load
- audio device latency / buffering
- audio level settings
- radio frequency stability
- RF noise environment

If ChronoGPS shows:

- error within ±0.1 seconds, and  
- `Time is accurate`

then time is unlikely to be the root cause.

---

## Q15. Is ChronoGPS a “continuous correction” tool?

**A. No — and that is intentional.**

ChronoGPS is designed around:

- **Instant Sync** → calibrate and then maintain by monitoring GNSS; correct only when justified  
- **Weak Sync (Interval)** → monitor state and correct only as an exception

This respects:

- OS time model behavior
- avoidance of unnecessary writes
- explainable, reproducible logic

ChronoGPS is not a black-box tool that forces time every second.  
It is a tool that can explain **why the current time is what it is.**

---

## Q16. Why not adopt a “rewrite the system time every second” approach?

**A. Because it can make OS time less stable.**

GNSS reception always includes small jitter.  
If you rewrite the Windows system time every second, you may inject that jitter directly into OS time.

ChronoGPS prioritizes:

- respecting the OS time model
- avoiding unnecessary rewrites
- explainable, reproducible behavior

Therefore:

- Instant Sync maintains a calibrated state via monitoring and minimal corrections  
- Weak Sync monitors primarily, and corrects only when necessary

---

## Q17. If GNSS is available, why include NTP at all?

**A. To provide a reliable alternative when GNSS is not usable.**

GNSS is not always available:

- indoor operation
- no antenna installation
- receiver not connected
- temporary laptop operation

ChronoGPS treats:

- GNSS as the preferred absolute reference  
- NTP as a trustworthy fallback (RFC 5905-compliant)

For FT8 / FT4, NTP can still provide sufficient accuracy in many environments.

---

## Q18. Can ChronoGPS be used for measurement / verification purposes?

**A. Yes — as a reference/visualization tool, not as a lab instrument.**

ChronoGPS can visualize and log:

- offsets vs GNSS/NTP
- whether corrections occurred
- drift trends over time

However, it does not provide lab-instrument features such as:

- PPS input
- hardware timestamping
- guaranteed nanosecond accuracy

It is designed to help you understand  
**how accurate your PC time currently is** and how it behaves.

---

## Q19. Are logs available for later analysis?

**A. Yes — ChronoGPS outputs detailed logs suitable for analysis.**

Logs include:

- sync source (GNSS / NTP)
- correction amounts
- decision outcomes (skipped / adjusted / accurate)
- timestamps

This makes it easy to:

- validate behavior
- troubleshoot issues
- explain results to others
- reuse in README / Issues / Q&A

(You can copy/save the logs externally as needed.)

---

## Q20. What is the single biggest feature of ChronoGPS?

**A. It can explain “why the time is this time.”**

ChronoGPS is not designed to:

- blindly force time
- hide corrections
- run as a black box

Instead, it is designed to be explainable:

- why a correction occurred
- why it was skipped
- why the displayed error looks the way it does

ChronoGPS prioritizes not just “accuracy,”  
but **understandable accuracy**.

---

## Q21. I want ChronoGPS to start elevated (Sync mode) automatically, without clicking Unlock every time

**A. You can use Windows Task Scheduler. (Advanced / Optional)**

ChronoGPS itself maintains its design principle: it never elevates silently without explicit user action.  
However, by registering ChronoGPS in Windows Task Scheduler with "Run with highest privileges," you can have it launch automatically with administrator rights at logon.

> ⚠️ This is optional. It may not be available on managed/work PCs where administrator policies restrict it.  
> Also, make sure to **disable** ChronoGPS's built-in "Start with Windows" option to avoid double-launch conflicts.

### Setup Steps

**1. Open Task Scheduler**
- Start → search "Task Scheduler", or press `Win+R` → type `taskschd.msc`

**2. Select "Create Task" (not "Create Basic Task")**
- In the right-hand Actions panel → click ［Create Task］

**3. ［General］ tab**
- Name: e.g. `ChronoGPS (Admin AutoStart)`
- Select "Run only when user is logged on"
- ✅ Check **"Run with highest privileges"** ← most important

**4. ［Triggers］ tab**
- Click ［New…］→ Begin the task: "At log on"
- Specific user: your account
- (Optional) Delay: 30 seconds (can help on slow-to-boot PCs)

**5. ［Actions］ tab**
- Click ［New…］→ Action: "Start a program"
- Program/script: full path to `ChronoGPS.exe` (e.g. `C:\Tools\ChronoGPS\ChronoGPS.exe`)
- Arguments (optional): `--mode=sync`

**6. ［Conditions］ tab**
- On laptops: uncheck "Start the task only if the computer is on AC power" if needed

**7. ［Settings］ tab (recommended)**
- ✅ "Allow task to be run on demand"
- "If the task is already running" → select "Do not start a new instance"

**8. Save and verify**
- Click OK to save, then right-click the task → ［Run］ to test
- Confirm it launches automatically on next logon

### Troubleshooting
- Make sure the path points to the `.exe` file itself, not a shortcut
- Confirm "Run with highest privileges" is checked
- If ChronoGPS's built-in "Start with Windows" is still ON, a double-launch may be blocked by the Mutex — disable it
