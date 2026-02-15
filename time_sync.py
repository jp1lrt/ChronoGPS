"""
時刻同期機能（FT8オフセット0.1秒刻み対応版・多言語対応）
"""
import ctypes
from datetime import datetime, timedelta, timezone

class SYSTEMTIME(ctypes.Structure):
    _fields_ = [
        ('wYear', ctypes.c_uint16),
        ('wMonth', ctypes.c_uint16),
        ('wDayOfWeek', ctypes.c_uint16),
        ('wDay', ctypes.c_uint16),
        ('wHour', ctypes.c_uint16),
        ('wMinute', ctypes.c_uint16),
        ('wSecond', ctypes.c_uint16),
        ('wMilliseconds', ctypes.c_uint16),
    ]

class TimeSynchronizer:
    def __init__(self, localization=None):
        # 管理者判定（Windows API）
        try:
            self.is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            self.is_admin = False
        self.time_offset = 0.0  # FT8時刻オフセット（秒）
        self.loc = localization  # 多言語対応

    def sync_time(self, target_time):
        """システム時刻を同期（target_time を UTC として扱う）"""
        if not self.is_admin:
            if self.loc:
                return False, self.loc.get('admin_required')
            return False, "管理者権限が必要です"

        try:
            # target_time を UTC に正規化（tz-aware なら変換、naive なら UTC とみなす）
            if target_time.tzinfo is None:
                target_utc = target_time.replace(tzinfo=timezone.utc)
            else:
                target_utc = target_time.astimezone(timezone.utc)

            # FT8オフセット適用
            adjusted_time = target_utc + timedelta(seconds=self.time_offset)

            # 現在のシステム時刻（UTC）
            system_time = datetime.now(timezone.utc)
            diff = (adjusted_time - system_time).total_seconds()

            # 時刻設定（SYSTEMTIME は UTC を期待）
            st = self._datetime_to_systemtime(adjusted_time)
            result = ctypes.windll.kernel32.SetSystemTime(ctypes.byref(st))

            if result == 0:
                if self.loc:
                    return False, self.loc.get('sync_failed_settime')
                return False, "SetSystemTime failed"

            # 差分メッセージ
            if self.loc:
                if abs(diff) > 1.0:
                    msg = self.loc.get('sync_time_major')
                    return True, f"{msg} ({diff:+.3f}s)"
                elif abs(diff) > 0.01:
                    msg = self.loc.get('sync_time_adjusted')
                    return True, f"{msg} ({diff:+.3f}s)"
                else:
                    msg = self.loc.get('sync_time_accurate').format(error=abs(diff))
                    return True, msg
            else:
                if abs(diff) > 1.0:
                    return True, f"時刻を大幅修正しました ({diff:+.3f}秒)"
                elif abs(diff) > 0.01:
                    return True, f"時刻を微調整しました ({diff:+.3f}秒)"
                else:
                    return True, f"時刻は正確です (誤差: {abs(diff):.3f}秒)"

        except Exception as e:
            return False, str(e)

    def apply_offset(self, offset_seconds):
        """FT8時刻オフセットを適用（0.1秒刻み）"""
        if not self.is_admin:
            if self.loc:
                return False, self.loc.get('admin_required')
            return False, "管理者権限が必要です"

        try:
            # 現在時刻（UTC）を取得
            current_time = datetime.now(timezone.utc)

            # オフセット適用した時刻（UTC）
            adjusted_time = current_time + timedelta(seconds=offset_seconds)

            # システム時刻を設定
            st = self._datetime_to_systemtime(adjusted_time)
            result = ctypes.windll.kernel32.SetSystemTime(ctypes.byref(st))

            if result == 0:
                if self.loc:
                    return False, self.loc.get('sync_failed_settime')
                return False, "SetSystemTime failed"

            # オフセット累積（内部状態）
            self.time_offset += offset_seconds

            if self.loc:
                msg = self.loc.get('sync_time_adjusted')
                return True, f"{msg} ({offset_seconds:+.1f}s)"
            return True, f"時刻を調整しました ({offset_seconds:+.1f}秒)"

        except Exception as e:
            return False, str(e)

    def get_offset(self):
        """現在のオフセット値を取得"""
        return self.time_offset

    def set_offset(self, offset_seconds):
        """オフセット値を設定（時刻は変更しない）"""
        self.time_offset = offset_seconds

    def reset_offset(self):
        """オフセットをリセット"""
        self.time_offset = 0.0

    def _datetime_to_systemtime(self, dt):
        """datetime を SYSTEMTIME に変換（必ず UTC、wDayOfWeek を Windows 仕様に合わせる）"""
        # dt を UTC に正規化
        if dt.tzinfo is None:
            dt_utc = dt.replace(tzinfo=timezone.utc)
        else:
            dt_utc = dt.astimezone(timezone.utc)

        # Python: isoweekday() => Mon=1 .. Sun=7
        # Windows SYSTEMTIME.wDayOfWeek: Sun=0 .. Sat=6
        wday = dt_utc.isoweekday() % 7  # Sun -> 0

        return SYSTEMTIME(
            dt_utc.year,
            dt_utc.month,
            wday,
            dt_utc.day,
            dt_utc.hour,
            dt_utc.minute,
            dt_utc.second,
            dt_utc.microsecond // 1000
        )