"""
時刻同期機能（FT8オフセット0.1秒刻み対応版・多言語対応）
- sync_time():        強同期（即時/手動向け）… 絶対設定
- sync_time_weak():   弱同期（定期向け）… 閾値＋中央値＋連続確認でジッタ注入を抑制
"""
import logging
import ctypes
from collections import deque
from statistics import median
from datetime import datetime, timedelta, timezone
from weak_sync_logic import decide_weak_sync


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

    def _normalize_target_utc(self, target_time):
        """target_time をUTCのtz-aware datetimeに正規化"""
        if target_time.tzinfo is None:
            return target_time.replace(tzinfo=timezone.utc)
        return target_time.astimezone(timezone.utc)

    def _set_system_time_utc(self, dt_utc):
        """UTCのdatetimeをWindowsへ絶対設定。成功で1、失敗で0を返す"""
        st = self._datetime_to_systemtime(dt_utc)
        return ctypes.windll.kernel32.SetSystemTime(ctypes.byref(st))

    def _loc_get(self, key, fallback):
        """ローカライズ文字列を取得。未設定またはNoneのとき fallback を返す"""
        if self.loc:
            val = self.loc.get(key)
            if val is not None:
                return val
        return fallback

    def sync_time(self, target_time):
        """システム時刻を同期（target_time を UTC として扱う）"""
        if not self.is_admin:
            return False, self._loc_get('admin_required', "管理者権限が必要です")

        try:
            target_utc = self._normalize_target_utc(target_time)

            # FT8オフセット適用
            adjusted_time = target_utc + timedelta(seconds=self.time_offset)

            # 現在のシステム時刻（UTC）との差分
            system_time = datetime.now(timezone.utc)
            diff = (adjusted_time - system_time).total_seconds()

            # 時刻設定
            if self._set_system_time_utc(adjusted_time) == 0:
                return False, self._loc_get('sync_failed_settime', "SetSystemTime failed")

            # 差分メッセージ
            if abs(diff) > 1.0:
                msg = self._loc_get('sync_time_major', "時刻を大幅修正しました")
                return True, f"{msg} ({diff:+.3f}s)"
            elif abs(diff) > 0.01:
                msg = self._loc_get('sync_time_adjusted', "時刻を微調整しました")
                return True, f"{msg} ({diff:+.3f}s)"
            else:
                # sync_time_accurate は {error} プレースホルダを含む想定
                fmt = self._loc_get('sync_time_accurate', "時刻は正確です (誤差: {error:.3f}秒)")
                return True, fmt.format(error=abs(diff))

        except Exception as e:
            return False, str(e)

    def add_sample(self, target_time):
        """
        サンプルをバッファに追加するだけ（SetSystemTimeは呼ばない）
        毎秒GPS受信のたびに呼び出すことで、統計精度を上げる。
        期限到達時に sync_time_weak(append_sample=False) を呼ぶことで二重追加を防ぐ。
        """
        try:
            target_utc = self._normalize_target_utc(target_time)
            adjusted_time = target_utc + timedelta(seconds=self.time_offset)
            system_time = datetime.now(timezone.utc)
            diff = (adjusted_time - system_time).total_seconds()
            self._weak_diffs.append(diff)
        except Exception as e:
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
            return False, self._loc_get('admin_required', "管理者権限が必要です")

        try:
            # パラメータ解決（None のときはインスタンス既定値を使用）
            th = self._weak_threshold if threshold is None else float(threshold)
            st_th = self._weak_strong_threshold if strong_threshold is None else float(strong_threshold)
            cn = self._weak_confirm_needed if confirm_needed is None else int(confirm_needed)

            if window is not None:
                w = max(1, int(window))
                if w != self._weak_diffs.maxlen:
                    self._weak_diffs = deque(maxlen=w)
                    self._weak_confirm_count = 0
                    self._weak_last_sign = 0

            target_utc = self._normalize_target_utc(target_time)
            adjusted_time = target_utc + timedelta(seconds=self.time_offset)
            system_time = datetime.now(timezone.utc)
            diff = (adjusted_time - system_time).total_seconds()

            # accumulate（add_sample()で追加済みの場合はスキップして二重追加を防ぐ）
            if append_sample:
                self._weak_diffs.append(diff)

            # サンプル収集フェーズ
            if len(self._weak_diffs) < self._weak_diffs.maxlen:
                msg = self._loc_get('sync_collecting_samples', "弱同期: サンプル収集中")
                return True, f"{msg} ({diff:+.3f}s)"

            decision = decide_weak_sync(
                diffs=list(self._weak_diffs),
                threshold=th,
                strong_threshold=st_th,
                confirm_needed=cn,
                last_sign=self._weak_last_sign,
                confirm_count=self._weak_confirm_count,
            )

            # 状態更新
            self._weak_confirm_count = decision.confirm_count
            self._weak_last_sign = decision.last_sign

            if decision.action == "collecting":
                # decide_weak_sync 側が collecting を返した場合の安全策
                msg = self._loc_get('sync_collecting_samples', "弱同期: サンプル収集中")
                return True, f"{msg} ({diff:+.3f}s)"

            if decision.action == "skip":
                msg = self._loc_get('sync_skipped_jitter', "誤差が閾値以内のため補正しませんでした")
                return True, f"{msg} ({decision.med:+.3f}s)"

            if decision.action == "pending":
                msg = self._loc_get('sync_pending_confirm', "弱同期: 安定確認中")
                return True, f"{msg} ({decision.med:+.3f}s)"

            # "strong_set" または "set": 時刻を絶対設定
            if self._set_system_time_utc(adjusted_time) == 0:
                return False, self._loc_get('sync_failed_settime', "SetSystemTime failed")

            if decision.action == "strong_set":
                msg = self._loc_get('sync_time_major', "時刻を大幅修正しました")
            else:
                msg = self._loc_get('sync_time_adjusted', "時刻を微調整しました")

            return True, f"{msg} ({decision.med:+.3f}s)"

        except Exception as e:
            return False, str(e)

    def apply_offset(self, offset_seconds):
        """FT8時刻オフセットを適用（0.1秒刻み）"""
        if not self.is_admin:
            return False, self._loc_get('admin_required', "管理者権限が必要です")

        try:
            current_time = datetime.now(timezone.utc)
            adjusted_time = current_time + timedelta(seconds=offset_seconds)

            if self._set_system_time_utc(adjusted_time) == 0:
                return False, self._loc_get('sync_failed_settime', "SetSystemTime failed")

            # オフセット累積（内部状態）
            self.time_offset += offset_seconds

            msg = self._loc_get('sync_time_adjusted', "時刻を調整しました")
            return True, f"{msg} ({offset_seconds:+.1f}s)"

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