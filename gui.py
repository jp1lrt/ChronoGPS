"""
GPS/NTP 時刻同期ツール GUI（FT8オフセット0.1秒刻み対応版）
全16言語対応 + システムトレイ + 自動スタート + FT8時刻オフセット（0.1秒刻み）
About ウィンドウは NMEATime2 風（大アイコン + 情報）・寄付ボタンあり（PayPal.Me @jp1lrt）

Author: 津久浦 慶治 / Yoshiharu Tsukuura  callsign JP1LRT (@jp1lrt)
License: MIT
"""
import sys
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import webbrowser
import serial.tools.list_ports
import threading
import serial
import time
from datetime import datetime, timezone, timedelta
import queue
from nmea_parser import NMEAParser
from ntp_client import NTPClient
from time_sync import TimeSynchronizer
from locales import Localization
from config import Config
from tray_icon import TrayIcon
from autostart import AutoStart
import os

# v2.5 (案2) 追加：昇格再起動・確実終了
try:
    from shutdown_manager import ShutdownManager
except Exception:
    ShutdownManager = None  # テスト/段階導入用

try:
    import admin  # admin.py: check_admin / launch_elevated_and_confirm
except Exception:
    admin = None  # テスト/段階導入用


def get_resource_path(relative_path):
    """PyInstallerのバンドルリソースへのパスを取得（デバッグ出力なし）"""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


class ScrollableFrame(ttk.Frame):
    """
    ttk.Frame の中身を縦スクロール可能にする軽量実装。
    - Canvas + interior frame + Scrollbar
    - Canvas 幅に content 幅を追従（レスポンシブ）
    - Windows / macOS / Linux マウスホイール対応
    使い方:
        sf = ScrollableFrame(parent, padding=10)
        sf.pack(fill=tk.BOTH, expand=True)
        main_frame = sf.content
    """

    def __init__(self, parent, *, padding=0):
        super().__init__(parent)

        self._canvas = tk.Canvas(self, highlightthickness=0)
        self._vsb = ttk.Scrollbar(self, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=self._vsb.set)

        self._vsb.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        self.content = ttk.Frame(self._canvas, padding=padding)
        self._window_id = self._canvas.create_window((0, 0), window=self.content, anchor="nw")

        # ラムダ式で簡潔に
        self.content.bind("<Configure>",
            lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<Configure>",
            lambda e: self._canvas.itemconfigure(self._window_id, width=e.width))

        # マウスホイール：Enter/Leave で制御
        self._canvas.bind("<Enter>", self._bind_mousewheel)
        self._canvas.bind("<Leave>", self._unbind_mousewheel)

    def _on_mousewheel(self, event):
        # Linux: Button-4/5
        num = getattr(event, "num", None)
        if num == 4:
            self._canvas.yview_scroll(-1, "units")
            return
        if num == 5:
            self._canvas.yview_scroll(1, "units")
            return
        # Windows / macOS
        delta = getattr(event, "delta", 0)
        if not delta:
            return
        if sys.platform == "darwin":
            self._canvas.yview_scroll(int(-delta), "units")
        else:
            self._canvas.yview_scroll(int(-delta / 120), "units")

    def _bind_mousewheel(self, event=None):
        self._canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        # Linux 用
        self._canvas.bind_all("<Button-4>", self._on_mousewheel)
        self._canvas.bind_all("<Button-5>", self._on_mousewheel)

    def _unbind_mousewheel(self, event=None):
        try:
            self._canvas.unbind_all("<MouseWheel>")
            self._canvas.unbind_all("<Button-4>")
            self._canvas.unbind_all("<Button-5>")
        except Exception:
            pass


class GPSTimeSyncGUI:
    def __init__(self, root, *, startup_ctx=None):
        self.root = root
        # v2.5 (案2): main.py から起動コンテキストを受け取り、初期モードを反映する
        self.startup_ctx = startup_ctx

        # 設定管理
        self.config = Config()

        # 自動スタート管理
        self.autostart = AutoStart()

        # 多言語対応
        self.loc = Localization()
        lang = self.config.get('language')
        if lang and lang != 'auto':
            self.loc.set_language(lang)
        else:
            # 未設定または'auto'の場合：OSロケールから自動判定
            detected = self._detect_system_language(list(self.loc.get_available_languages()))
            self.loc.set_language(detected)

        # override 適用（locales_override があれば上書きを有効にする）
        self._apply_locales_override()

        self.root.title(self.loc.get('app_title') or "GPS/NTP Time Synchronization Tool")

        # Windows タスクバー用 AppUserModelID を設定
        # これがないと python.exe のアイコンがタスクバーに出てしまう
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('jp1lrt.ChronoGPS')
        except Exception:
            pass

        # ウィンドウアイコン設定（icon.ico → icon.png の順で試みる）
        try:
            icon_path = get_resource_path('icon.ico')
            if os.path.exists(icon_path):
                self.root.iconbitmap(icon_path)
            else:
                icon_png = get_resource_path('icon.png')
                if os.path.exists(icon_png):
                    from PIL import Image, ImageTk
                    img = Image.open(icon_png).resize((32, 32), Image.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
                    self.root.iconphoto(True, photo)
                    self._icon_photo = photo  # GC防止
        except Exception:
            pass  # アイコンが無くてもアプリは動く

        # ウィンドウサイズと位置を復元
        width = self.config.get('window', 'width') or 950
        height = self.config.get('window', 'height') or 850
        x = self.config.get('window', 'x')
        y = self.config.get('window', 'y')

        if x and y:
            self.root.geometry(f"{width}x{height}+{x}+{y}")
        else:
            self.root.geometry(f"{width}x{height}")

        self.root.minsize(820, 650)

        self.parser = NMEAParser()
        self.ntp_client = NTPClient()
        self.sync = TimeSynchronizer(self.loc)  # localizationを渡す

        self.serial_port = None
        self.is_running = False
        self.ntp_sync_timer = None
        self.gps_sync_timer = None
        self._gps_next_sync_mono = None  # interval sync: 次回同期期限（monotonic）
        self.debug_enabled = False         # スレッドセーフなデバッグフラグ
        self._gps_interval_index = 2       # スレッドセーフなインターバルインデックス

        # GPS同期モードのスレッドセーフなコピー（_read_gpsスレッドから参照）
        self._gps_sync_mode = 'none'

        # _on_gps_mode_change のリエントラント防止フラグ
        # gps_sync_mode.set() をコードから呼ぶ際に True にしてコールバックを無視する
        self._gps_mode_changing = False

        # UIキュー（workerスレッド → メインスレッド）
        self.ui_queue = queue.Queue()
        # FT8 offset 表示タイマーID（多重防止）
        self._offset_timer_id = None

        # v2.5 (案2) 追加：UIキューafter IDを保持（ShutdownManagerで確実に止めるため）
        self._ui_queue_timer_id = None

        # v2.5 (案2) 追加：ShutdownManager（存在すれば使う）
        self._closing = False
        self.shutdown_mgr = None
        if ShutdownManager is not None:
            try:
                self.shutdown_mgr = ShutdownManager()
            except Exception:
                self.shutdown_mgr = None

        # GPS時刻追従表示用（monotonic で受信時刻を記録）
        self._gps_rx_dt = None   # 最後に受信したGPS時刻（datetime）
        self._gps_rx_mono = None   # その時の time.monotonic()

        # システムトレイ
        self.tray = TrayIcon(
            app_title=self.loc.get('app_title') or "GPS/NTP Time Synchronization Tool",
            on_show=self._show_window,
            on_quit=self._quit_app
        )

        # ウィジェット参照を保存（言語切り替え用）
        self.widgets = {}

        self._create_menu()
        self._create_widgets()
        self._update_ui_language()  # ウィジェット作成後に言語を適用
        self._update_ports()
        self._load_settings_to_ui()

        # ウィンドウイベント
        # × ボタンはトレイに収納（終了はトレイメニューの「終了」から）
        self.root.protocol("WM_DELETE_WINDOW", self._minimize_to_tray)

        # 最小化イベント
        self.root.bind("<Unmap>", self._on_minimize)

        # 起動時の処理
        if self.config.get('startup', 'start_minimized'):
            self.root.after(100, self._minimize_to_tray)

        # 起動時に同期
        if self.config.get('startup', 'sync_on_startup'):
            self.root.after(2000, self._sync_on_startup)

        # オフセット表示を更新（多重タイマー防止版）
        self._start_offset_timer()

        # UIキューのポーリング開始（v2.5: after id を保持）
        self._ui_queue_timer_id = self.root.after(200, self._process_ui_queue)

        # 管理者権限チェック：v2.5では監視起動が既定のため、
        # 起動時ダイアログは出さず、バナーで誘導する（_check_admin_on_startupは呼ばない）
        # if not self.sync.is_admin:
        #     self.root.after(300, self._check_admin_on_startup)

        # v2.5: 起動時バナー表示更新
        self.root.after(300, self._update_unlock_banner_visibility)

        # v2.5 (案2): 起動モードを反映（monitor なら同期機能を無効化し、バナー表示を合わせる）
        try:
            if self.startup_ctx and getattr(self.startup_ctx, "mode", "") == "monitor":
                self.root.after(400, self._apply_monitor_mode)
                self.root.after(450, self._update_unlock_banner_visibility)
        except Exception:
            pass

    def _detect_system_language(self, available_langs):
        """
        OSのシステムロケールからChronoGPS対応言語を自動判定。
        対応言語にない場合は 'en' にフォールバック。
        """
        import locale
        try:
            # Windows: GetUserDefaultUILanguage経由でより確実に取得
            import ctypes
            lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            # LCID → BCP47風の文字列マッピング（主要言語）
            lcid_map = {
                0x0411: 'ja',   # 日本語
                0x0804: 'zh',   # 中国語（簡体）
                0x0404: 'zh-tw',# 中国語（繁体）
                0x0412: 'ko',   # 韓国語
                0x040C: 'fr',   # フランス語
                0x0C0A: 'es',   # スペイン語
                0x0407: 'de',   # ドイツ語
                0x0416: 'pt',   # ポルトガル語
                0x0410: 'it',   # イタリア語
                0x0413: 'nl',   # オランダ語
                0x0419: 'ru',   # ロシア語
                0x0415: 'pl',   # ポーランド語
                0x041F: 'tr',   # トルコ語
                0x041D: 'sv',   # スウェーデン語
                0x0421: 'id',   # インドネシア語
            }
            detected = lcid_map.get(lang_id)
            if detected and detected in available_langs:
                return detected
        except Exception:
            pass

        # fallback: locale.getdefaultlocale()
        try:
            loc_code, _ = locale.getdefaultlocale()
            if loc_code:
                lang_code = loc_code.split('_')[0].lower()
                if lang_code in available_langs:
                    return lang_code
        except Exception:
            pass

        return 'en'  # 最終フォールバック

    def _apply_locales_override(self):
        """
        Apply locales_override.EXTRA_LOCALES by monkey-patching self.loc.get safely.
        - Put this method inside GPSTimeSyncGUI class (it is).
        - Called from __init__ after language setup.
        """
        try:
            import locales_override
        except Exception:
            # override ファイルが無ければ何もしない
            return

        # self.loc に get があり callable なら続行
        if not hasattr(self.loc, 'get') or not callable(getattr(self.loc, 'get')):
            return

        original_get = self.loc.get

        def patched_get(*args, **kwargs):
            """
            汎用ラッパー: args/kwargs を受け、最初の引数をキーとみなす。
            override があればそれを返し、なければ元の get を呼ぶ。
            """
            try:
                key = args[0] if len(args) > 0 else kwargs.get('key')
                if key is None:
                    return original_get(*args, **kwargs)

                # Localization の現在言語を安全に取得
                lang = getattr(self.loc, 'current_lang', None) or getattr(self.loc, 'lang', None) or 'en'

                overrides = getattr(locales_override, 'EXTRA_LOCALES', {})
                if isinstance(overrides, dict):
                    lang_over = overrides.get(lang) or overrides.get(str(lang))
                    if isinstance(lang_over, dict) and key in lang_over:
                        return lang_over[key]
            except Exception:
                # 問題があれば元の挙動にフォールバック
                pass

            return original_get(*args, **kwargs)

        # モンキーパッチ適用
        self.loc.get = patched_get

    def _create_menu(self):
        """メニューバーを（現在の言語で）作り直す。言語切替時にこれを呼べば確実に更新される。"""
        menubar = tk.Menu(self.root)

        # Language メニュー
        language_label = self.loc.get('menu_language') or 'Language'
        language_menu = tk.Menu(menubar, tearoff=0)

        # 表示名のフォールバック（locales に表示名があればそちらを優先）
        lang_names = {
            'ja': '日本語', 'en': 'English', 'fr': 'Français', 'es': 'Español',
            'de': 'Deutsch', 'zh': '中文（简体）', 'zh-tw': '中文（繁體）', 'ko': '한국어',
            'pt': 'Português', 'it': 'Italiano', 'nl': 'Nederlands', 'ru': 'Русский',
            'pl': 'Polski', 'tr': 'Türkçe', 'sv': 'Svenska', 'id': 'Bahasa Indonesia'
        }

        # 利用可能な言語一覧を取得（無ければフォールバックのキーを使う）
        try:
            available = list(self.loc.get_available_languages())
        except Exception:
            available = list(lang_names.keys())

        for code in available:
            label = self.loc.get(f'lang_{code}') or lang_names.get(code, code)
            # lambda の遅延評価問題を避ける書き方
            language_menu.add_command(label=label, command=(lambda c=code: self._change_language(c)))

        menubar.add_cascade(label=language_label, menu=language_menu)

        # Help メニュー（About）
        help_label = self.loc.get('menu_help') or 'Help'
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label=self.loc.get('menu_about') or 'About...', command=self._show_about)
        menubar.add_cascade(label=help_label, menu=help_menu)

        # ルートウィンドウにメニューをセット（これで画面に反映される）
        self.root.config(menu=menubar)

        # 参照を保存しておく（必要なら後で使える）
        self.menubar = menubar
        self.language_menu = language_menu
        self.help_menu = help_menu

    def _change_language(self, lang_code):
        """言語を変更（タブを作り直して完全反映）"""
        # 1) 言語をセット・保存
        self.loc.set_language(lang_code)
        self.config.set('language', value=lang_code)
        self.config.save()

        # 2) override を再適用
        try:
            self._apply_locales_override()
        except Exception:
            pass

        # 3) タブを作り直す（根本解決）
        self._rebuild_tabs()

        # 4) メニューを作り直す
        try:
            self._create_menu()
        except Exception:
            pass

        # 以降は既存処理（言語名取得・通知など）
        lang_names = {
            'ja': '日本語', 'en': 'English', 'fr': 'Français', 'es': 'Español',
            'de': 'Deutsch', 'zh': '中文（简体）', 'zh-tw': '中文（繁體）', 'ko': '한국어',
            'pt': 'Português', 'it': 'Italiano', 'nl': 'Nederlands', 'ru': 'Русский',
            'pl': 'Polski', 'tr': 'Türkçe', 'sv': 'Svenska', 'id': 'Bahasa Indonesia'
        }
        lang_name = lang_names.get(lang_code, lang_code)
        messagebox.showinfo(
            self.loc.get('app_title') or "GPS/NTP Time Synchronization Tool",
            f"{self.loc.get('language_changed') or 'Language changed'}: {lang_name}"
        )

    def _show_about(self):
        """NMEATime2風のリッチな About ウィンドウ（Toplevel）
        左に大きなアイコン、右にアプリ情報ブロック、下に GitHub / Donate ボタン。
        Donate は PayPal.Me (https://www.paypal.me/jp1lrt) に飛び、表示は @jp1lrt。
        """
        title = self.loc.get('about_title') or (self.loc.get('app_title') or "About")
        _app_title = self.loc.get('app_title') or 'GPS/NTP Time Synchronization Tool'
        _app_ver = self.loc.get('app_version') or '2.5'
        about_text = self.loc.get('about_text') or f"{_app_title}\nVersion: {_app_ver}"
        credits = self.loc.get('credits') or "Developed by @jp1lrt"
        github_url = self.loc.get('github_url') or "https://github.com/jp1lrt"
        github_label = self.loc.get('github_label') or "Project on GitHub"
        donate_url = self.loc.get('donate_url') or "https://www.paypal.me/jp1lrt"
        donate_label = self.loc.get('donate_label') or "Donate (@jp1lrt)"
        license_text = self.loc.get('license_name') or "MIT License"

        # create modal-like toplevel
        about_win = tk.Toplevel(self.root)
        about_win.title(title)
        about_win.transient(self.root)
        about_win.resizable(False, False)

        # center window relative to main
        about_win.update_idletasks()
        w = 560
        h = 260
        try:
            x = max(0, self.root.winfo_x() + (self.root.winfo_width() - w) // 2)
            y = max(0, self.root.winfo_y() + (self.root.winfo_height() - h) // 2)
        except Exception:
            x = 100
            y = 100
        about_win.geometry(f"{w}x{h}+{x}+{y}")

        # layout: left icon frame, right info frame
        container = ttk.Frame(about_win, padding=10)
        container.pack(fill=tk.BOTH, expand=True)

        left = ttk.Frame(container, width=140)
        left.pack(side=tk.LEFT, fill=tk.Y)
        right = ttk.Frame(container)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(12, 0))

        # Left: large icon or placeholder
        icon_path = None
        for candidate in ('icon.png', 'app_icon.png', 'icon.ico'):
            path = get_resource_path(candidate)
            if os.path.exists(path):
                icon_path = path
                break

        if icon_path:
            try:
                from PIL import Image, ImageTk
                img = Image.open(icon_path)
                img = img.resize((120, 120), Image.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                icon_lbl = ttk.Label(left, image=photo)
                icon_lbl.image = photo
                icon_lbl.pack(pady=6)
            except Exception:
                canvas = tk.Canvas(
                    left,
                    width=120,
                    height=120,
                    bg='#FFFFFF',
                    highlightthickness=1,
                    highlightbackground='#CCCCCC')
                canvas.create_text(60, 60, text="GPS\nTool", font=('Arial', 12, 'bold'))
                canvas.pack(pady=6)
        else:
            canvas = tk.Canvas(
                left,
                width=120,
                height=120,
                bg='#FFFFFF',
                highlightthickness=1,
                highlightbackground='#CCCCCC')
            canvas.create_text(60, 60, text="GPS\nTool", font=('Arial', 12, 'bold'))
            canvas.pack(pady=6)

        # Right: information block
        info_title = ttk.Label(
            right,
            text=self.loc.get('app_title') or "GPS/NTP Time Synchronization Tool",
            font=(
                'Arial',
                12,
                'bold'))
        info_title.pack(anchor='w')
        info_version = ttk.Label(right, text=self.loc.get('app_version_text') or about_text, justify=tk.LEFT)
        info_version.pack(anchor='w', pady=(6, 2))

        # License / credits / small links
        link_frame = ttk.Frame(right)
        link_frame.pack(anchor='w', pady=(6, 2), fill=tk.X)

        license_lbl = ttk.Label(
            link_frame,
            text=f"{self.loc.get('license_label') or 'License'}: {license_text}",
            foreground='gray')
        license_lbl.pack(side=tk.LEFT, anchor='w')

        credits_lbl = ttk.Label(right, text=credits, foreground='gray')
        credits_lbl.pack(anchor='w', pady=(6, 6))

        # Buttons: GitHub, Donate, Close
        btn_frame = ttk.Frame(right)
        btn_frame.pack(anchor='w', pady=(6, 0))

        def open_url(url):
            try:
                webbrowser.open(url)
            except Exception:
                messagebox.showinfo(title, url)

        gh_btn = ttk.Button(btn_frame, text=github_label, command=lambda: open_url(github_url))
        gh_btn.pack(side=tk.LEFT, padx=(0, 8))

        donate_btn = ttk.Button(btn_frame, text=donate_label, command=lambda: open_url(donate_url))
        donate_btn.pack(side=tk.LEFT, padx=(0, 8))

        # Optional: show QR if file exists (e.g., donate_qr.png)
        qr_path = None
        for cand in ('donate_qr.png', 'qr_donate.png'):
            if os.path.exists(cand):
                qr_path = cand
                break

        if qr_path:
            try:
                from PIL import Image, ImageTk
                qimg = Image.open(qr_path)
                qimg = qimg.resize((80, 80), Image.LANCZOS)
                qphoto = ImageTk.PhotoImage(qimg)
                qr_lbl = ttk.Label(right, image=qphoto)
                qr_lbl.image = qphoto
                qr_lbl.pack(anchor='w', pady=(8, 0))
            except Exception:
                pass

        close_btn = ttk.Button(about_win, text=self.loc.get('close') or "Close", command=about_win.destroy)
        close_btn.pack(side=tk.BOTTOM, pady=(6, 8))

        # modal
        about_win.grab_set()
        self.root.wait_window(about_win)

    def _update_ui_language(self):
        """UI全体の言語を更新"""
        lang_code = self.loc.current_lang
        is_ja_or_en = lang_code in ['ja', 'en']

        # ウィンドウタイトル
        self.root.title(self.loc.get('app_title') or "GPS/NTP Time Synchronization Tool")

        # タブ名
        try:
            self.notebook.tab(0, text=self.loc.get('tab_sync') or "Time Sync")
            self.notebook.tab(1, text=self.loc.get('tab_satellite') or "Satellite Info")
            self.notebook.tab(2, text=self.loc.get('options_tab') or "Options")
        except Exception:
            pass

        # ラベルフレーム
        if 'gps_frame' in self.widgets:
            self.widgets['gps_frame'].config(text=self.loc.get('gps_settings') or "GPS Settings")
        if 'ntp_frame' in self.widgets:
            self.widgets['ntp_frame'].config(text=self.loc.get('ntp_settings') or "NTP Settings")
        if 'ft8_frame' in self.widgets:
            self.widgets['ft8_frame'].config(text=self.loc.get('ft8_offset_title') or "FT8 Offset")

        if 'status_frame' in self.widgets:
            self.widgets['status_frame'].config(text=self.loc.get('status') or "Status")
        if 'log_frame' in self.widgets:
            self.widgets['log_frame'].config(text=self.loc.get('log') or "Log")

        # ラベル
        if 'com_port_label' in self.widgets:
            self.widgets['com_port_label'].config(text=self.loc.get('com_port') or "COM Port")
        if 'baud_rate_label' in self.widgets:
            self.widgets['baud_rate_label'].config(text=self.loc.get('baud_rate') or "Baud Rate")
        if 'ntp_server_label' in self.widgets:
            self.widgets['ntp_server_label'].config(text=self.loc.get('ntp_server') or "NTP Server")
        if 'gps_sync_interval_label' in self.widgets:
            self.widgets['gps_sync_interval_label'].config(text=self.loc.get('sync_interval') or "Sync Interval")
        if 'ntp_sync_interval_label' in self.widgets:
            self.widgets['ntp_sync_interval_label'].config(text=self.loc.get('sync_interval') or "Sync Interval")

        if 'system_time_label' in self.widgets:
            self.widgets['system_time_label'].config(text=self.loc.get('system_time') or "System Time")
        if 'gps_time_label' in self.widgets:
            self.widgets['gps_time_label'].config(text=self.loc.get('gps_time') or "GPS Time")
        if 'ntp_time_label' in self.widgets:
            self.widgets['ntp_time_label'].config(text=self.loc.get('ntp_time') or "NTP Time")
        if 'grid_locator_label' in self.widgets:
            self.widgets['grid_locator_label'].config(text=self.loc.get('grid_locator') or "Grid Locator")
        if 'latitude_label' in self.widgets:
            self.widgets['latitude_label'].config(text=self.loc.get('latitude') or "Latitude")
        if 'longitude_label' in self.widgets:
            self.widgets['longitude_label'].config(text=self.loc.get('longitude') or "Longitude")
        if 'altitude_label' in self.widgets:
            self.widgets['altitude_label'].config(text=self.loc.get('altitude') or "Altitude")
        if 'offset_label' in self.widgets:
            self.widgets['offset_label'].config(text=self.loc.get('time_error') or "Time Error")

        # 衛星情報フレームのラベル
        if 'summary_frame' in self.widgets:
            self.widgets['summary_frame'].config(text=self.loc.get('summary') or "Summary")
        if 'sat_inuse_label_text' in self.widgets:
            self.widgets['sat_inuse_label_text'].config(text=self.loc.get('satellites_in_use') or "Satellites in use")
        if 'sat_visible_label_text' in self.widgets:
            self.widgets['sat_visible_label_text'].config(
                text=self.loc.get('satellites_visible') or "Satellites visible")
        if 'gps_frame_sat' in self.widgets:
            self.widgets['gps_frame_sat'].config(text=self.loc.get('gps_usa') or "GPS (US)")
        if 'sbas_frame_sat' in self.widgets:
            self.widgets['sbas_frame_sat'].config(text=self.loc.get('sbas_label') or "SBAS/MSAS/WAAS")
        if 'glo_frame_sat' in self.widgets:
            self.widgets['glo_frame_sat'].config(text=self.loc.get('glonass_russia') or "GLONASS (Russia)")
        if 'bei_frame_sat' in self.widgets:
            self.widgets['bei_frame_sat'].config(text=self.loc.get('beidou_china') or "BeiDou (China)")
        if 'galileo_frame_sat' in self.widgets:
            self.widgets['galileo_frame_sat'].config(text=self.loc.get('galileo_eu') or "Galileo (EU)")
        if 'qzss_frame_sat' in self.widgets:
            self.widgets['qzss_frame_sat'].config(text=self.loc.get('qzss_japan') or "QZSS (Japan)")

        # 衛星テーブルのカラムヘッダーを更新
        for tree in [self.gps_tree, self.sbas_tree, self.glo_tree, self.bei_tree, self.galileo_tree, self.qzss_tree]:
            if tree:
                tree.heading('ID', text=self.loc.get('sat_id') or "ID")
                tree.heading('SNR', text=self.loc.get('snr') or "SNR")
                tree.heading('Elev', text=self.loc.get('elevation') or "Elevation")
                tree.heading('Azim', text=self.loc.get('azimuth') or "Azimuth")

        # GPS Sync Mode（条件付き表示）
        if 'gps_sync_mode_label' in self.widgets:
            self.widgets['gps_sync_mode_label'].config(text=self.loc.get('gps_sync_mode') or "GPS Sync Mode / GPS同期モード")

        # GPS Sync Modeラジオボタン
        if hasattr(self, 'gps_sync_radios'):
            for mode in ['none', 'instant', 'interval']:
                key = f'sync_mode_{mode}'
                text = self.loc.get(key) or {
                    'none': 'Off / オフ',
                    'instant': 'Instant / 即時',
                    'interval': 'Interval / 定期'
                }[mode]
                if mode in self.gps_sync_radios:
                    self.gps_sync_radios[mode].config(text=text)

        # FT8 Offset関連
        if 'ft8_offset_label' in self.widgets:
            self.widgets['ft8_offset_label'].config(text=self.loc.get('ft8_offset_label') or "Offset (seconds):")
        if 'ft8_apply_btn' in self.widgets:
            self.widgets['ft8_apply_btn'].config(text=self.loc.get('ft8_apply') or "Apply")
        if 'ft8_reset_btn' in self.widgets:
            self.widgets['ft8_reset_btn'].config(text=self.loc.get('ft8_reset') or "Reset")
        if 'ft8_quick_label' in self.widgets:
            self.widgets['ft8_quick_label'].config(text=self.loc.get('ft8_quick_adjust') or "Quick Adjust")
        if 'ft8_current_label' in self.widgets:
            self.widgets['ft8_current_label'].config(text=self.loc.get('ft8_current_offset') or "Current Offset")
        if 'ft8_note_label' in self.widgets:
            self.widgets['ft8_note_label'].config(text=self.loc.get('ft8_note') or "")

        # Options タブ内の要素（条件付き表示）
        if 'startup_frame' in self.widgets:
            self.widgets['startup_frame'].config(text=self.loc.get('startup_settings') or "Startup Settings")
        if 'start_with_windows_check' in self.widgets:
            self.widgets['start_with_windows_check'].config(
                text=self.loc.get('start_with_windows') or "Start with Windows")
        if 'start_minimized_check' in self.widgets:
            self.widgets['start_minimized_check'].config(text=self.loc.get('start_minimized') or "Start Minimized")
        if 'sync_on_startup_check' in self.widgets:
            self.widgets['sync_on_startup_check'].config(text=self.loc.get('sync_on_startup') or "Sync on Startup")
        if 'settings_frame' in self.widgets:
            self.widgets['settings_frame'].config(text=self.loc.get('settings_section') or "Settings")
        if 'save_settings_btn' in self.widgets:
            self.widgets['save_settings_btn'].config(text=self.loc.get('save_settings') or "Save Settings")
        if 'load_settings_btn' in self.widgets:
            self.widgets['load_settings_btn'].config(text=self.loc.get('load_settings') or "Load Settings")
        if 'reset_default_btn' in self.widgets:
            self.widgets['reset_default_btn'].config(text=self.loc.get('reset_default') or "Reset to Default")

        # その他ボタン・チェックボックス
        if 'refresh_btn' in self.widgets:
            self.widgets['refresh_btn'].config(text=self.loc.get('refresh') or "Refresh")
        if 'ntp_auto_check' in self.widgets:
            self.widgets['ntp_auto_check'].config(text=self.loc.get('ntp_auto_sync') or "NTP Auto Sync")

        # インターバルコンボボックスの中身を更新
        interval_values = [
            self.loc.get('interval_5min') or "5 min",
            self.loc.get('interval_10min') or "10 min",
            self.loc.get('interval_30min') or "30 min",
            self.loc.get('interval_1hour') or "1 hour",
            self.loc.get('interval_6hour') or "6 hours"
        ]
        if hasattr(self, 'gps_interval_combo'):
            idx = self.gps_interval_combo.current()
            self.gps_interval_combo.config(values=interval_values)
            self.gps_interval_combo.current(idx)
        if hasattr(self, 'ntp_interval_combo'):
            idx = self.ntp_interval_combo.current()
            self.ntp_interval_combo.config(values=interval_values)
            self.ntp_interval_combo.current(idx)

        # メインボタンのテキスト更新
        if 'start_btn' in self.widgets:
            self.widgets['start_btn'].config(text=self.loc.get('start') or "Start")
        if 'stop_btn' in self.widgets:
            self.widgets['stop_btn'].config(text=self.loc.get('stop') or "Stop")
        if 'sync_gps_btn' in self.widgets:
            self.widgets['sync_gps_btn'].config(text=self.loc.get('sync_gps') or "Sync GPS")
        if 'sync_ntp_btn' in self.widgets:
            self.widgets['sync_ntp_btn'].config(text=self.loc.get('sync_ntp') or "Sync NTP")
        if 'debug_check' in self.widgets:
            self.widgets['debug_check'].config(text=self.loc.get('debug_mode') or "Debug Mode")

        # Info タブのクレジットラベルを更新（存在する場合）
        if hasattr(self, 'credits_label'):
            self.credits_label.config(text=self.loc.get('credits') or "Developed by @jp1lrt")

        # Informationセクションも更新
        if hasattr(self, 'info_text'):
            self._update_info_text()

    def _rebuild_tabs(self):
        """言語切り替え時にタブの中身を破棄して作り直す（根本解決）"""
        # 現在のタブ位置を保存
        try:
            current_tab = self.notebook.index('current')
        except Exception:
            current_tab = 0

        # 実行中の状態を保存
        was_running = self.is_running

        # 各タブの中身を全削除
        for widget in self.tab_sync.winfo_children():
            widget.destroy()
        for widget in self.tab_satellite.winfo_children():
            widget.destroy()
        for widget in self.tab_options.winfo_children():
            widget.destroy()

        # タブ名を更新
        self.notebook.tab(0, text=self.loc.get('tab_sync') or "Time Sync")
        self.notebook.tab(1, text=self.loc.get('tab_satellite') or "Satellite Info")
        self.notebook.tab(2, text=self.loc.get('options_tab') or "Options")

        # widgets辞書をリセット
        self.widgets = {}

        # タブを作り直す
        self._create_sync_tab()
        self._create_satellite_tab()
        self._create_options_tab()

        # UI状態を復元
        self._load_settings_to_ui()
        self._update_ports()

        # 実行中だったらボタン状態を復元
        if was_running:
            if 'start_btn' in self.widgets:
                self.widgets['start_btn'].config(state='disabled')
            if 'stop_btn' in self.widgets:
                self.widgets['stop_btn'].config(state='normal')
            if 'sync_gps_btn' in self.widgets:
                self.widgets['sync_gps_btn'].config(state='normal')

        # タブ位置を戻す
        try:
            self.notebook.select(current_tab)
        except Exception:
            pass

    def _create_widgets(self):
        # タブコントロール
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # タブ1：時刻同期
        self.tab_sync = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_sync, text=self.loc.get('tab_sync') or "Time Sync")
        self._create_sync_tab()

        # タブ2：衛星情報
        self.tab_satellite = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_satellite, text=self.loc.get('tab_satellite') or "Satellite Info")
        self._create_satellite_tab()

        # タブ3：オプション
        self.tab_options = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_options, text=self.loc.get('options_tab') or "Options")
        self._create_options_tab()

    def _create_sync_tab(self):
        """時刻同期タブ"""
        sf = ScrollableFrame(self.tab_sync, padding=10)
        sf.pack(fill=tk.BOTH, expand=True)
        main_frame = sf.content

        # v2.5 (案2) 追加：監視起動 + 昇格誘導バナー（非管理者時に目立たせる）
        self._unlock_banner = ttk.Frame(main_frame, padding=(10, 8))
        self._unlock_banner.pack(fill=tk.X, pady=(0, 8))

        self._unlock_banner_icon = ttk.Label(self._unlock_banner, text="🔓", font=('Arial', 16))
        self._unlock_banner_icon.pack(side=tk.LEFT)

        self._unlock_banner_text = ttk.Label(
            self._unlock_banner,
            text=self.loc.get('monitor_mode_warn') or self.loc.get('unlock_sync_hint') or "Monitor mode: system time will not be changed.",
            wraplength=700,
            justify=tk.LEFT
        )
        self._unlock_banner_text.pack(side=tk.LEFT, padx=(10, 10), expand=True, fill=tk.X)

        self._unlock_banner_btn = ttk.Button(
            self._unlock_banner,
            text=self.loc.get('unlock_sync_btn') or self.loc.get('unlock_sync_button') or "Unlock Sync Features",
            command=self.on_unlock_sync
        )
        self._unlock_banner_btn.pack(side=tk.RIGHT)

        # GPS設定
        gps_frame = ttk.LabelFrame(main_frame, text=self.loc.get('gps_settings') or "GPS Settings", padding="10")
        gps_frame.pack(fill=tk.X, pady=5)
        self.widgets['gps_frame'] = gps_frame

        # 第1行：COMポート、ボーレート
        com_port_label = ttk.Label(gps_frame, text=self.loc.get('com_port') or "COM Port")
        com_port_label.grid(row=0, column=0, sticky=tk.W)
        self.widgets['com_port_label'] = com_port_label

        self.port_combo = ttk.Combobox(gps_frame, width=15, state='readonly')
        self.port_combo.grid(row=0, column=1, padx=5)

        refresh_btn = ttk.Button(gps_frame, text=self.loc.get('refresh') or "Refresh", command=self._update_ports)
        refresh_btn.grid(row=0, column=2, padx=5)
        self.widgets['refresh_btn'] = refresh_btn

        baud_rate_label = ttk.Label(gps_frame, text=self.loc.get('baud_rate') or "Baud Rate")
        baud_rate_label.grid(row=0, column=3, sticky=tk.W, padx=(20, 0))
        self.widgets['baud_rate_label'] = baud_rate_label

        self.baud_combo = ttk.Combobox(
            gps_frame, width=10, state='readonly', values=[
                '4800', '9600', '19200', '38400', '57600', '115200'])
        self.baud_combo.current(1)
        self.baud_combo.grid(row=0, column=4, padx=5)

        # 第2行：GPS同期モード選択
        self.gps_sync_mode_label = ttk.Label(
            gps_frame, text=self.loc.get('gps_sync_mode') or "GPS Sync Mode / GPS同期モード")
        self.gps_sync_mode_label.grid(row=1, column=0, sticky=tk.W, pady=5)
        self.widgets['gps_sync_mode_label'] = self.gps_sync_mode_label

        self.gps_sync_mode = tk.StringVar(value='none')
        mode_frame = ttk.Frame(gps_frame)
        mode_frame.grid(row=1, column=1, columnspan=3, sticky=tk.W, pady=5)

        # ラジオボタンも辞書に保存（後で更新できるように）
        self.gps_sync_radios = {}

        self.gps_sync_radios['none'] = ttk.Radiobutton(
            mode_frame,
            text=self.loc.get('sync_mode_none') or "Off / オフ",
            variable=self.gps_sync_mode,
            value='none',
            command=self._on_gps_mode_change
        )
        self.gps_sync_radios['none'].pack(side=tk.LEFT, padx=5)

        self.gps_sync_radios['instant'] = ttk.Radiobutton(
            mode_frame,
            text=self.loc.get('sync_mode_instant') or "Instant / 即時",
            variable=self.gps_sync_mode,
            value='instant',
            command=self._on_gps_mode_change
        )
        self.gps_sync_radios['instant'].pack(side=tk.LEFT, padx=5)

        self.gps_sync_radios['interval'] = ttk.Radiobutton(
            mode_frame,
            text=self.loc.get('sync_mode_interval') or "Interval / 定期（監視用）",
            variable=self.gps_sync_mode,
            value='interval',
            command=self._on_gps_mode_change
        )
        self.gps_sync_radios['interval'].pack(side=tk.LEFT, padx=5)

        # 第3行：定期同期の間隔設定
        gps_sync_interval_label = ttk.Label(gps_frame, text=self.loc.get('sync_interval') or "Sync Interval")
        gps_sync_interval_label.grid(row=2, column=1, sticky=tk.W, padx=(0, 5))
        self.widgets['gps_sync_interval_label'] = gps_sync_interval_label

        self.gps_interval_combo = ttk.Combobox(gps_frame, width=15, state='readonly', values=[
            self.loc.get('interval_5min') or "5 min",
            self.loc.get('interval_10min') or "10 min",
            self.loc.get('interval_30min') or "30 min",
            self.loc.get('interval_1hour') or "1 hour",
            self.loc.get('interval_6hour') or "6 hours"
        ])
        self.gps_interval_combo.current(2)
        self.gps_interval_combo.bind('<<ComboboxSelected>>',
            lambda _: setattr(self, '_gps_interval_index', self.gps_interval_combo.current()))
        self.gps_interval_combo.grid(row=2, column=2, padx=5)

        # NTP設定
        ntp_frame = ttk.LabelFrame(main_frame, text=self.loc.get('ntp_settings') or "NTP Settings", padding="10")
        ntp_frame.pack(fill=tk.X, pady=5)
        self.widgets['ntp_frame'] = ntp_frame

        # 第1行
        ntp_server_label = ttk.Label(ntp_frame, text=self.loc.get('ntp_server') or "NTP Server")
        ntp_server_label.grid(row=0, column=0, sticky=tk.W)
        self.widgets['ntp_server_label'] = ntp_server_label

        self.ntp_entry = ttk.Entry(ntp_frame, width=30)
        self.ntp_entry.insert(0, "pool.ntp.org")
        self.ntp_entry.grid(row=0, column=1, padx=5)

        # 第2行：自動同期設定
        self.ntp_auto_sync_var = tk.BooleanVar(value=False)
        ntp_auto_check = ttk.Checkbutton(ntp_frame, text=self.loc.get('ntp_auto_sync') or "NTP Auto Sync",
                                         variable=self.ntp_auto_sync_var,
                                         command=self._toggle_ntp_auto_sync)
        ntp_auto_check.grid(row=1, column=0, sticky=tk.W, pady=5)
        self.widgets['ntp_auto_check'] = ntp_auto_check

        ntp_sync_interval_label = ttk.Label(ntp_frame, text=self.loc.get('sync_interval') or "Sync Interval")
        ntp_sync_interval_label.grid(row=1, column=1, sticky=tk.W, padx=(0, 5))
        self.widgets['ntp_sync_interval_label'] = ntp_sync_interval_label

        self.ntp_interval_combo = ttk.Combobox(ntp_frame, width=15, state='readonly', values=[
            self.loc.get('interval_5min') or "5 min",
            self.loc.get('interval_10min') or "10 min",
            self.loc.get('interval_30min') or "30 min",
            self.loc.get('interval_1hour') or "1 hour",
            self.loc.get('interval_6hour') or "6 hours"
        ])
        self.ntp_interval_combo.current(2)
        self.ntp_interval_combo.grid(row=1, column=2, padx=5)

        # FT8時刻オフセット機能（0.1秒刻み）
        ft8_frame = ttk.LabelFrame(main_frame, text=self.loc.get('ft8_offset_title') or "FT8 Time Offset", padding="10")
        ft8_frame.pack(fill=tk.X, pady=5)
        self.widgets['ft8_frame'] = ft8_frame

        # 第1行：オフセット入力
        ft8_offset_label = ttk.Label(ft8_frame, text=self.loc.get('ft8_offset_label') or "Offset (seconds):")
        ft8_offset_label.grid(row=0, column=0, sticky=tk.W, padx=5)
        self.widgets['ft8_offset_label'] = ft8_offset_label

        self.offset_entry = ttk.Entry(ft8_frame, width=10)
        self.offset_entry.insert(0, "0.0")
        self.offset_entry.grid(row=0, column=1, padx=5)

        ft8_apply_btn = ttk.Button(ft8_frame, text=self.loc.get('ft8_apply') or "Apply", command=self._apply_offset)
        ft8_apply_btn.grid(row=0, column=2, padx=5)
        self.widgets['ft8_apply_btn'] = ft8_apply_btn

        ft8_reset_btn = ttk.Button(ft8_frame, text=self.loc.get('ft8_reset') or "Reset", command=self._reset_offset)
        ft8_reset_btn.grid(row=0, column=3, padx=5)
        self.widgets['ft8_reset_btn'] = ft8_reset_btn

        ft8_current_label = ttk.Label(ft8_frame, text=self.loc.get('ft8_current_offset') or "Current Offset")
        ft8_current_label.grid(row=0, column=4, sticky=tk.W, padx=(20, 5))
        self.widgets['ft8_current_label'] = ft8_current_label

        self.current_offset_label = ttk.Label(ft8_frame, text="0.0 sec", font=('Arial', 10, 'bold'), foreground='green')
        self.current_offset_label.grid(row=0, column=5, padx=5)

        # 第2行：プリセットボタン
        ft8_quick_label = ttk.Label(ft8_frame, text=self.loc.get('ft8_quick_adjust') or "Quick Adjust")
        ft8_quick_label.grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.widgets['ft8_quick_label'] = ft8_quick_label

        preset_frame = ttk.Frame(ft8_frame)
        preset_frame.grid(row=1, column=1, columnspan=5, sticky=tk.W, padx=5, pady=5)

        ttk.Button(preset_frame, text="-1.0", width=6,
                   command=lambda: self._quick_offset(-1.0)).pack(side=tk.LEFT, padx=2)
        ttk.Button(preset_frame, text="-0.5", width=6,
                   command=lambda: self._quick_offset(-0.5)).pack(side=tk.LEFT, padx=2)
        ttk.Button(preset_frame, text="-0.1", width=6,
                   command=lambda: self._quick_offset(-0.1)).pack(side=tk.LEFT, padx=2)
        ttk.Button(
            preset_frame,
            text="+0.1",
            width=6,
            command=lambda: self._quick_offset(0.1)).pack(
            side=tk.LEFT,
            padx=2)
        ttk.Button(
            preset_frame,
            text="+0.5",
            width=6,
            command=lambda: self._quick_offset(0.5)).pack(
            side=tk.LEFT,
            padx=2)
        ttk.Button(
            preset_frame,
            text="+1.0",
            width=6,
            command=lambda: self._quick_offset(1.0)).pack(
            side=tk.LEFT,
            padx=2)

        # 第3行：注意書き
        ft8_note_label = ttk.Label(ft8_frame, text=self.loc.get('ft8_note') or "", font=('Arial', 8), foreground='gray')
        ft8_note_label.grid(row=2, column=0, columnspan=6, sticky=tk.W, padx=5, pady=2)
        self.widgets['ft8_note_label'] = ft8_note_label

        # ボタン
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(pady=10)

        start_btn = ttk.Button(button_frame, text=self.loc.get('start') or "Start", command=self._start)
        start_btn.grid(row=0, column=0, padx=5)
        self.widgets['start_btn'] = start_btn

        stop_btn = ttk.Button(button_frame, text=self.loc.get('stop') or "Stop", command=self._stop, state='disabled')
        stop_btn.grid(row=0, column=1, padx=5)
        self.widgets['stop_btn'] = stop_btn

        sync_gps_btn = ttk.Button(
            button_frame,
            text=self.loc.get('sync_gps') or "Sync GPS",
            command=self._sync_gps,
            state='disabled')
        sync_gps_btn.grid(row=0, column=2, padx=5)
        self.widgets['sync_gps_btn'] = sync_gps_btn

        sync_ntp_btn = ttk.Button(button_frame, text=self.loc.get('sync_ntp') or "Sync NTP", command=self._sync_ntp)
        sync_ntp_btn.grid(row=0, column=3, padx=5)
        self.widgets['sync_ntp_btn'] = sync_ntp_btn

        # デバッグモード
        self.debug_var = tk.BooleanVar(value=False)
        self.debug_var.trace_add('write', lambda *_: setattr(self, 'debug_enabled', bool(self.debug_var.get())))
        debug_check = ttk.Checkbutton(button_frame, text=self.loc.get('debug') or "Debug", variable=self.debug_var)
        debug_check.grid(row=0, column=4, padx=5)
        self.widgets['debug_check'] = debug_check

        # ステータス表示
        status_frame = ttk.LabelFrame(main_frame, text=self.loc.get('status') or "Status", padding="10")
        status_frame.pack(fill=tk.X, pady=5)
        self.widgets['status_frame'] = status_frame

        # 時刻情報
        system_time_label = ttk.Label(status_frame, text=self.loc.get('system_time') or "System Time")
        system_time_label.grid(row=0, column=0, sticky=tk.W)
        self.widgets['system_time_label'] = system_time_label

        self.system_time_value = ttk.Label(status_frame, text="-", font=('Courier', 10))
        self.system_time_value.grid(row=0, column=1, sticky=tk.W, padx=10)

        gps_time_label = ttk.Label(status_frame, text=self.loc.get('gps_time') or "GPS Time")
        gps_time_label.grid(row=1, column=0, sticky=tk.W)
        self.widgets['gps_time_label'] = gps_time_label

        self.gps_time_value = ttk.Label(status_frame, text="-", font=('Courier', 10))
        self.gps_time_value.grid(row=1, column=1, sticky=tk.W, padx=10)

        ntp_time_label = ttk.Label(status_frame, text=self.loc.get('ntp_time') or "NTP Time")
        ntp_time_label.grid(row=2, column=0, sticky=tk.W)
        self.widgets['ntp_time_label'] = ntp_time_label

        self.ntp_time_value = ttk.Label(status_frame, text="-", font=('Courier', 10))
        self.ntp_time_value.grid(row=2, column=1, sticky=tk.W, padx=10)

        # 位置情報
        grid_locator_label = ttk.Label(status_frame, text=self.loc.get('grid_locator') or "Grid Locator")
        grid_locator_label.grid(row=0, column=2, sticky=tk.W, padx=(30, 0))
        self.widgets['grid_locator_label'] = grid_locator_label

        self.grid_value = ttk.Label(status_frame, text="-", font=('Courier', 12, 'bold'), foreground='blue')
        self.grid_value.grid(row=0, column=3, sticky=tk.W, padx=10)

        latitude_label = ttk.Label(status_frame, text=self.loc.get('latitude') or "Latitude")
        latitude_label.grid(row=1, column=2, sticky=tk.W, padx=(30, 0))
        self.widgets['latitude_label'] = latitude_label

        self.lat_value = ttk.Label(status_frame, text="-", font=('Courier', 10))
        self.lat_value.grid(row=1, column=3, sticky=tk.W, padx=10)

        longitude_label = ttk.Label(status_frame, text=self.loc.get('longitude') or "Longitude")
        longitude_label.grid(row=2, column=2, sticky=tk.W, padx=(30, 0))
        self.widgets['longitude_label'] = longitude_label

        self.lon_value = ttk.Label(status_frame, text="-", font=('Courier', 10))
        self.lon_value.grid(row=2, column=3, sticky=tk.W, padx=10)

        altitude_label = ttk.Label(status_frame, text=self.loc.get('altitude') or "Altitude")
        altitude_label.grid(row=3, column=0, sticky=tk.W)
        self.widgets['altitude_label'] = altitude_label

        self.alt_value = ttk.Label(status_frame, text="-", font=('Courier', 10))
        self.alt_value.grid(row=3, column=1, sticky=tk.W, padx=10)

        # 時刻誤差 Δ(System - GPS) 表示
        offset_label = ttk.Label(status_frame, text=self.loc.get('time_error') or "Time Error")
        offset_label.grid(row=4, column=0, sticky=tk.W)
        self.widgets['offset_label'] = offset_label

        self.offset_value = ttk.Label(status_frame, text="–", font=('Courier', 10))
        self.offset_value.grid(row=4, column=1, sticky=tk.W, padx=10)

        # ログ
        log_frame = ttk.LabelFrame(main_frame, text=self.loc.get('log') or "Log", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        self.widgets['log_frame'] = log_frame

        self.log_text = scrolledtext.ScrolledText(log_frame, height=6, state='disabled')
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # 時刻更新タイマー, 位置更新
        self._update_system_time()
        self._update_position_info()
        # ★ここに追加！ main_frameの中で「ログ」が入っている行を縦に伸ばす設定
        main_frame.rowconfigure(4, weight=1)  # ログフレームは5番目(index 4)の要素なので

    def _create_satellite_tab(self):
        """衛星情報タブ"""
        main_frame = ttk.Frame(self.tab_satellite, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # サマリー
        summary_frame = ttk.LabelFrame(main_frame, text=self.loc.get('summary') or "Summary", padding="10")
        summary_frame.pack(fill=tk.X, pady=5)
        self.widgets['summary_frame'] = summary_frame

        sat_inuse_label_text = ttk.Label(summary_frame, text=self.loc.get('satellites_in_use') or "Satellites in use")
        sat_inuse_label_text.grid(row=0, column=0, sticky=tk.W)
        self.widgets['sat_inuse_label_text'] = sat_inuse_label_text

        self.sat_inuse_value = ttk.Label(summary_frame, text="0", font=('Arial', 14, 'bold'), foreground='green')
        self.sat_inuse_value.grid(row=0, column=1, padx=10)

        sat_visible_label_text = ttk.Label(summary_frame,
                                           text=self.loc.get('satellites_visible') or "Satellites visible")
        sat_visible_label_text.grid(row=0, column=2, sticky=tk.W, padx=(20, 0))
        self.widgets['sat_visible_label_text'] = sat_visible_label_text

        self.sat_total_value = ttk.Label(summary_frame, text="0", font=('Arial', 14, 'bold'))
        self.sat_total_value.grid(row=0, column=3, padx=10)

        # 衛星リスト（システム別）
        sat_frame = ttk.Frame(main_frame)
        sat_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        # GPS
        gps_frame_sat = ttk.LabelFrame(sat_frame, text=self.loc.get('gps_usa') or "GPS (US)", padding="5")
        gps_frame_sat.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)
        self.widgets['gps_frame_sat'] = gps_frame_sat
        self.gps_tree = self._create_satellite_tree(gps_frame_sat)

        # SBAS/MSAS
        sbas_frame_sat = ttk.LabelFrame(sat_frame, text=self.loc.get('sbas_label') or "SBAS/MSAS/WAAS", padding="5")
        sbas_frame_sat.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)
        self.widgets['sbas_frame_sat'] = sbas_frame_sat
        self.sbas_tree = self._create_satellite_tree(sbas_frame_sat)

        # GLONASS
        glo_frame_sat = ttk.LabelFrame(sat_frame, text=self.loc.get(
            'glonass_russia') or "GLONASS (Russia)", padding="5")
        glo_frame_sat.grid(row=0, column=2, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)
        self.widgets['glo_frame_sat'] = glo_frame_sat
        self.glo_tree = self._create_satellite_tree(glo_frame_sat)

        # BeiDou
        bei_frame_sat = ttk.LabelFrame(sat_frame, text=self.loc.get('beidou_china') or "BeiDou (China)", padding="5")
        bei_frame_sat.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)
        self.widgets['bei_frame_sat'] = bei_frame_sat
        self.bei_tree = self._create_satellite_tree(bei_frame_sat)

        # Galileo
        galileo_frame_sat = ttk.LabelFrame(sat_frame, text=self.loc.get('galileo_eu') or "Galileo (EU)", padding="5")
        galileo_frame_sat.grid(row=1, column=1, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)
        self.widgets['galileo_frame_sat'] = galileo_frame_sat
        self.galileo_tree = self._create_satellite_tree(galileo_frame_sat)

        # QZSS
        qzss_frame_sat = ttk.LabelFrame(sat_frame, text=self.loc.get('qzss_japan') or "QZSS (Japan)", padding="5")
        qzss_frame_sat.grid(row=1, column=2, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)
        self.widgets['qzss_frame_sat'] = qzss_frame_sat
        self.qzss_tree = self._create_satellite_tree(qzss_frame_sat)

        # グリッド設定（3列に変更）
        sat_frame.columnconfigure(0, weight=1)
        sat_frame.columnconfigure(1, weight=1)
        sat_frame.columnconfigure(2, weight=1)
        sat_frame.rowconfigure(0, weight=1)
        sat_frame.rowconfigure(1, weight=1)

        # 更新タイマー
        self._update_satellite_info()

    def _create_satellite_tree(self, parent):
        """衛星情報ツリービュー作成（縦スクロールバー付き・幅追従）"""

        # Treeview + Scrollbar を入れるコンテナ
        container = ttk.Frame(parent)
        container.pack(fill=tk.BOTH, expand=True)

        tree = ttk.Treeview(
            container,
            columns=('ID', 'SNR', 'Elev', 'Azim'),
            show='headings',
            height=6
        )

        # 見出し
        tree.heading('ID', text=self.loc.get('sat_id') or "ID")
        tree.heading('SNR', text=self.loc.get('snr') or "SNR")
        tree.heading('Elev', text=self.loc.get('elevation') or "Elevation")
        tree.heading('Azim', text=self.loc.get('azimuth') or "Azimuth")

        # 縦スクロールバー
        vsb = ttk.Scrollbar(container, orient='vertical', command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)

        # レイアウト（Treeviewが伸びる）
        tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        container.columnconfigure(0, weight=1)
        container.rowconfigure(0, weight=1)

        # 列：固定60pxをやめて伸縮可能に（最小幅だけ確保）
        tree.column('ID', anchor='center', stretch=True, minwidth=50, width=70)
        tree.column('SNR', anchor='center', stretch=True, minwidth=50, width=70)
        tree.column('Elev', anchor='center', stretch=True, minwidth=50, width=70)
        tree.column('Azim', anchor='center', stretch=True, minwidth=50, width=70)

        # 幅追従：ウィンドウを広げたら列幅も按分して追従
        def _autosize_columns(event=None):
            w = tree.winfo_width()
            if w <= 1:
                return
            # スクロールバー分＋余白を引く（だいたいでOK）
            avail = max(w - 22, 200)

            # IDは少し狭く、他を広めに
            id_w = max(int(avail * 0.22), 50)
            rest = max(int((avail - id_w) / 3), 50)

            tree.column('ID', width=id_w)
            tree.column('SNR', width=rest)
            tree.column('Elev', width=rest)
            tree.column('Azim', width=rest)

        tree.bind('<Configure>', _autosize_columns)

        return tree
 
    def _create_options_tab(self):
        """オプションタブ"""
        sf = ScrollableFrame(self.tab_options, padding=10)
        sf.pack(fill=tk.BOTH, expand=True)
        main_frame = sf.content

        # 起動設定
        startup_frame = ttk.LabelFrame(main_frame, text=self.loc.get(
            'startup_settings') or "Startup Settings", padding=10)
        startup_frame.pack(fill=tk.X, pady=5)
        self.widgets['startup_frame'] = startup_frame

        self.auto_start_var = tk.BooleanVar(value=self.autostart.is_enabled())
        auto_start_check = ttk.Checkbutton(
            startup_frame,
            text=self.loc.get('start_with_windows') or "Start with Windows",
            variable=self.auto_start_var,
            command=self._toggle_auto_start
        )
        auto_start_check.grid(row=0, column=0, sticky=tk.W, pady=5)
        self.widgets['start_with_windows_check'] = auto_start_check

        self.start_minimized_var = tk.BooleanVar(value=self.config.get('startup', 'start_minimized'))
        start_minimized_check = ttk.Checkbutton(
            startup_frame,
            text=self.loc.get('start_minimized') or "Start Minimized",
            variable=self.start_minimized_var
        )
        start_minimized_check.grid(row=1, column=0, sticky=tk.W, pady=5)
        self.widgets['start_minimized_check'] = start_minimized_check

        self.sync_on_startup_var = tk.BooleanVar(value=self.config.get('startup', 'sync_on_startup'))
        sync_on_startup_check = ttk.Checkbutton(
            startup_frame,
            text=self.loc.get('sync_on_startup') or "Sync on Startup",
            variable=self.sync_on_startup_var
        )
        sync_on_startup_check.grid(row=2, column=0, sticky=tk.W, pady=5)
        self.widgets['sync_on_startup_check'] = sync_on_startup_check

        # 設定管理
        settings_frame = ttk.LabelFrame(main_frame, text=self.loc.get('settings_section') or "Settings", padding="10")
        settings_frame.pack(fill=tk.X, pady=5)
        self.widgets['settings_frame'] = settings_frame

        save_btn = ttk.Button(settings_frame, text=self.loc.get('save_settings')
                              or "Save Settings", command=self._save_settings)
        save_btn.grid(row=0, column=0, padx=5, pady=5)
        self.widgets['save_settings_btn'] = save_btn

        load_btn = ttk.Button(settings_frame, text=self.loc.get('load_settings')
                              or "Load Settings", command=self._load_settings)
        load_btn.grid(row=0, column=1, padx=5, pady=5)
        self.widgets['load_settings_btn'] = load_btn

        reset_btn = ttk.Button(settings_frame, text=self.loc.get('reset_default')
                               or "Reset to Default", command=self._reset_settings)
        reset_btn.grid(row=0, column=2, padx=5, pady=5)
        self.widgets['reset_default_btn'] = reset_btn

        # 情報表示
        self.info_frame = ttk.LabelFrame(main_frame, text=self.loc.get('info_section') or "Info", padding="10")
        self.info_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        self.info_text = scrolledtext.ScrolledText(self.info_frame, height=15, state='disabled', wrap=tk.WORD)
        self.info_text.pack(fill=tk.BOTH, expand=True)

        # 恒久的に見えるクレジットラベル（Info タブの下）
        credits_text = self.loc.get('credits') or "Developed by @jp1lrt"
        self.credits_label = ttk.Label(
            self.info_frame,
            text=credits_text,
            foreground='blue',
            cursor='hand2',
            anchor='e',
            font=(
                'Arial',
                9,
                'italic'))
        self.credits_label.pack(fill=tk.X, pady=(6, 0))

        def _open_credits_link(event=None):
            url = self.loc.get('github_url') or "https://github.com/jp1lrt"
            try:
                webbrowser.open(url)
            except Exception:
                messagebox.showinfo(self.loc.get('app_title') or "Info", url)
        self.credits_label.bind("<Button-1>", _open_credits_link)

        self._update_info_text()

    def _update_info_text(self):
        """情報テキストを更新"""
        self.info_text.config(state='normal')
        self.info_text.delete('1.0', tk.END)

        self.info_text.insert(tk.END, f"{self.loc.get('app_title') or 'GPS/NTP Time Synchronization Tool'}\n\n")
        self.info_text.insert(tk.END, f"{self.loc.get('info_version') or ''}\n")
        self.info_text.insert(tk.END, f"{self.loc.get('info_multilang') or ''}\n")
        self.info_text.insert(tk.END, f"{self.loc.get('info_gnss') or ''}\n\n")
        self.info_text.insert(tk.END, f"{self.loc.get('info_features') or ''}\n")
        self.info_text.insert(tk.END, f"{self.loc.get('info_feat_tray') or ''}\n")
        self.info_text.insert(tk.END, f"{self.loc.get('info_feat_autostart') or ''}\n")
        self.info_text.insert(tk.END, f"{self.loc.get('info_feat_gps_modes') or ''}\n")
        self.info_text.insert(tk.END, f"{self.loc.get('info_feat_ntp') or ''}\n")
        self.info_text.insert(tk.END, f"{self.loc.get('info_feat_ft8') or ''}\n\n")
        self.info_text.insert(tk.END, f"{self.loc.get('info_config_file') or ''}\n")
        # クレジットを Info セクションにも追加（補助）
        self.info_text.insert(tk.END, f"{self.loc.get('credits') or 'Developed by @jp1lrt'}\n")

        self.info_text.config(state='disabled')

    def _apply_offset(self):
        """オフセットを適用"""
        try:
            offset = float(self.offset_entry.get())

            if not self.sync.is_admin:
                messagebox.showerror(self.loc.get('app_title') or "Error",
                                     self.loc.get('admin_required') or "Administrator privileges required")
                return

            success, msg = self.sync.apply_offset(offset)

            if success:
                self._log("⏰ " + (self.loc.get('ft8_offset_applied') or 'FT8 offset applied: {msg}').format(msg=msg))
                self._update_offset_display()
                messagebox.showinfo(self.loc.get('app_title') or "Success", msg)
            else:
                messagebox.showerror(self.loc.get('app_title') or "Error", msg)

        except ValueError:
            messagebox.showerror(self.loc.get('app_title') or "Error",
                                 f"{self.loc.get('no_gps_time') or 'Invalid number'}\nInvalid number")

    def _quick_offset(self, offset):
        """クイック調整ボタン"""
        if not self.sync.is_admin:
            messagebox.showerror(self.loc.get('app_title') or "Error",
                                 self.loc.get('admin_required') or "Administrator privileges required")
            return

        success, msg = self.sync.apply_offset(offset)

        if success:
            self._log("⏰ " + (self.loc.get('ft8_quick_adjust_fmt') or 'FT8 quick adjust: {offset:+.1f}s').format(offset=offset))
            self._update_offset_display()
        else:
            messagebox.showerror(self.loc.get('app_title') or "Error", msg)

    def _reset_offset(self):
        """オフセットをリセット"""
        if abs(self.sync.get_offset()) < 0.01:
            messagebox.showinfo(self.loc.get('app_title') or "Info",
                                self.loc.get('offset_reset_success') or "Offset reset to 0")
            return

        if not self.sync.is_admin:
            messagebox.showerror(self.loc.get('app_title') or "Error",
                                 self.loc.get('admin_required') or "Administrator privileges required")
            return

        # 現在のオフセットの逆を適用
        current_offset = self.sync.get_offset()
        success, msg = self.sync.apply_offset(-current_offset)

        if success:
            self.sync.reset_offset()
            self.offset_entry.delete(0, tk.END)
            self.offset_entry.insert(0, "0.0")
            self._update_offset_display()
            self._log(f"🔄 {self.loc.get('ft8_reset_log') or 'FT8 offset reset'}")
            messagebox.showinfo(self.loc.get('app_title') or "Success",
                                self.loc.get('offset_reset_success') or "Offset reset to 0")
        else:
            messagebox.showerror(self.loc.get('app_title') or "Error", msg)

    def _start_offset_timer(self):
        """オフセット表示タイマーを1本だけ起動"""
        if self._offset_timer_id is None:
            self._offset_timer_id = self.root.after(1000, self._offset_timer_tick)

    def _stop_offset_timer(self):
        """オフセット表示タイマーを停止"""
        if self._offset_timer_id is not None:
            try:
                self.root.after_cancel(self._offset_timer_id)
            except Exception:
                pass
            self._offset_timer_id = None

    def _offset_timer_tick(self):
        """1秒ごとのオフセット表示更新（多重防止）"""
        self._offset_timer_id = None
        self._update_offset_display()
        self._offset_timer_id = self.root.after(1000, self._offset_timer_tick)

    def _update_offset_display(self):
        """オフセット表示を更新（表示のみ・タイマー管理しない）"""
        offset = self.sync.get_offset()
        self.current_offset_label.config(text=f"{offset:+.1f} sec")
        if abs(offset) < 0.01:
            self.current_offset_label.config(foreground='green')
        else:
            self.current_offset_label.config(foreground='red')

    def _toggle_auto_start(self):
        """自動スタート設定の切り替え"""
        if self.auto_start_var.get():
            success, msg = self.autostart.enable()
            if success:
                messagebox.showinfo(self.loc.get('app_title') or "Success",
                                    f"{self.loc.get('info_feat_autostart') or 'Auto-start'}\n{msg}")
            else:
                messagebox.showerror(self.loc.get('app_title') or "Error", msg)
                self.auto_start_var.set(False)
        else:
            success, msg = self.autostart.disable()
            if success:
                messagebox.showinfo(self.loc.get('app_title') or "Success",
                                    f"{self.loc.get('info_feat_autostart') or 'Auto-start'}\n{msg}")
            else:
                messagebox.showerror(self.loc.get('app_title') or "Error", msg)
                self.auto_start_var.set(True)

    def _on_minimize(self, event):
        """最小化イベント"""
        if self.root.state() == 'iconic':
            self.root.after(100, self._minimize_to_tray)

    def _minimize_to_tray(self):
        """システムトレイに格納"""
        self.root.withdraw()
        if not self.tray.is_running:
            self.tray.start()

    def _show_window(self):
        """ウィンドウを表示"""
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _quit_app(self):
        """トレイメニュー等、別スレッドから呼ばれても安全に終了できるようにする"""
        import threading

    # Tk操作はメインスレッドで実行する
        if threading.current_thread() is threading.main_thread():
            self._on_closing()
        else:
        # 0msでメインスレッドに投げる
            self.root.after(0, self._on_closing)
            
    def _sync_on_startup(self):
        """起動時に同期"""
        self._log(f"🚀 {self.loc.get('sync_on_startup_log') or 'Running startup sync...'}")

        if self.ntp_entry.get():
            self._sync_ntp()

    def _on_gps_mode_change(self):
        """GPS同期モードが変更された時"""
        # コードから gps_sync_mode.set() した際の再入を防ぐ
        if self._gps_mode_changing:
            return

        mode = self.gps_sync_mode.get()

        if self.debug_var.get():
            self._log(f"[DEBUG] _on_gps_mode_change called: mode={mode}")

        # スレッドセーフなコピーを更新
        self._gps_sync_mode = mode

        if mode == 'none':
            self._stop_gps_auto_sync()
            self._log(self.loc.get('gps_sync_off_log') or "GPS sync: off")
        elif mode == 'instant':
            self._stop_gps_auto_sync()
            self._log(self.loc.get('gps_sync_instant_log') or "GPS sync: instant")
        elif mode == 'interval':
            self._start_gps_interval_sync()
            interval_text = self.gps_interval_combo.get()
            self._log(self.loc.get('gps_sync_interval_log') or f"GPS sync: interval ({interval_text})")

    def _start_gps_interval_sync(self):
        """GPS定期同期開始（受信直後トリガ方式）
        タイマーで突然 SetSystemTime するのではなく、
        「期限が来たら次のGPS受信直後に1回だけ同期」する。
        これにより NMEA整数秒のタイミングズレ（最大±1s）を排除する。
        """
        self._stop_gps_auto_sync()
        self._gps_next_sync_mono = time.monotonic()  # 今すぐ許可（次の受信で即1回）

    def _stop_gps_auto_sync(self):
        """GPS自動同期停止"""
        if self.gps_sync_timer:
            self.root.after_cancel(self.gps_sync_timer)
            self.gps_sync_timer = None

    def _schedule_gps_sync(self):
        """次のGPS同期をスケジュール"""
        if self.gps_sync_mode.get() != 'interval':
            return

        try:
            interval_minutes = [5, 10, 30, 60, 360][self.gps_interval_combo.current()]
        except Exception:
            interval_minutes = 30
        interval_ms = interval_minutes * 60 * 1000

        self.gps_sync_timer = self.root.after(interval_ms, self._gps_sync_callback)

    def _gps_sync_callback(self):
        """GPS同期コールバック"""
        if self.parser.last_time and self.sync.is_admin:
            success, msg = self.sync.sync_time_weak(self.parser.last_time)
            if success:
                self._log(f"⏰ GPS {self.loc.get('sync_success') or 'Sync success'}: {msg}")
            else:
                self._log(f"✗ GPS {self.loc.get('sync_failed') or 'Sync failed'}: {msg}")

        self._schedule_gps_sync()

    def _toggle_ntp_auto_sync(self):
        """NTP自動同期ON/OFF"""
        if self.ntp_auto_sync_var.get():
            self._start_ntp_auto_sync()
        else:
            self._stop_ntp_auto_sync()

    def _start_ntp_auto_sync(self):
        """NTP自動同期開始"""
        self._sync_ntp_background()
        self._schedule_ntp_sync()
        self._log(f"🔄 {self.loc.get('ntp_auto_on') or 'NTP auto sync ON'}")

    def _stop_ntp_auto_sync(self):
        """NTP自動同期停止"""
        if self.ntp_sync_timer:
            self.root.after_cancel(self.ntp_sync_timer)
            self.ntp_sync_timer = None
        self._log(f"⏸ {self.loc.get('ntp_auto_off') or 'NTP auto sync OFF'}")

    def _schedule_ntp_sync(self):
        """次のNTP同期をスケジュール"""
        if not self.ntp_auto_sync_var.get():
            return

        try:
            interval_minutes = [5, 10, 30, 60, 360][self.ntp_interval_combo.current()]
        except Exception:
            interval_minutes = 30
        interval_ms = interval_minutes * 60 * 1000

        self.ntp_sync_timer = self.root.after(interval_ms, self._ntp_sync_callback)

    def _ntp_sync_callback(self):
        """NTP同期コールバック"""
        self._sync_ntp_background()
        self._schedule_ntp_sync()

    def _sync_ntp_background(self):
        """バックグラウンドでNTP同期"""
        self._sync_ntp()

    def _sync_ntp(self):
        """UIスレッドからのエントリーポイント: serverを取得してworkerを起動"""
        server = (self.ntp_entry.get() or "").strip() or "pool.ntp.org"
        threading.Thread(target=self._sync_ntp_worker, args=(server,), daemon=True).start()

    def _sync_ntp_worker(self, server: str):
        """Worker: NTP問い合わせのみ行い結果をqueueへ（UIに直接触らない）"""
        try:
            self.ntp_client.set_server(server)
            self.ui_queue.put(('log', f"NTP: {server}"))
            ntp_time, offset_ms = self.ntp_client.get_time()
            self.ui_queue.put(('ntp_result', ntp_time, offset_ms))
        except Exception as e:
            self.ui_queue.put(('ntp_error', str(e)))

    def _process_ui_queue(self):
        """メインスレッド: workerの結果を受け取りUI更新・時刻設定を行う（TclError対策済み）"""
        try:
            # ウィンドウが既に閉じられている場合は、以後の処理もタイマー予約も行わない
            if not self.root.winfo_exists():
                return

            while True:
                try:
                    item = self.ui_queue.get_nowait()
                except queue.Empty:
                    break

                if not item:
                    continue
                tag = item[0]

                if tag == 'log':
                    _, message = item
                    self._log(message)

                elif tag == 'gps_time':
                    _, gps_time, rx_mono = item
                    self._gps_rx_dt = gps_time
                    self._gps_rx_mono = rx_mono

                elif tag == 'gps_mode_reset':
                    self._gps_mode_changing = True
                    try:
                        self.gps_sync_mode.set('none')
                        self._gps_sync_mode = 'none'
                        self._gps_next_sync_mono = None  # 残留期限をリセット
                    finally:
                        self._gps_mode_changing = False

                elif tag == 'ntp_result':
                    _, ntp_time, offset_ms = item
                    self.ntp_time_value.config(text=ntp_time.strftime("%Y-%m-%d %H:%M:%S UTC"))
                    self._log(f"NTP: {ntp_time}, offset: {offset_ms / 1000.0:.3f}s ({offset_ms:.2f}ms)")

                    corrected_utc = datetime.now(timezone.utc) + timedelta(milliseconds=offset_ms)

                    if not self.sync.is_admin:
                        self._log(f"⚠ {self.loc.get('admin_required') or 'Administrator required'}")
                        messagebox.showerror(
                            self.loc.get('app_title') or "Error",
                            self.loc.get('admin_required') or "Administrator privileges required"
                        )
                    else:
                        success, msg = self.sync.sync_time(corrected_utc)
                        if success:
                            self._log(f"✓ NTP {self.loc.get('sync_success') or 'Sync success'}: {msg}")
                            if not self.ntp_auto_sync_var.get():
                                messagebox.showinfo(
                                    self.loc.get('app_title') or "Success",
                                    self.loc.get('sync_success') or "Sync success"
                                )
                        else:
                            self._log(f"✗ NTP {self.loc.get('sync_failed') or 'Sync failed'}: {msg}")
                            if not self.ntp_auto_sync_var.get():
                                messagebox.showerror(self.loc.get('app_title') or "Error", msg)

                elif tag == 'ntp_error':
                    _, err = item
                    self._log(f"✗ NTP error: {err}")
                    messagebox.showerror(
                        self.loc.get('app_title') or "Error",
                        self.loc.get('ntp_error') or f"NTP error: {err}"
                    )

                try:
                    self.ui_queue.task_done()
                except Exception:
                    pass

        except (tk.TclError, RuntimeError):
            # アプリ終了時のアクセスエラーを静かに無視
            return

        # ウィンドウが存在する場合のみ、次のタイマーを予約する
        try:
            if self.root.winfo_exists():
                # v2.5: after id を保持（ShutdownManagerで確実に止めるため）
                self._ui_queue_timer_id = self.root.after(200, self._process_ui_queue)
        except (tk.TclError, RuntimeError):
            pass

    def _save_settings(self, silent=False):
        """現在の設定を保存。silent=Trueの時はダイアログを出さない"""
        # GPS設定
        self.config.set('gps', 'com_port', value=self.port_combo.get())
        try:
            baud_val = int(self.baud_combo.get())
        except (ValueError, TypeError):
            baud_val = 9600
        self.config.set('gps', 'baud_rate', value=baud_val)
        self.config.set('gps', 'sync_mode', value=self.gps_sync_mode.get())
        self.config.set('gps', 'sync_interval_index', value=self.gps_interval_combo.current())

        # NTP設定
        self.config.set('ntp', 'server', value=self.ntp_entry.get())
        self.config.set('ntp', 'auto_sync', value=self.ntp_auto_sync_var.get())
        self.config.set('ntp', 'sync_interval_index', value=self.ntp_interval_combo.current())

        # 起動設定
        self.config.set('startup', 'start_minimized', value=self.start_minimized_var.get())
        self.config.set('startup', 'sync_on_startup', value=self.sync_on_startup_var.get())

        # FT8設定
        self.config.set('ft8', 'time_offset_seconds', value=self.sync.get_offset())

        # デバッグ
        self.config.set('debug', value=self.debug_var.get())

        # ウィンドウサイズと位置
        self.config.set('window', 'width', value=self.root.winfo_width())
        self.config.set('window', 'height', value=self.root.winfo_height())
        self.config.set('window', 'x', value=self.root.winfo_x())
        self.config.set('window', 'y', value=self.root.winfo_y())

        result = self.config.save()
        if not silent:
            if result:
                messagebox.showinfo(self.loc.get('app_title') or "Success",
                                    self.loc.get('settings_saved') or "Settings saved successfully!")
            else:
                messagebox.showerror(self.loc.get('app_title') or "Error",
                                     self.loc.get('settings_save_failed') or "Failed to save settings")

    def _load_settings_to_ui(self):
        """設定をUIに反映"""
        # COMポート
        com_port = self.config.get('gps', 'com_port')
        if com_port and com_port in self.port_combo['values']:
            self.port_combo.set(com_port)

        # ボーレート（安全に処理）
        baud_rate = self.config.get('gps', 'baud_rate')
        try:
            baud_val = int(baud_rate)
        except (TypeError, ValueError):
            baud_val = 9600
        baud_list = [4800, 9600, 19200, 38400, 57600, 115200]
        baud_index = baud_list.index(baud_val) if baud_val in baud_list else 1
        self.baud_combo.current(baud_index)

        # GPS sync mode
        mode = self.config.get('gps', 'sync_mode') or 'none'
        self._gps_mode_changing = True
        try:
            self.gps_sync_mode.set(mode)
            self._gps_sync_mode = mode  # スレッドセーフコピーも更新
        finally:
            self._gps_mode_changing = False

        # GPS interval index (validate)
        gps_interval_index = self.config.get('gps', 'sync_interval_index')
        try:
            gps_interval_index = int(gps_interval_index) if gps_interval_index is not None else None
        except (ValueError, TypeError):
            gps_interval_index = None

        gps_values = list(self.gps_interval_combo['values'])
        if gps_values and gps_interval_index is not None and 0 <= gps_interval_index < len(gps_values):
            try:
                self.gps_interval_combo.current(gps_interval_index)
                self._gps_interval_index = gps_interval_index
            except Exception:
                self.gps_interval_combo.current(2 if len(gps_values) > 2 else 0)
        else:
            default_gps_idx = 2 if len(gps_values) > 2 else (0 if gps_values else None)
            if default_gps_idx is not None:
                self.gps_interval_combo.current(default_gps_idx)

        # GPS interval モードなら起動時にタイマー再開
        if mode == 'interval':
            self.root.after(600, self._start_gps_interval_sync)

        # NTP server
        ntp_server = self.config.get('ntp', 'server')
        if ntp_server:
            self.ntp_entry.delete(0, tk.END)
            self.ntp_entry.insert(0, ntp_server)

        # NTP auto sync
        ntp_auto_val = self.config.get('ntp', 'auto_sync') or False
        self.ntp_auto_sync_var.set(ntp_auto_val)
        if ntp_auto_val:
            self.root.after(500, self._start_ntp_auto_sync)

        # NTP interval index (validate)
        ntp_interval_index = self.config.get('ntp', 'sync_interval_index')
        try:
            ntp_interval_index = int(ntp_interval_index) if ntp_interval_index is not None else None
        except (ValueError, TypeError):
            ntp_interval_index = None

        ntp_values = list(self.ntp_interval_combo['values'])
        if ntp_values and ntp_interval_index is not None and 0 <= ntp_interval_index < len(ntp_values):
            try:
                self.ntp_interval_combo.current(ntp_interval_index)
            except Exception:
                self.ntp_interval_combo.current(2 if len(ntp_values) > 2 else 0)
        else:
            default_ntp_idx = 2 if len(ntp_values) > 2 else (0 if ntp_values else None)
            if default_ntp_idx is not None:
                self.ntp_interval_combo.current(default_ntp_idx)

        # FT8 offset
        try:
            offset_val = float(self.config.get('ft8', 'time_offset_seconds') or 0.0)
        except (ValueError, TypeError):
            offset_val = 0.0
        self.sync.set_offset(offset_val)

        # debug flag
        self.debug_var.set(self.config.get('debug') or False)

    def _load_settings(self):
        """設定を読み込み"""
        if self.config.load():
            self._load_settings_to_ui()
            messagebox.showinfo(self.loc.get('app_title') or "Success",
                                self.loc.get('settings_loaded') or "Settings loaded successfully!")
        else:
            messagebox.showerror(self.loc.get('app_title') or "Error",
                                 self.loc.get('settings_load_failed') or "Failed to load settings")

    def _reset_settings(self):
        """設定をデフォルトに戻す"""
        if messagebox.askyesno(self.loc.get('app_title') or "Confirm", self.loc.get(
                'settings_reset_confirm') or "Reset all settings to default?\nすべての設定をデフォルトに戻しますか？"):
            self.config.reset()
            self._load_settings_to_ui()
            messagebox.showinfo(self.loc.get('app_title') or "Success",
                                self.loc.get('settings_reset') or "Settings reset to default!")

    def _update_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.port_combo['values'] = ports
        if ports:
            try:
                self.port_combo.current(0)
            except Exception:
                pass

    def _log(self, message):
        self.log_text.config(state='normal')
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')

    def _update_system_time(self):
        now = datetime.now(timezone.utc)
        self.system_time_value.config(text=now.strftime("%Y-%m-%d %H:%M:%S UTC"))

        # GPS時刻：受信した整数秒を monotonic で今に追従させる
        if self._gps_rx_dt is not None and self._gps_rx_mono is not None:
            age = time.monotonic() - self._gps_rx_mono
            if age < 10.0:  # 10秒以上古いなら表示しない
                gps_now = self._gps_rx_dt + timedelta(seconds=age)
                self.gps_time_value.config(
                    text=gps_now.strftime("%Y-%m-%d %H:%M:%S UTC"))

                # Δ(System - GPS) を時刻誤差ラベルに表示
                if hasattr(self, 'offset_value'):
                    delta = (now - gps_now).total_seconds()
                    if abs(delta) < 1.0:
                        color = '#00aa00'
                    elif abs(delta) < 3.0:
                        color = '#aaaa00'
                    else:
                        color = '#cc0000'
                    self.offset_value.config(
                        text=f"{delta:+.3f} s", foreground=color)
            else:
                self.gps_time_value.config(text="–")

        self.root.after(200, self._update_system_time)

    def _update_position_info(self):
        """位置情報を更新"""
        if self.is_running:
            if self.parser.grid_locator:
                self.grid_value.config(text=self.parser.grid_locator)

            if self.parser.latitude is not None:
                lat_str = f"{abs(self.parser.latitude):.6f}° {'N' if self.parser.latitude >= 0 else 'S'}"
                self.lat_value.config(text=lat_str)

            if self.parser.longitude is not None:
                lon_str = f"{abs(self.parser.longitude):.6f}° {'E' if self.parser.longitude >= 0 else 'W'}"
                self.lon_value.config(text=lon_str)

            if self.parser.altitude is not None:
                alt_str = f"{self.parser.altitude:.1f} m"
                self.alt_value.config(text=alt_str)

        self.root.after(1000, self._update_position_info)

    def _update_satellite_info(self):
        """衛星情報表示を更新（正確なカウント）"""
        if self.is_running:
            by_system = self.parser.get_satellites_by_system()

            # 正確なカウント（SNR閾値を考慮）
            strong = 0     # SNR >= 20（GNSS主星）
            weak = 0       # 10 <= SNR < 20（GNSS主星）
            sbas_used = 0  # SBAS使用中
            total = 0

            for system, sats in by_system.items():
                for sat in sats:
                    total += 1
                    if sat['in_use']:
                        if system == 'SBAS':
                            sbas_used += 1
                        elif sat['snr'] >= 20:
                            strong += 1
                        elif sat['snr'] >= 10:
                            weak += 1

            in_use = strong + weak

            # デバッグ出力
            if self.debug_var.get():
                print(f"[DEBUG] 衛星数: 使用中={in_use} (強:{strong}, 弱:{weak}), SBAS={sbas_used}, 合計={total}")
                print(f"[DEBUG] satellites辞書: {len(self.parser.satellites)}個")
                print(f"[DEBUG] satellites_in_use: {self.parser.satellites_in_use}")

            # 表示更新（GNSS主星 / SBAS補強を分けて表示）
            if sbas_used > 0:
                self.sat_inuse_value.config(
                    text=f"{in_use + sbas_used}  (GNSS: {in_use} / SBAS: {sbas_used})")
            elif strong > 0 and weak > 0:
                self.sat_inuse_value.config(text=f"{in_use} ({strong}+{weak})")
            else:
                self.sat_inuse_value.config(text=str(in_use))

            self.sat_total_value.config(text=str(total))

            # デバッグ出力
            if self.debug_var.get():
                for system, sats in by_system.items():
                    print(f"[DEBUG] {system}: {len(sats)}個")
                    if len(sats) > 0:
                        print(f"[DEBUG]   最初の衛星: {sats[0]}")

            # ツリー更新
            self._update_tree(self.gps_tree, by_system.get('GPS', []))
            self._update_tree(self.sbas_tree, by_system.get('SBAS', []))
            self._update_tree(self.glo_tree, by_system.get('GLONASS', []))
            self._update_tree(self.bei_tree, by_system.get('BeiDou', []))
            self._update_tree(self.galileo_tree, by_system.get('Galileo', []))
            self._update_tree(self.qzss_tree, by_system.get('QZSS', []))

        self.root.after(1000, self._update_satellite_info)

    def _update_tree(self, tree, satellites):
        """ツリービューを更新（3段階表示）"""
        for item in tree.get_children():
            tree.delete(item)

        for sat in satellites:
            values = (sat.get('id'), sat.get('snr'), sat.get('elevation'), sat.get('azimuth'))

            if sat.get('in_use') and sat.get('snr', 0) >= 20:
                # 強い信号で使用中（濃い緑）
                item = tree.insert('', tk.END, values=values, tags=('strong',))
            elif sat.get('in_use') and sat.get('snr', 0) >= 10:
                # 弱い信号で使用中（薄い緑）
                item = tree.insert('', tk.END, values=values, tags=('weak',))
            else:
                # 未使用または信号弱すぎ（白）
                item = tree.insert('', tk.END, values=values)

        # 色設定
        tree.tag_configure('strong', background='#90EE90')  # 濃い緑（ライトグリーン）
        tree.tag_configure('weak', background='#D0F0D0')    # 薄い緑（ペールグリーン）

    def _start(self):
        port = self.port_combo.get()
        try:
            baud = int(self.baud_combo.get())
        except (ValueError, TypeError):
            baud = 9600

        if not port:
            messagebox.showerror(
                self.loc.get('app_title') or "Error",
                self.loc.get('select_port') or "Please select COM port")
            return

        try:
            self.serial_port = serial.Serial(port, baud, timeout=1)
            self.is_running = True
            self.widgets['start_btn'].config(state='disabled')
            self.widgets['stop_btn'].config(state='normal')
            self.widgets['sync_gps_btn'].config(state='normal')

            if self.gps_sync_mode.get() != 'none':
                self._log(f"{self.loc.get('gps_started_log') or 'GPS started'}: {port} @ {baud}bps")

            if self.gps_sync_mode.get() == 'interval':
                self._start_gps_interval_sync()

            self.gps_thread = threading.Thread(target=self._read_gps, daemon=True)
            self.gps_thread.start()

        except Exception as e:
            port_err = self.loc.get('port_error') or 'Port error'
            messagebox.showerror(
                self.loc.get('app_title') or "Error", f"{port_err}: {e}")

    def _stop(self):
        self.is_running = False
        if self.serial_port:
            self.serial_port.close()

        self._stop_gps_auto_sync()

        self.widgets['start_btn'].config(state='normal')
        self.widgets['stop_btn'].config(state='disabled')
        self.widgets['sync_gps_btn'].config(state='disabled')
        self._log(self.loc.get('gps_stopped_log') or "GPS stopped")

    def _read_gps(self):
        last_log_msg = ""
        last_sync_system_second = None  # 最後に同期したシステム時刻の秒を記録

        while self.is_running:
            try:
                line = self.serial_port.readline().decode('ascii', errors='ignore').strip()
                if line:
                    # デバッグ出力（GSA, GSV, RMC, GGAメッセージ）
                    if self.debug_enabled:
                        if 'GSA' in line:
                            self._log(f"🔍 GSA: {line}")
                        elif 'GSV' in line:
                            print(f"[DEBUG-GSV] {line}")
                        elif 'RMC' in line:
                            self._log(f"🕐 RMC: {line}")
                        elif 'GGA' in line:
                            self._log(f"📍 GGA: {line}")

                    gps_time = self.parser.parse(line)
                    if gps_time:
                        self.ui_queue.put(('gps_time', gps_time, time.monotonic()))

                        if self._gps_sync_mode == 'instant':
                            current_system_second = datetime.now().replace(microsecond=0)

                            if last_sync_system_second == current_system_second:
                                continue

                            if self.sync.is_admin:
                                success, msg = self.sync.sync_time(gps_time)

                                if success:
                                    last_sync_system_second = current_system_second

                                    if "大幅修正" in msg:
                                        self.ui_queue.put(('log', f"⏰ {msg}"))
                                        last_log_msg = msg
                                    elif "微調整" in msg and msg != last_log_msg:
                                        self.ui_queue.put(('log', f"⏰ {msg}"))
                                        last_log_msg = msg
                                    elif "正確" in msg:
                                        if "正確" not in last_log_msg:
                                            self.ui_queue.put(('log', f"✓ {msg}"))
                                        last_log_msg = msg
                                else:
                                    self.ui_queue.put(('log',
                                                       f"✗ {self.loc.get('sync_failed') or 'Sync failed'}: {msg}"))
                            else:
                                self.ui_queue.put(('log',
                                                   f"⚠ {self.loc.get('admin_required') or 'Administrator required'}"))
                                self._gps_sync_mode = 'none'
                                self.ui_queue.put(('gps_mode_reset', None))

                        elif self._gps_sync_mode == 'interval':
                            # 期限が未設定なら今すぐ許可
                            if self._gps_next_sync_mono is None:
                                self._gps_next_sync_mono = time.monotonic()

                            if self.sync.is_admin:
                                # 毎秒サンプルを蓄積（期限に関係なく常時）
                                self.sync.add_sample(gps_time)

                                # 期限到達時のみ判断・ログ・期限更新
                                if time.monotonic() >= self._gps_next_sync_mono:
                                    success, msg = self.sync.sync_time_weak(gps_time, append_sample=False)
                                    if success:
                                        self.ui_queue.put(('log', f"⏰ GPS {self.loc.get('sync_success') or 'Sync success'}: {msg}"))
                                    else:
                                        self.ui_queue.put(('log',
                                                           f"✗ GPS {self.loc.get('sync_failed') or 'Sync failed'}: {msg}"))

                                    # 次回期限を更新
                                    try:
                                        interval_minutes = [5, 10, 30, 60, 360][self._gps_interval_index]
                                    except Exception:
                                        interval_minutes = 30
                                    self._gps_next_sync_mono = time.monotonic() + interval_minutes * 60.0
                            else:
                                self.ui_queue.put(('log',
                                                   f"⚠ {self.loc.get('admin_required') or 'Administrator required'}"))
                                self._gps_sync_mode = 'none'
                                self.ui_queue.put(('gps_mode_reset', None))

            except Exception as e:
                self._log(f"❌ Error: {e}")

    def _sync_gps(self):
        if not self.parser.last_time:
            messagebox.showwarning(self.loc.get('app_title') or "Warning", self.loc.get('no_gps_time') or "No GPS time")
            return

        if not self.sync.is_admin:
            messagebox.showerror(self.loc.get('app_title') or "Error",
                                 self.loc.get('admin_required') or "Administrator privileges required")
            return

        success, msg = self.sync.sync_time(self.parser.last_time)
        if success:
            self._log(f"✓ GPS {self.loc.get('sync_success') or 'Sync success'}: {msg}")
            messagebox.showinfo(self.loc.get('app_title') or "Success", self.loc.get('sync_success') or "Sync success")
        else:
            self._log(f"✗ {self.loc.get('sync_failed') or 'Sync failed'}: {msg}")
            messagebox.showerror(self.loc.get('app_title') or "Error", msg)

    def _check_admin_on_startup(self):
        """起動時に管理者権限を確認し、なければ選択肢を提示する"""
        title = self.loc.get('not_admin_title') or 'Administrator Required'
        message = self.loc.get('not_admin_message') or (
            'Administrator privileges are required to sync the system clock.\n'
            'Would you like to restart as administrator?\n\n'
            'Choosing "No" starts in Monitor-Only mode\n'
            '(GPS/NTP display only, time sync disabled).'
        )
        btn_restart = self.loc.get('not_admin_restart') or 'Restart as Administrator'
        btn_monitor = self.loc.get('not_admin_monitor') or 'Continue in Monitor Mode'

        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.transient(self.root)
        dialog.resizable(False, False)
        dialog.grab_set()

        dialog.update_idletasks()
        w, h = 480, 200
        x = max(0, self.root.winfo_x() + (self.root.winfo_width() - w) // 2)
        y = max(0, self.root.winfo_y() + (self.root.winfo_height() - h) // 2)
        dialog.geometry(f"{w}x{h}+{x}+{y}")

        frame = ttk.Frame(dialog, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text="⚠", font=('Arial', 24)).pack(side=tk.LEFT, anchor='n', padx=(0, 12))
        ttk.Label(frame, text=message, justify=tk.LEFT, wraplength=380).pack(side=tk.LEFT, anchor='n')

        btn_frame = ttk.Frame(dialog, padding=(0, 0, 16, 12))
        btn_frame.pack(side=tk.BOTTOM, anchor='e')

        def do_restart():
            dialog.destroy()
            success, msg = self.autostart.restart_as_admin()
            if success:
                self._on_closing()
            else:
                messagebox.showerror(title, msg)
                self._apply_monitor_mode()

        def do_monitor():
            dialog.destroy()
            self._apply_monitor_mode()

        ttk.Button(btn_frame, text=btn_restart, command=do_restart).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text=btn_monitor, command=do_monitor).pack(side=tk.LEFT, padx=4)
        dialog.protocol("WM_DELETE_WINDOW", do_monitor)

        self.root.wait_window(dialog)

    # =========================================================================
    # v2.5 (案2) 追加：Unlock Sync バナー制御 + 昇格再起動
    # =========================================================================

    def _update_unlock_banner_visibility(self):
        """非管理者時に Unlock バナーを表示、管理者時は非表示"""
        try:
            if not hasattr(self, "_unlock_banner"):
                return
            is_admin = bool(getattr(self.sync, "is_admin", False))
            if is_admin:
                self._unlock_banner.pack_forget()
            else:
                if not self._unlock_banner.winfo_ismapped():
                    self._unlock_banner.pack(fill=tk.X, pady=(0, 8),
                                             before=self._unlock_banner.master.winfo_children()[1]
                                             if len(self._unlock_banner.master.winfo_children()) > 1
                                             else None)
        except Exception:
            pass

    def on_unlock_sync(self):
        """監視起動 → ユーザー操作で昇格再起動（handoff）"""
        title = self.loc.get('app_title') or "ChronoGPS"

        # 既に管理者なら何もしない
        if getattr(self.sync, "is_admin", False):
            self._log("v2.5: already elevated; unlock banner ignored.")
            self._update_unlock_banner_visibility()
            return

        if admin is None:
            messagebox.showerror(title, "admin.py not available.")
            return

        self._log("v2.5: unlock requested; launching elevated (handoff, mode=sync)")

        try:
            # ElevationResult を返す（タプルではない）← Step2のAPI仕様に合わせる
            res = admin.launch_elevated_and_confirm(
                mode="sync",
                handoff=True,
                timeout_sec=10.0,
            )
            ok = res.waited_confirmed
            msg = res.reason
        except Exception as e:
            ok = False
            msg = f"launch_elevated_and_confirm failed: {e}"

        # 必ずログに残す（Must）
        self._log(f"v2.5: launch result ok={ok} msg={msg}")

        if not ok:
            # v2.5 Fix: UACキャンセル時はエラーダイアログを出さず、監視モード継続（ログのみ）
            self._log("v2.5: UAC cancelled or failed. Monitor mode continues.")
            return

        # 成功したら現プロセスを確実に閉じる（ゾンビ防止）
        self._on_closing()

    # =========================================================================

    def _apply_monitor_mode(self):
        """モニタ専用モード：同期系ボタンを無効化してログに表示"""
        for key in ('sync_gps_btn', 'sync_ntp_btn'):
            if key in self.widgets:
                self.widgets[key].config(state='disabled')

        for mode in ('instant', 'interval'):
            if mode in self.gps_sync_radios:
                self.gps_sync_radios[mode].config(state='disabled')

        if 'ntp_auto_check' in self.widgets:
            self.widgets['ntp_auto_check'].config(state='disabled')

        for key in ('ft8_apply_btn', 'ft8_reset_btn'):
            if key in self.widgets:
                self.widgets[key].config(state='disabled')

        # ログに通知（wait_window 解放後に実行されるよう遅延）
        msg = self.loc.get('monitor_mode_log') or '⚠ Monitor-Only mode (time sync disabled)'
        self.root.after(100, lambda: self._log(msg))

        # v2.5: バナー表示更新
        self.root.after(150, self._update_unlock_banner_visibility)

    def _on_closing(self):
        """終了時の処理"""
        # v2.5: 二重実行ガード
        if getattr(self, "_closing", False):
            return
        self._closing = True

        # v2.5: ShutdownManager に終了開始を通知
        try:
            if self.shutdown_mgr is not None:
                self.shutdown_mgr._started = False  # 再利用のためリセット
        except Exception:
            pass

        # 設定を自動保存（ダイアログなし）
        self._save_settings(silent=True)

        # GPS受信停止
        if self.is_running:
            self._stop()

            # --- 追加：GPSスレッド終了を待つ（最大2秒） ---
            try:
                if getattr(self, "gps_thread", None) and self.gps_thread.is_alive():
                    self.gps_thread.join(timeout=2.0)
            except Exception:
                pass

        # タイマー停止
        if self.gps_sync_timer:
            self.root.after_cancel(self.gps_sync_timer)
        if self.ntp_sync_timer:
            self.root.after_cancel(self.ntp_sync_timer)
        # FT8 offset 表示タイマー停止
        self._stop_offset_timer()

        # v2.5: UIキュー after を停止
        if getattr(self, "_ui_queue_timer_id", None):
            try:
                self.root.after_cancel(self._ui_queue_timer_id)
            except Exception:
                pass
            self._ui_queue_timer_id = None

        # システムトレイ停止
        self.tray.stop()

        self.root.destroy()


def main():
    root = tk.Tk()

    # Window icon (Windows)
    try:
        import os
        root.iconbitmap(os.path.join(os.path.dirname(__file__), "icon.ico"))
    except Exception:
        pass

    app = GPSTimeSyncGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
