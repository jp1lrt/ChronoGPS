# FAQ (Frequently Asked Questions)

## Q1. I see “⏰ Time adjusted” very frequently. Is something wrong?

**A. No — this is normal behavior.**

ChronoGPS uses **GNSS (GPS / QZSS, etc.)** as a high-precision time reference directly tied to UTC.  
By contrast, the Windows system clock has an internal **time resolution / quantization** of roughly **10–15 ms**.  
When compared against a precise GNSS reference, small differences will be detected continuously.

ChronoGPS does not hide this — it detects it and applies corrections when needed.

Typical correction amounts you may see in the log, such as:

- ±0.011s  
- ±0.013s  
- ±0.07–0.08s  

are within the normal range of Windows quantization and natural drift.

After each correction, ChronoGPS reports:

- `✓ Time is accurate (error: 0.000–0.009s)`

For FT8 / FT4 (typically ±1 second tolerance), this provides **more than two orders of magnitude of margin**.

This does **not** mean the time is unstable — it means  
**small behavior that was previously invisible is now being made visible.**

---

## Q2. Why do I see repeated corrections even when using Instant Sync?

**A. Because Instant Sync is not a “follow every second” mode.**

Instant Sync is designed to:

- use GNSS as a reference, and  
- **calibrate the Windows system clock once using a representative value**

It is **not** intended for continuous correction or second-by-second tracking.

However, if Instant Sync is left **ON continuously**, ChronoGPS will correct whenever it detects Windows-side quantization or natural drift.  
As a result:

- “Time adjusted” may appear continuously  
- while the effective error remains < 0.01 seconds

### Recommended usage

- **Everyday FT8 / FT4 operation**
  - After Instant Sync shows `Time is accurate`, you can turn the sync mode **OFF** and operate normally.

- **Long sessions / drift monitoring / verification**
  - Use **Weak Sync (Interval Sync)**.

Instant Sync is not “always pull the clock” —  
it is a feature to **create a correctly calibrated state**.

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

**monitoring first, correction only as an exception.**

---

## Q4. I see one-direction drift like `-0.03s → -0.05s`. Is that a problem?

**A. No — this is typically normal.**

In many cases, this represents:

- natural drift of the PC system clock

If you correct every tiny change, you may end up injecting small GNSS jitter into Windows time.  
ChronoGPS therefore uses a conservative, explainable policy:

- within threshold → **do nothing on purpose**  
- beyond threshold → **correct only when necessary**

---

## Q5. Which mode should I use for FT8 / FT4?

**A. For normal operation, Instant Sync is recommended.**

- **Everyday FT8 / FT4**
  - → **Instant Sync**
  - One calibration before operation is usually sufficient.

- **Long sessions / verification / monitoring**
  - → **Weak Sync (Interval Sync)**

GNSS is an extremely stable UTC reference.  
Once the system clock is properly calibrated, it typically exceeds FT8 / FT4 requirements by a wide margin.

ChronoGPS is not “always keep forcing time” —  
it is a tool to **create a correct state and avoid breaking it.**

---

## Q6. Should I use NTP Sync or GNSS (GPS) Sync?

**A. If possible, GNSS (GPS/QZSS) Sync is recommended.**

ChronoGPS treats GNSS as a first-class time source:

- **GNSS**
  - UTC-based absolute time
  - not affected by network delay
  - ideal for FT8 and measurement use

- **NTP**
  - depends on network quality
  - affected by routing / congestion / latency
  - useful when GNSS is unavailable

ChronoGPS implements NTP according to RFC 5905 and calculates offset/delay via t1/t2/t3/t4,  
but **GNSS is inherently more stable** as a time reference.

Recommended use:

- GNSS receiver available → **GNSS**
- GNSS unavailable → **NTP**

---

## Q7. Is it OK that ChronoGPS runs NTP sync at startup and then GNSS sync afterward?

**A. Yes — this is normal and intended.**

Startup Sync is a two-step design:

1. use NTP to remove large offsets (hundreds of ms to seconds)  
2. use GNSS to re-calibrate with high precision

NTP acts as a “coarse adjustment” and GNSS becomes the final reference.

So logs like:

- NTP correction: ±0.x seconds  
- then GNSS correction: ±0.03–0.08 seconds  

are not errors — they are evidence that the final precision is improving.

---

## Q8. The displayed times sometimes look slightly different (System vs GNSS vs NTP). Is that an issue?

**A. No — this is due to display timing differences.**

ChronoGPS displays:

- System Time  
- GNSS Time  
- NTP Time  

Each is acquired and refreshed on different schedules, so you may briefly see:

- a few ms to a few tens of ms difference

This is a **display artifact**, not a synchronization error.  
The internal sync logic still maintains millisecond-level accuracy.

---

## Q9. What can I do without administrator privileges (Monitor-Only mode)?

**A. You can monitor and verify time — without modifying the system clock.**

In non-admin mode, ChronoGPS can:

- receive GNSS data  
- show satellite view  
- query NTP time  
- display offsets vs system time

But it will **not** write the Windows system time.

This is not just a limitation — it is a safety and transparency feature.

Monitor-Only mode is ideal for:

- checking reception quality  
- observing drift trends  
- collecting logs for verification

---

## Q10. The “⏰ Time adjusted” messages feel noisy. Should I disable them?

**A. You can reduce them — but the messages are shown intentionally.**

ChronoGPS intentionally makes the following visible:

- when a correction happened  
- how large it was  
- and that the result is accurate

This is not “noisy logging” — it is proof the system is behaving as designed.

If you want fewer messages:

- use Instant Sync until `Time is accurate`, then turn sync mode **OFF**, or  
- use Weak Sync (Interval Sync), which skips corrections within threshold

ChronoGPS is not designed to “look like nothing is happening.”  
It is designed to **tell you exactly what is happening.**

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

All source code is public, and you can build the exe yourself for verification.

---

## Q12. Why do I see “Time is accurate” and still get adjustment logs? Isn’t that contradictory?

**A. Not contradictory — it’s normal Windows time quantization.**

Windows system time is internally quantized (roughly **~10 ms** steps).  
So you can have:

- sub-millisecond effective accuracy, while  
- display/rounding results make small corrections appear

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

- **Instant Sync** → calibrate once accurately  
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

- Instant Sync calibrates once using a representative value  
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
