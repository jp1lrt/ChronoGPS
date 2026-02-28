# admin.py
# =============================================================================
# ChronoGPS v2.5 (Phase 1) - Admin / Elevation utilities
#
# 【目的 / Why】
# - v2.5「案2：監視起動 + 昇格再起動」を Windows 的に正しく実現する。
# - Windowsでは起動後に同一プロセスが昇格できないため、
#   必要なときだけ "runas" で管理者プロセスを別途起動する。
#
# 【このファイルの責務 / Responsibilities】
# 1) check_admin(): 実際に管理者権限で動いているか判定
# 2) launch_elevated(): runas で自分自身を再起動（管理者）
# 3) wait_for_elevated_instance(): 昇格プロセスが実際に起動した “確証” を待つ
#    → v2.5では Windows Mutex（startup.py）を確証シグナルとして利用
#
# 【重要】
# - UACがキャンセルされた場合、旧プロセス（監視）は終了してはいけない。
#   → "確証（ChronoGPS-sync Mutex出現）" を待ってから旧を終了する。
# =============================================================================

from __future__ import annotations

import logging
import os
import sys
import time
import ctypes
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

from startup import WindowsMutex, build_mutex_name  # Step1で固定したMutex名を利用

logger = logging.getLogger(__name__)


# --- Win32: admin check / ShellExecuteW --------------------------------------

_SHELL32 = ctypes.WinDLL("shell32", use_last_error=True)
_IsUserAnAdmin = _SHELL32.IsUserAnAdmin
_IsUserAnAdmin.argtypes = []
_IsUserAnAdmin.restype = ctypes.c_bool

_ShellExecuteW = _SHELL32.ShellExecuteW
_ShellExecuteW.argtypes = [
    ctypes.c_void_p,  # hwnd
    ctypes.c_wchar_p, # lpOperation
    ctypes.c_wchar_p, # lpFile
    ctypes.c_wchar_p, # lpParameters
    ctypes.c_wchar_p, # lpDirectory
    ctypes.c_int,     # nShowCmd
]
_ShellExecuteW.restype = ctypes.c_void_p  # HINSTANCE


@dataclass(frozen=True)
class ElevationResult:
    """
    runas起動の結果を呼び出し側に返すためのデータクラス。
    """
    launched: bool
    waited_confirmed: bool
    reason: str
    shell_execute_code: int
    timeout_sec: float


def check_admin() -> bool:
    """
    実際に管理者権限で動作しているか判定する。

    NOTE:
    - 引数の --elevated は “昇格再起動として起動された” 目印であって、
      実権限の保証ではない。実権限はこの関数で必ず判定する。
    """
    try:
        return bool(_IsUserAnAdmin())
    except Exception:
        # IsUserAnAdminが失敗するケースは稀だが、安全側に倒して False。
        logger.exception("check_admin() failed; assume not admin.")
        return False


# --- Command line construction ------------------------------------------------

def _quote_arg(arg: str) -> str:
    """
    ShellExecuteWに渡す parameter 文字列用の簡易クォート。
    既存の " はエスケープしておく。
    """
    if arg == "":
        return '""'
    arg = arg.replace('"', '\\"')
    if any(ch in arg for ch in (" ", "\t", "\n")):
        return f'"{arg}"'
    return arg


def _build_relaunch_command(extra_args: Sequence[str]) -> Tuple[str, str, str]:
    """
    自分自身を再起動するための (exe, params, cwd) を返す。

    PyInstaller exe の場合：
      - exe = sys.executable (ChronoGPS.exe)
      - params = extra_args を連結

    python実行（開発）場合：
      - exe = sys.executable (python.exe)
      - params = <script_path> + extra_args

    IMPORTANT:
    - main.py を直接呼ぶのではなく、"現在起動しているエントリ" を再現する。
    - sys.argv[0] を script として扱うのが最も自然。
    """
    cwd = os.getcwd()

    if getattr(sys, "frozen", False):
        # PyInstaller / frozen binary
        exe = sys.executable
        params_list = list(extra_args)
    else:
        exe = sys.executable
        script = os.path.abspath(sys.argv[0])
        params_list = [script] + list(extra_args)

    params = " ".join(_quote_arg(a) for a in params_list)
    return exe, params, cwd


# --- Elevation (runas) --------------------------------------------------------

def launch_elevated(mode: str, *, handoff: bool = True, addl_args: Optional[Sequence[str]] = None) -> int:
    """
    runas で管理者プロセスを起動する（起動要求のみ）。
    戻り値は ShellExecuteW の返り値（成功なら > 32）。

    mode:
      - "sync" を想定（v2.5案2: unlockボタン→syncへ昇格）
      - "monitor" も理論上は可能だが、現時点では主用途ではない。

    handoff:
      - startup.py の「handoff=Trueなら他モード並走を許可」に合わせて、
        昇格起動時は基本 True とする。

    addl_args:
      - 将来的な拡張用。例：特定タブを開く、特定操作の自動開始など。
    """
    args = [f"--mode={mode}", "--elevated"]
    if handoff:
        args.append("--handoff")
    if addl_args:
        args.extend(list(addl_args))

    exe, params, cwd = _build_relaunch_command(args)

    logger.info(
        "UAC launch requested: exe=%s params=%s cwd=%s mode=%s handoff=%s",
        exe, params, cwd, mode, handoff
    )

    # ShellExecuteW: 성공なら戻り値 > 32
    # nShowCmd=1 (SW_SHOWNORMAL)
    hinst = _ShellExecuteW(None, "runas", exe, params, cwd, 1)
    code = int(ctypes.cast(hinst, ctypes.c_void_p).value or 0)
    return code


def wait_for_elevated_instance(mode: str, *, timeout_sec: float = 10.0, poll_sec: float = 0.10) -> bool:
    """
    “昇格インスタンスが起動した確証”を待つ。

    v2.5では、確証として Windows Mutex の存在を使う：
      - ChronoGPS-sync の mutex が作成されている → syncインスタンスが起動した

    UACキャンセル時は mutex が現れないので False を返す。
    """
    mutex_name = build_mutex_name(mode)  # ChronoGPS-sync / ChronoGPS-monitor
    deadline = time.monotonic() + timeout_sec

    while time.monotonic() < deadline:
        if WindowsMutex.exists(mutex_name):
            logger.info("Elevated instance detected via mutex: %s", mutex_name)
            return True
        time.sleep(poll_sec)

    logger.warning("Timeout waiting elevated instance mutex: %s (%.1fs)", mutex_name, timeout_sec)
    return False


def launch_elevated_and_confirm(
    mode: str = "sync",
    *,
    handoff: bool = True,
    timeout_sec: float = 10.0,
    poll_sec: float = 0.10,
    addl_args: Optional[Sequence[str]] = None,
) -> ElevationResult:
    """
    runas起動 → 確証待ち を一括で行うヘルパー。
    GUI側の on_unlock_sync() は原則これを呼び、結果に応じて
    - confirmedなら shutdown へ
    - not confirmedなら 監視継続
    という分岐にする。

    Returns:
      ElevationResult
    """
    shell_code = launch_elevated(mode, handoff=handoff, addl_args=addl_args)

    if shell_code <= 32:
        # UACキャンセルや起動失敗など
        reason = f"ShellExecuteW failed or cancelled (code={shell_code})."
        logger.warning(reason)
        return ElevationResult(
            launched=False,
            waited_confirmed=False,
            reason=reason,
            shell_execute_code=shell_code,
            timeout_sec=timeout_sec,
        )

    # 起動要求は成功した。次に “実際に起動した”確証を待つ。
    confirmed = wait_for_elevated_instance(mode, timeout_sec=timeout_sec, poll_sec=poll_sec)

    if confirmed:
        reason = "Elevated instance confirmed."
    else:
        reason = "Elevated instance not confirmed (timeout or cancelled)."

    return ElevationResult(
        launched=True,
        waited_confirmed=confirmed,
        reason=reason,
        shell_execute_code=shell_code,
        timeout_sec=timeout_sec,
    )