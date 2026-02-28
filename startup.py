# startup.py
# =============================================================================
# ChronoGPS v2.5 (Phase 1) - Startup orchestration
#
# 【目的 / Why】
# - v2.5の合意スコープ「案2：監視起動 + 昇格再起動」の“入口”を統一する。
# - 具体的には：
#   1) 引数解析（--mode, --elevated, --handoff）
#   2) 起動モード決定（既定は monitor）
#   3) Windows Mutex で二重起動を制御（ゾンビ/二重起動事故の土台）
#
# 【設計の要点】
# - monitor→syncへ昇格再起動する際、旧プロセス(monitor)が終了するまでの短時間、
#   新プロセス(sync)を起動できないと手渡しが成立しない。
#   → “単一グローバルMutex”は不適切（手渡し時に必ず衝突してしまう）
#   → “mode別Mutex + handoff例外” が最も堅実。
#
# - 通常起動では「別モードが動いていたら起動しない」ことで、
#   ユーザーが誤ってmonitor/syncを同時に立ち上げる混乱を防ぐ。
#   ただし handoff（昇格再起動）時だけは短時間の並走を許可する。
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional
import argparse
import ctypes
import logging

logger = logging.getLogger(__name__)

Mode = Literal["monitor", "sync"]


# --- Windows Mutex (ctypes) ---------------------------------------------------
# NOTE:
# - CreateMutexW() returns a handle even if already exists.
# - GetLastError() == ERROR_ALREADY_EXISTS means "another instance already created it".
# - We must CloseHandle() to avoid handle leak.
#
# This is intentionally small and dependency-free (no pywin32 required).

_KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)
_CreateMutexW = _KERNEL32.CreateMutexW
_CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
_CreateMutexW.restype = ctypes.c_void_p

_OpenMutexW = _KERNEL32.OpenMutexW
_OpenMutexW.argtypes = [ctypes.c_uint32, ctypes.c_bool, ctypes.c_wchar_p]
_OpenMutexW.restype = ctypes.c_void_p

_CloseHandle = _KERNEL32.CloseHandle
_CloseHandle.argtypes = [ctypes.c_void_p]
_CloseHandle.restype = ctypes.c_bool

_GetLastError = _KERNEL32.GetLastError
_GetLastError.argtypes = []
_GetLastError.restype = ctypes.c_uint32

ERROR_ALREADY_EXISTS = 183
MUTEX_ALL_ACCESS = 0x1F0001  # sufficient for OpenMutex checks


class WindowsMutex:
    """
    Named mutex wrapper for single-instance checks.

    We use "CreateMutexW" so that:
      - If it doesn't exist -> created and owned by this process
      - If it exists -> still returns a handle, and GetLastError=ERROR_ALREADY_EXISTS

    This class does not "WaitForSingleObject" because we only need existence checks
    for single-instance gating and "elevated instance detected" confirmation.
    """

    def __init__(self, name: str):
        self.name = name
        self.handle: Optional[int] = None
        self.already_exists: bool = False

    def create(self) -> None:
        handle = _CreateMutexW(None, False, self.name)
        if not handle:
            raise OSError(ctypes.get_last_error(), f"CreateMutexW failed: {self.name}")
        self.handle = int(handle)
        self.already_exists = (_GetLastError() == ERROR_ALREADY_EXISTS)

    def close(self) -> None:
        if self.handle:
            _CloseHandle(ctypes.c_void_p(self.handle))
            self.handle = None

    @staticmethod
    def exists(name: str) -> bool:
        h = _OpenMutexW(MUTEX_ALL_ACCESS, False, name)
        if h:
            _CloseHandle(h)
            return True
        return False


# --- Startup Context ----------------------------------------------------------

@dataclass(frozen=True)
class StartupContext:
    """
    startup.py の出力（main/guiへ渡す“起動の事実”）

    mode:
      - "monitor": 非管理者で成立する監視起動（v2.5の既定）
      - "sync":    同期UIにフォーカス。管理者での時刻反映が目的

    elevated_arg:
      - 引数として --elevated が来ているか（再起動ループ防止の材料）
      - 実際に管理者かどうかは admin.check_admin() 側で判定する（Step2で実装）

    handoff:
      - monitor→sync の「昇格再起動」用途かどうか
      - handoff=True のときだけ短時間の並走を許容する
    """
    mode: Mode
    elevated_arg: bool
    handoff: bool
    mutex_name: str
    other_mode_running: bool
    should_exit: bool
    exit_reason: str


# --- Public API ---------------------------------------------------------------

def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    """
    引数解析（v2.5追加）
    - --mode: 起動目的（sync/monitor）
    - --elevated: 昇格再起動後の識別（無限ループ防止）
    - --handoff: monitor→sync への“手渡し”であることを示す（短時間並走を許可）
    """
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--mode", choices=["monitor", "sync"], default=None)
    p.add_argument("--elevated", action="store_true")
    p.add_argument("--handoff", action="store_true")
    # 既存コードが独自引数を持つ可能性があるので、未知引数は残す方針にする。
    # ここでは parse_known_args を使い、残りは呼び出し側で必要に応じて処理できる。
    ns, _unknown = p.parse_known_args(argv)
    return ns


def build_mutex_name(mode: Mode) -> str:
    # NOTE: 名前は将来変えない（互換性維持）。衝突しにくいよう prefix を固定。
    return f"ChronoGPS-{mode}"


def decide_mode(ns: argparse.Namespace) -> Mode:
    """
    v2.5の既定は monitor。
    （Phase1の段階導入として、まず“監視起動が正常”を土台にする）
    """
    if ns.mode in ("monitor", "sync"):
        return ns.mode
    return "monitor"


def init_startup(argv: Optional[list[str]] = None) -> StartupContext:
    """
    起動時に必ず最初に呼ぶ想定の関数。
    - mode決定
    - Mutex取得
    - 二重起動 / 他モード起動 の抑止判定
    """
    ns = parse_args(argv)
    mode = decide_mode(ns)
    elevated_arg = bool(ns.elevated)
    handoff = bool(ns.handoff)

    mutex_name = build_mutex_name(mode)
    other_mode: Mode = "sync" if mode == "monitor" else "monitor"
    other_mutex_name = build_mutex_name(other_mode)

    # まず自分のmode mutexを作る
    m = WindowsMutex(mutex_name)
    m.create()

    # すでに同modeが動いているなら終了（明確な二重起動）
    if m.already_exists:
        m.close()
        return StartupContext(
            mode=mode,
            elevated_arg=elevated_arg,
            handoff=handoff,
            mutex_name=mutex_name,
            other_mode_running=WindowsMutex.exists(other_mutex_name),
            should_exit=True,
            exit_reason=f"Another instance is already running (mode={mode}).",
        )

    # 他モードが動いている場合：
    # - 通常起動は混乱を避けるため終了
    # - handoff=True の場合は短時間の並走を許可（monitor→sync起動ができなくなるのを防ぐ）
    other_running = WindowsMutex.exists(other_mutex_name)
    if other_running and not handoff:
        # 自分を落とす（既存を残す）
        m.close()
        return StartupContext(
            mode=mode,
            elevated_arg=elevated_arg,
            handoff=handoff,
            mutex_name=mutex_name,
            other_mode_running=True,
            should_exit=True,
            exit_reason=f"Other mode instance is running (mode={other_mode}).",
        )

    # 正常起動
    # NOTE: ここで close() すると mutex が解放されて意味が無いので、
    #       呼び出し側（main）がプロセス終了まで保持する。
    #       → 返り値に mutex_name を含め、必要なら shutdown 時に close できるよう Step3で設計する。
    logger.debug("Startup init ok: mode=%s elevated_arg=%s handoff=%s", mode, elevated_arg, handoff)

    return StartupContext(
        mode=mode,
        elevated_arg=elevated_arg,
        handoff=handoff,
        mutex_name=mutex_name,
        other_mode_running=other_running,
        should_exit=False,
        exit_reason="",
    )