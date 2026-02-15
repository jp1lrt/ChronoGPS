"""
システムトレイアイコン管理モジュール
"""
import pystray
from PIL import Image, ImageDraw
import threading

class TrayIcon:
    def __init__(self, app_title="GPS Time Sync", on_show=None, on_quit=None):
        self.app_title = app_title
        self.on_show = on_show
        self.on_quit = on_quit
        self.icon = None
        self.is_running = False
        
    def create_icon_image(self, color='blue'):
        """トレイアイコン画像を作成"""
        # 64x64のアイコン画像を作成
        width = 64
        height = 64
        image = Image.new('RGB', (width, height), color='white')
        dc = ImageDraw.Draw(image)
        
        # 背景
        dc.rectangle([0, 0, width, height], fill=color)
        
        # 白い円（時計のイメージ）
        margin = 8
        dc.ellipse([margin, margin, width-margin, height-margin], fill='white', outline='black', width=2)
        
        # 時計の針
        center_x = width // 2
        center_y = height // 2
        dc.line([center_x, center_y, center_x, center_y - 15], fill='black', width=3)  # 短針
        dc.line([center_x, center_y, center_x + 10, center_y], fill='black', width=2)  # 長針
        
        # 中心点
        dc.ellipse([center_x-3, center_y-3, center_x+3, center_y+3], fill='red')
        
        return image
    
    def create_menu(self):
        """トレイアイコンのメニューを作成"""
        return pystray.Menu(
            pystray.MenuItem("Show / 表示", self._on_show_clicked),
            pystray.MenuItem("Quit / 終了", self._on_quit_clicked)
        )
    
    def _on_show_clicked(self, icon, item):
        """表示メニューがクリックされた時"""
        if self.on_show:
            self.on_show()
    
    def _on_quit_clicked(self, icon, item):
        """終了メニューがクリックされた時"""
        self.stop()
        if self.on_quit:
            self.on_quit()
    
    def start(self):
        """トレイアイコンを表示"""
        if self.is_running:
            return
        
        image = self.create_icon_image()
        menu = self.create_menu()
        
        self.icon = pystray.Icon(
            name="gps_time_sync",
            icon=image,
            title=self.app_title,
            menu=menu
        )
        
        self.is_running = True
        
        # 別スレッドで実行
        self.icon_thread = threading.Thread(target=self._run_icon, daemon=True)
        self.icon_thread.start()
    
    def _run_icon(self):
        """トレイアイコンを実行"""
        self.icon.run()
    
    def stop(self):
        """トレイアイコンを停止"""
        if self.icon and self.is_running:
            self.icon.stop()
            self.is_running = False
    
    def update_icon(self, color='blue'):
        """アイコンの色を変更"""
        if self.icon:
            self.icon.icon = self.create_icon_image(color)

# テスト
if __name__ == "__main__":
    import time
    
    def on_show():
        print("Show clicked!")
    
    def on_quit():
        print("Quit clicked!")
    
    tray = TrayIcon(on_show=on_show, on_quit=on_quit)
    tray.start()
    
    print("トレイアイコンが表示されました。右クリックしてメニューを確認してください。")
    print("10秒後に自動終了します...")
    
    time.sleep(10)
    tray.stop()
    print("終了しました。")