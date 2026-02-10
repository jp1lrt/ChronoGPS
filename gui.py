"""
GPS/NTP 時刻同期ツール GUI
"""
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import serial.tools.list_ports
import threading
import serial
from datetime import datetime, timezone
from nmea_parser import NMEAParser
from ntp_client import NTPClient
from time_sync import TimeSynchronizer

class GPSTimeSyncGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("GPS/NTP 時刻同期ツール - Windows 11対応")
        self.root.geometry("800x600")
        
        self.parser = NMEAParser()
        self.ntp_client = NTPClient()
        self.sync = TimeSynchronizer()
        
        self.serial_port = None
        self.is_running = False
        
        self._create_widgets()
        self._update_ports()
        
    def _create_widgets(self):
        # メインフレーム
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # GPS設定
        gps_frame = ttk.LabelFrame(main_frame, text="GPS設定", padding="10")
        gps_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        ttk.Label(gps_frame, text="COMポート:").grid(row=0, column=0, sticky=tk.W)
        self.port_combo = ttk.Combobox(gps_frame, width=15, state='readonly')
        self.port_combo.grid(row=0, column=1, padx=5)
        
        ttk.Button(gps_frame, text="更新", command=self._update_ports).grid(row=0, column=2, padx=5)
        
        ttk.Label(gps_frame, text="ボーレート:").grid(row=0, column=3, sticky=tk.W, padx=(20, 0))
        self.baud_combo = ttk.Combobox(gps_frame, width=10, state='readonly', values=['4800', '9600', '19200', '38400', '57600', '115200'])
        self.baud_combo.current(1)  # 9600
        self.baud_combo.grid(row=0, column=4, padx=5)
        
        # NTP設定
        ntp_frame = ttk.LabelFrame(main_frame, text="NTP設定", padding="10")
        ntp_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        ttk.Label(ntp_frame, text="NTPサーバー:").grid(row=0, column=0, sticky=tk.W)
        self.ntp_entry = ttk.Entry(ntp_frame, width=30)
        self.ntp_entry.insert(0, "pool.ntp.org")
        self.ntp_entry.grid(row=0, column=1, padx=5)
        
        # ボタン
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=2, column=0, columnspan=2, pady=10)
        
        self.start_btn = ttk.Button(button_frame, text="開始", command=self._start)
        self.start_btn.grid(row=0, column=0, padx=5)
        
        self.stop_btn = ttk.Button(button_frame, text="停止", command=self._stop, state='disabled')
        self.stop_btn.grid(row=0, column=1, padx=5)
        
        self.sync_gps_btn = ttk.Button(button_frame, text="GPS時刻で同期", command=self._sync_gps, state='disabled')
        self.sync_gps_btn.grid(row=0, column=2, padx=5)
        
        self.sync_ntp_btn = ttk.Button(button_frame, text="NTP時刻で同期", command=self._sync_ntp)
        self.sync_ntp_btn.grid(row=0, column=3, padx=5)
        
        # ステータス表示
        status_frame = ttk.LabelFrame(main_frame, text="ステータス", padding="10")
        status_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        ttk.Label(status_frame, text="システム時刻:").grid(row=0, column=0, sticky=tk.W)
        self.system_time_label = ttk.Label(status_frame, text="-")
        self.system_time_label.grid(row=0, column=1, sticky=tk.W, padx=10)
        
        ttk.Label(status_frame, text="GPS時刻:").grid(row=1, column=0, sticky=tk.W)
        self.gps_time_label = ttk.Label(status_frame, text="-")
        self.gps_time_label.grid(row=1, column=1, sticky=tk.W, padx=10)
        
        ttk.Label(status_frame, text="NTP時刻:").grid(row=2, column=0, sticky=tk.W)
        self.ntp_time_label = ttk.Label(status_frame, text="-")
        self.ntp_time_label.grid(row=2, column=1, sticky=tk.W, padx=10)
        
        # ログ
        log_frame = ttk.LabelFrame(main_frame, text="ログ", padding="10")
        log_frame.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=15, state='disabled')
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # リサイズ設定
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(4, weight=1)
        
        # 時刻更新タイマー
        self._update_system_time()
        
    def _update_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.port_combo['values'] = ports
        if ports:
            self.port_combo.current(0)
    
    def _log(self, message):
        self.log_text.config(state='normal')
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')
    
    def _update_system_time(self):
        now = datetime.now(timezone.utc)
        self.system_time_label.config(text=now.strftime("%Y-%m-%d %H:%M:%S UTC"))
        self.root.after(1000, self._update_system_time)
    
    def _start(self):
        port = self.port_combo.get()
        baud = int(self.baud_combo.get())
        
        if not port:
            messagebox.showerror("エラー", "COMポートを選択してください")
            return
        
        try:
            self.serial_port = serial.Serial(port, baud, timeout=1)
            self.is_running = True
            self.start_btn.config(state='disabled')
            self.stop_btn.config(state='normal')
            self.sync_gps_btn.config(state='normal')
            
            self._log(f"GPS受信開始: {port} @ {baud}bps")
            
            # GPS読み取りスレッド開始
            self.gps_thread = threading.Thread(target=self._read_gps, daemon=True)
            self.gps_thread.start()
            
        except Exception as e:
            messagebox.showerror("エラー", f"ポートを開けません: {e}")
    
    def _stop(self):
        self.is_running = False
        if self.serial_port:
            self.serial_port.close()
        
        self.start_btn.config(state='normal')
        self.stop_btn.config(state='disabled')
        self.sync_gps_btn.config(state='disabled')
        self._log("GPS受信停止")
    
    def _read_gps(self):
        while self.is_running:
            try:
                line = self.serial_port.readline().decode('ascii', errors='ignore').strip()
                if line:
                    gps_time = self.parser.parse(line)
                    if gps_time:
                        self.gps_time_label.config(text=gps_time.strftime("%Y-%m-%d %H:%M:%S UTC"))
            except Exception as e:
                self._log(f"GPS読み取りエラー: {e}")
    
    def _sync_gps(self):
        if not self.parser.last_time:
            messagebox.showwarning("警告", "GPS時刻が取得できていません")
            return
        
        if not self.sync.is_admin:
            messagebox.showerror("エラー", "管理者権限で実行してください")
            return
        
        success, msg = self.sync.sync_time(self.parser.last_time)
        if success:
            self._log(f"✓ GPS時刻で同期: {msg}")
            messagebox.showinfo("成功", "GPS時刻で同期しました")
        else:
            self._log(f"✗ 同期失敗: {msg}")
            messagebox.showerror("エラー", msg)
    
    def _sync_ntp(self):
        server = self.ntp_entry.get()
        self.ntp_client.set_server(server)
        
        self._log(f"NTP時刻取得中: {server}")
        ntp_time, offset = self.ntp_client.get_time()
        
        if ntp_time is None:
            messagebox.showerror("エラー", "NTP時刻が取得できませんでした")
            return
        
        self.ntp_time_label.config(text=ntp_time.strftime("%Y-%m-%d %H:%M:%S UTC"))
        self._log(f"NTP時刻: {ntp_time}, オフセット: {offset:.2f}ms")
        
        if not self.sync.is_admin:
            messagebox.showerror("エラー", "管理者権限で実行してください")
            return
        
        success, msg = self.sync.sync_time(ntp_time)
        if success:
            self._log(f"✓ NTP時刻で同期: {msg}")
            messagebox.showinfo("成功", "NTP時刻で同期しました")
        else:
            self._log(f"✗ 同期失敗: {msg}")
            messagebox.showerror("エラー", msg)