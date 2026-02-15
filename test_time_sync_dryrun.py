# Dry-run test for TimeSynchronizer.sync_time / apply_offset
# This replaces kernel32.SetSystemTime with a fake that returns success (1)
# so the system time is NOT actually changed.

import ctypes
from datetime import datetime, timezone, timedelta
from time_sync import TimeSynchronizer, SYSTEMTIME

# save original
kernel32 = ctypes.windll.kernel32
orig_set = kernel32.SetSystemTime

# create a fake SetSystemTime that accepts SYSTEMTIME* and returns non-zero
CF = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.POINTER(SYSTEMTIME))
def _fake_set(st_ptr):
    # optional: inspect st_ptr contents for confirmation
    st = st_ptr.contents
    print("fake SetSystemTime called with:", 
          f"Y={st.wYear} M={st.wMonth} DOW={st.wDayOfWeek} D={st.wDay}",
          f"H={st.wHour} m={st.wMinute} s={st.wSecond} ms={st.wMilliseconds}")
    return 1
fake_c = CF(_fake_set)

try:
    # patch
    kernel32.SetSystemTime = fake_c

    ts = TimeSynchronizer()
    print("is_admin:", ts.is_admin)

    # Test sync_time: target = now + 3s
    target = datetime.now(timezone.utc) + timedelta(seconds=3)
    ok, msg = ts.sync_time(target)
    print("sync_time:", ok, msg)

    # Test apply_offset: +0.1s then +0.5s
    ok2, msg2 = ts.apply_offset(0.1)
    print("apply_offset 0.1s:", ok2, msg2)
    ok3, msg3 = ts.apply_offset(0.5)
    print("apply_offset 0.5s:", ok3, msg3)

    # Check get_offset
    print("get_offset:", ts.get_offset())

finally:
    # restore original to be safe
    try:
        kernel32.SetSystemTime = orig_set
    except Exception:
        pass

print("dry-run finished")