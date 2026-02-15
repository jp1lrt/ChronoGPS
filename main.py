"""メインアプリケーション"""
import sys
import os
import tkinter as tk
from tkinter import messagebox

def get_base_dir():
    """実行ファイルの場所を返す（exe化・スクリプト両対応）"""
    if getattr(sys, 'frozen', False):
        # PyInstallerでexe化された場合
        return os.path.dirname(sys.executable)
    else:
        # スクリプト実行の場合
        return os.path.dirname(os.path.abspath(__file__))

def is_already_running():
    """多重起動チェック（Windows Mutex使用）"""
    try:
        import ctypes
        mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "ChronoGPS_SingleInstance")
        return ctypes.windll.kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS
    except Exception:
        return False  # Windows以外では無視

def main():
    # 多重起動チェック
    if is_already_running():
        root = tk.Tk()
        root.withdraw()  # メインウィンドウは表示しない
        messagebox.showwarning(
            "ChronoGPS",
            "ChronoGPS はすでに起動しています。\nタスクトレイを確認してください。"
        )
        root.destroy()
        sys.exit(0)

    base_dir = get_base_dir()
    # 作業ディレクトリを実行ファイルの場所に固定
    os.chdir(base_dir)

    from gui import GPSTimeSyncGUI
    root = tk.Tk()
    app = GPSTimeSyncGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
