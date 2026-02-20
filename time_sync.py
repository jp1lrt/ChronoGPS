"""
時刻同期機能（FT8オフセット0.1秒刻み対応版・多言語対応）
- sync_time():        強同期（即時/手動向け）… 絶対設定
- sync_time_weak():   弱同期（定期向け）… 閾値＋中央値＋連続確認でジッタ注入を抑制
"""
import ctypes
from collections import deque
from statistics import median
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

        # --- weak periodic sync state (for interval mode) ---
        # 直近diffの中央値で外れ値（瞬間ジッタ）に強くする
        self._weak_diffs = deque(maxlen=30)    # recent diffs (sec) - 30sec window
        self._weak_threshold = 0.2             # deadband threshold (sec)
        self._weak_strong_threshold = 1.0      # force set threshold (sec)
        self._weak_confirm_needed = 2          # consecutive confirmations
        self._weak_confirm_count = 0
        self._weak_last_sign = 0               # -1 / 0 / +1

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

    def _normalize_target_utc(self, target_time):
        """target_time をUTCのtz-aware datetimeに正規化"""
        if target_time.tzinfo is None:
            return target_time.replace(tzinfo=timezone.utc)
        return target_time.astimezone(timezone.utc)

    def _set_system_time_utc(self, dt_utc):
        """UTCのdatetimeをWindowsへ絶対設定"""
        st = self._datetime_to_systemtime(dt_utc)
        return ctypes.windll.kernel32.SetSystemTime(ctypes.byref(st))

    def add_sample(self, target_time):
        """
        サンプルをバッファに追加するだけ（SetSystemTimeは呼ばない）
        毎秒GPS受信のたびに呼び出すことで、統計精度を上げる。
        期限到達時に sync_time_weak(append_sample=False) を呼ぶことで二重追加を防ぐ。
        """
        try:
            if target_time.tzinfo is None:
                target_utc = target_time.replace(tzinfo=timezone.utc)
            else:
                target_utc = target_time.astimezone(timezone.utc)

            adjusted_time = target_utc + timedelta(seconds=self.time_offset)
            system_time = datetime.now(timezone.utc)
            diff = (adjusted_time - system_time).total_seconds()
            self._weak_diffs.append(diff)
        except Exception as e:
            # デバッグ用：通常運用では無視、問題発生時はここで捕捉可能
            import logging
            logging.debug(f"add_sample error: {e}")

    def sync_time_weak(
        self,
        target_time,
        threshold=None,
        window=None,
        strong_threshold=None,
        confirm_needed=None,
        append_sample=True
    ):
        """
        弱い同期（定期同期用）
        - GNSS受信の瞬間ジッタをOS時刻へ注入しないためのガードを入れる
        - abs(median(diff)) が threshold 未満なら何もしない（ジッタ扱い）
        - threshold を超える場合も confirm_needed 回連続で同方向を確認してから SetSystemTime
        - abs(median(diff)) が strong_threshold 以上なら即 SetSystemTime（安全策）

        diff の定義: diff = adjusted_time - system_time
          diff > 0: システムが遅れている（進める方向）
          diff < 0: システムが進んでいる（戻す方向）
        """
        if not self.is_admin:
            if self.loc:
                return False, self.loc.get('admin_required')
            return False, "管理者権限が必要です"

        try:
            # params
            th = self._weak_threshold if threshold is None else float(threshold)
            st_th = self._weak_strong_threshold if strong_threshold is None else float(strong_threshold)
            cn = self._weak_confirm_needed if confirm_needed is None else int(confirm_needed)

            if window is not None:
                w = int(window)
                if w <= 0:
                    w = 1
                if w != self._weak_diffs.maxlen:
                    self._weak_diffs = deque(maxlen=w)
                    self._weak_confirm_count = 0
                    self._weak_last_sign = 0

            # target_time を UTC に正規化
            if target_time.tzinfo is None:
                target_utc = target_time.replace(tzinfo=timezone.utc)
            else:
                target_utc = target_time.astimezone(timezone.utc)

            # FT8オフセット適用
            adjusted_time = target_utc + timedelta(seconds=self.time_offset)

            # 現在のシステム時刻（UTC）
            system_time = datetime.now(timezone.utc)
            diff = (adjusted_time - system_time).total_seconds()

            # accumulate（add_sample()で追加済みの場合はスキップして二重追加を防ぐ）
            if append_sample:
                self._weak_diffs.append(diff)

            # sample collecting phase
            if len(self._weak_diffs) < self._weak_diffs.maxlen:
                if self.loc:
                    msg = self.loc.get('sync_collecting_samples') or "Weak sync: collecting samples"
                else:
                    msg = "弱同期: サンプル収集中"
                return True, f"{msg} ({diff:+.3f}s)"

            med = float(median(self._weak_diffs))

            # deadband: do nothing
            if abs(med) < th:
                self._weak_confirm_count = 0
                self._weak_last_sign = 0
                if self.loc:
                    msg = self.loc.get('sync_skipped_jitter') or "Weak sync: skipped (within threshold)"
                else:
                    msg = "誤差が閾値以内のため補正しませんでした"
                return True, f"{msg} ({med:+.3f}s)"

            # strong: force set immediately
            if abs(med) >= st_th:
                st = self._datetime_to_systemtime(adjusted_time)
                result = ctypes.windll.kernel32.SetSystemTime(ctypes.byref(st))
                if result == 0:
                    if self.loc:
                        return False, self.loc.get('sync_failed_settime')
                    return False, "SetSystemTime failed"

                if self.loc:
                    msg = self.loc.get('sync_time_major') or "Time corrected (major)"
                else:
                    msg = "時刻を大幅修正しました"

                self._weak_confirm_count = 0
                self._weak_last_sign = 0
                return True, f"{msg} ({med:+.3f}s)"

            # confirm-stability: require consecutive same-direction median
            sign = 1 if med > 0 else -1
            if sign == self._weak_last_sign:
                self._weak_confirm_count += 1
            else:
                self._weak_last_sign = sign
                self._weak_confirm_count = 1

            if self._weak_confirm_count < cn:
                if self.loc:
                    msg = self.loc.get('sync_pending_confirm') or "Weak sync: confirming stability"
                else:
                    msg = "弱同期: 安定確認中"
                return True, f"{msg} ({med:+.3f}s)"

            # confirmed: apply absolute set
            st = self._datetime_to_systemtime(adjusted_time)
            result = ctypes.windll.kernel32.SetSystemTime(ctypes.byref(st))
            if result == 0:
                if self.loc:
                    return False, self.loc.get('sync_failed_settime')
                return False, "SetSystemTime failed"

            # reset confirm after action
            self._weak_confirm_count = 0
            self._weak_last_sign = 0

            if self.loc:
                msg = self.loc.get('sync_time_adjusted') or "Time adjusted"
            else:
                msg = "時刻を微調整しました"
            return True, f"{msg} ({med:+.3f}s)"

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
