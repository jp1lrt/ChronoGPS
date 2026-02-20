"""
Windows自動スタート設定モジュール
レジストリを使用してスタートアップに登録
"""
import os
import sys
import ctypes
import winreg


class AutoStart:
    def __init__(self, app_name="GPS_Time_Sync"):
        self.app_name = app_name
        self.reg_path = r"Software\Microsoft\Windows\CurrentVersion\Run"

    def get_executable_path(self):
        """実行ファイルのパスを取得"""
        if getattr(sys, 'frozen', False):
            # EXE化されている場合
            return sys.executable
        else:
            # Pythonスクリプトとして実行されている場合
            # pythonw.exe を使用してコンソールを表示しない
            python_path = sys.executable.replace('python.exe', 'pythonw.exe')
            script_path = os.path.abspath(sys.argv[0])
            return f'"{python_path}" "{script_path}"'

    def is_enabled(self):
        """自動スタートが有効か確認"""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self.reg_path,
                0,
                winreg.KEY_READ
            )
            try:
                value, _ = winreg.QueryValueEx(key, self.app_name)
                winreg.CloseKey(key)
                return True
            except FileNotFoundError:
                winreg.CloseKey(key)
                return False
        except Exception as e:
            print(f"レジストリ読み取りエラー: {e}")
            return False

    def enable(self):
        """自動スタートを有効にする"""
        try:
            exe_path = self.get_executable_path()

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self.reg_path,
                0,
                winreg.KEY_SET_VALUE
            )

            winreg.SetValueEx(
                key,
                self.app_name,
                0,
                winreg.REG_SZ,
                exe_path
            )

            winreg.CloseKey(key)
            return True, "自動スタートを有効にしました"

        except Exception as e:
            return False, f"エラー: {e}"

    def disable(self):
        """自動スタートを無効にする"""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self.reg_path,
                0,
                winreg.KEY_SET_VALUE
            )

            try:
                winreg.DeleteValue(key, self.app_name)
                winreg.CloseKey(key)
                return True, "自動スタートを無効にしました"
            except FileNotFoundError:
                winreg.CloseKey(key)
                return True, "既に無効です"

        except Exception as e:
            return False, f"エラー: {e}"

    def restart_as_admin(self):
        """管理者権限で自分自身を再起動する。

        成功した場合は True を返す（呼び出し元はその後 sys.exit() すること）。
        失敗した場合は False と理由を返す。
        """
        try:
            if getattr(sys, 'frozen', False):
                # EXE化されている場合
                exe = sys.executable
                params = ' '.join(sys.argv[1:])
            else:
                # Pythonスクリプトの場合: pythonw.exe でコンソールを出さない
                exe = sys.executable.replace('python.exe', 'pythonw.exe')
                params = ' '.join(f'"{a}"' for a in sys.argv)

            # ShellExecute で runas（UACダイアログを出して昇格）
            ret = ctypes.windll.shell32.ShellExecuteW(
                None,       # hwnd
                "runas",    # 動詞（管理者として実行）
                exe,        # 実行ファイル
                params,     # 引数
                None,       # 作業ディレクトリ（None = カレント）
                1           # SW_NORMAL
            )
            # ShellExecuteW は 32 より大きい値を返せば成功
            if ret > 32:
                return True, "再起動します"
            else:
                return False, f"ShellExecuteW failed (code={ret})"
        except Exception as e:
            return False, str(e)


# テスト
if __name__ == "__main__":
    autostart = AutoStart()

    print(f"  行ファイルパス: {autostart.get_executable_path()}")
    print(f"自動スタート状態: {'有効' if autostart.is_enabled() else '無効'}")

    # 有効化テスト
    success, msg = autostart.enable()
    print(f"有効化: {msg}")
    print(f"自動スタート状態: {'有効' if autostart.is_enabled() else '無効'}")

    # 無効化テスト
    success, msg = autostart.disable()
    print(f"無効化: {msg}")
    print(f"自動スタート状態: {'有効' if autostart.is_enabled() else '無効'}")
