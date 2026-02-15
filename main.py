"""メインアプリケーション"""
import sys
import os
import tkinter as tk
from gui import GPSTimeSyncGUI

def get_base_dir():
    """実行ファイルの場所を返す（exe化・スクリプト両対応）"""
    if getattr(sys, 'frozen', False):
        # PyInstallerでexe化された場合
        return os.path.dirname(sys.executable)
    else:
        # スクリプト実行の場合
        return os.path.dirname(os.path.abspath(__file__))

def main():
    base_dir = get_base_dir()
    # 作業ディレクトリを実行ファイルの場所に固定
    os.chdir(base_dir)

    root = tk.Tk()
    app = GPSTimeSyncGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
