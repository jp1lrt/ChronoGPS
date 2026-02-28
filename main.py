"""
ChronoGPS — GPS/NTP 時刻同期ツール
メインアプリケーション

Author: 津久浦 慶治 / Yoshiharu Tsukuura  callsign JP1LRT (@jp1lrt)
License: MIT
"""
from __future__ import annotations

import logging
import os
import re
import sys
import tkinter as tk
from tkinter import messagebox

import startup  # v2.5: 引数解析 / mode決定 / Windows Mutex 取得


def get_base_dir() -> str:
    """実行ファイルの場所を返す（exe化・スクリプト両対応）"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _setup_logging() -> None:
    """v2.5: 起動切り分け用に最低限のログを確実に残す。"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _detect_ui_lang() -> str:
    """
    起動拒否ダイアログの言語を決める（最小実装）。
    - GUI本体は gui 側のLocalizationに任せる
    - main.py は “拒否ダイアログ” だけなので、OSロケールで十分
    """
    lang = (os.environ.get("LANG") or "").lower()
    if lang.startswith("ja"):
        return "ja"
    # Windowsでは LANG が無いこともあるので、Pythonのロケールから推定
    try:
        import locale

        loc = (locale.getdefaultlocale()[0] or "").lower()
        if loc.startswith("ja"):
            return "ja"
    except Exception:
        pass
    return "en"


def _localize_startup_rejection(exit_reason: str, *, lang: str) -> str:
    """
    startup.py の exit_reason（英語）を、拒否ダイアログ向けにローカライズする。
    v2.5 Fix: raw英語文字列がそのまま出ないようにする（A-2/A-4）。
    """
    if not exit_reason:
        return "ChronoGPS is already running." if lang == "en" else "ChronoGPS はすでに起動しています。"

    # 代表的な理由をパターン化してローカライズ
    m = re.search(r"\(mode=(monitor|sync)\)", exit_reason)
    mode = m.group(1) if m else None

    if exit_reason.startswith("Another instance is already running"):
        if lang == "en":
            return f"ChronoGPS is already running (mode={mode})." if mode else "ChronoGPS is already running."
        return "ChronoGPS はすでに起動しています。"  # モード詳細は不要

    if exit_reason.startswith("Other mode instance is running"):
        if lang == "en":
            return f"Other mode instance is running (mode={mode})." if mode else "Other mode instance is running."
        return "ChronoGPS の別モードがすでに起動しています。"  # 危険な同時起動を抑止

    # それ以外は言語に応じてそのまま（en） / ざっくり置換（ja）
    if lang == "en":
        return exit_reason
    # 日本語UIでは“理由の詳細”より分かりやすさを優先
    return "ChronoGPS を起動できませんでした（既に起動している可能性があります）。"


def main(argv: list[str]) -> int:
    _setup_logging()
    log = logging.getLogger("chronogps.main")

    # 作業ディレクトリを実行ファイルの場所に固定（既存挙動を維持）
    base_dir = get_base_dir()
    os.chdir(base_dir)

    # v2.5: startup 初期化（引数解析 / mode決定 / Mutexで多重起動・他モード起動を抑止）
    ctx = startup.init_startup(argv)

    # v2.5 Must: 起動時に必須情報をログへ
    log.info(
        "startup: mode=%s elevated_arg=%s handoff=%s mutex_name=%s other_mode_running=%s should_exit=%s exit_reason=%s",
        getattr(ctx, "mode", None),
        getattr(ctx, "elevated_arg", None),
        getattr(ctx, "handoff", None),
        getattr(ctx, "mutex_name", None),
        getattr(ctx, "other_mode_running", None),
        getattr(ctx, "should_exit", None),
        getattr(ctx, "exit_reason", None),
    )

    # 起動拒否（同mode二重起動 / 他mode起動中 など）
    if getattr(ctx, "should_exit", False):
        lang = _detect_ui_lang()
        title = "ChronoGPS"
        msg = _localize_startup_rejection(getattr(ctx, "exit_reason", ""), lang=lang)

        # 既存main.pyのUXに合わせて警告を出す（メインウィンドウは表示しない）
        root = tk.Tk()
        root.withdraw()
        if lang == "en":
            msg2 = f"{msg}\n\nPlease check the system tray."
        else:
            msg2 = f"{msg}\n\nタスクトレイを確認してください。"
        messagebox.showwarning(title, msg2)
        root.destroy()

        log.warning("Startup rejected: %s", getattr(ctx, "exit_reason", ""))
        return 2

    # admin.check_admin は GUI 側でも使うが、ここでログに残しておくと切り分けが速い
    is_admin = False
    try:
        import admin  # v2.5: Step2

        is_admin = bool(admin.check_admin())
    except Exception:
        is_admin = False
    log.info("runtime: is_admin=%s", is_admin)

    # GUI 起動（v2.5: startup_ctx を渡す）
    from gui import GPSTimeSyncGUI  # v2.5 release: import fixed


    root = tk.Tk()
    _app = GPSTimeSyncGUI(root, startup_ctx=ctx)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
