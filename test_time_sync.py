from time_sync import TimeSynchronizer
from datetime import datetime, timezone, timedelta

ts = TimeSynchronizer()
print("is_admin:", ts.is_admin)

# 現在 UTC 時刻と数秒後を用意して SYSTEMTIME に変換して表示
for sec in (0, 2, -5):
    dt = datetime.now(timezone.utc) + timedelta(seconds=sec)
    st = ts._datetime_to_systemtime(dt)
    print(f"\ninput utc: {dt.isoformat()}")
    print("SYSTEMTIME ->",
          f"Year={st.wYear}, Month={st.wMonth}, DayOfWeek={st.wDayOfWeek}, Day={st.wDay},",
          f"Hour={st.wHour}, Min={st.wMinute}, Sec={st.wSecond}, MS={st.wMilliseconds}")