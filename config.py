"""
設定管理モジュール
JSON形式で設定を保存/読み込み
"""
import json
import os


class Config:
    def __init__(self, config_file='gps_time_sync_config.json'):
        self.config_file = config_file
        self.settings = self._load_default_settings()
        self.load()

    def _load_default_settings(self):
        """デフォルト設定"""
        return {
            # GPS設定
            'gps': {
                'com_port': '',
                'baud_rate': 9600,
                'auto_sync': False,
                'sync_mode': 'none',  # 'none', 'instant', 'interval'
                'sync_interval_index': 2,  # 0=5分, 1=10分, 2=30分, 3=1時間, 4=6時間
            },

            # NTP設定
            'ntp': {
                'server': 'pool.ntp.org',
                'auto_sync': False,
                'sync_interval_index': 2,  # 0=5分, 1=10分, 2=30分, 3=1時間, 4=6時間
            },

            # 言語設定
            'language': 'auto',  # 'auto' または言語コード

            # ウィンドウ設定
            'window': {
                'width': 950,
                'height': 750,
                'x': None,
                'y': None,
            },

            # デバッグモード
            'debug': False,

            # 起動時設定
            'startup': {
                'auto_start': False,  # Windows起動時に自動スタート
                'start_minimized': False,  # システムトレイに格納して起動
                'sync_on_startup': False,  # 起動時に同期
            },

            # ログ設定
            'logging': {
                'save_to_file': False,
                'log_file': 'gps_time_sync.log',
                'max_log_size_mb': 10,
            },

            # 通知設定
            'notifications': {
                'enabled': False,
                'notify_on_sync_fail': True,
                'notify_on_sync_success': False,
            },

            # FT8機能
            'ft8': {
                'time_offset_seconds': 0,  # ±秒数でずらす
            },
        }

    def load(self):
        """設定をファイルから読み込み"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    # デフォルト設定にマージ（新しいキーがあっても対応）
                    self._merge_settings(self.settings, loaded)
                    return True
        except Exception as e:
            print(f"設定読み込みエラー: {e}")
        return False

    def _merge_settings(self, default, loaded):
        """デフォルト設定に読み込んだ設定をマージ"""
        for key, value in loaded.items():
            if key in default:
                if isinstance(value, dict) and isinstance(default[key], dict):
                    self._merge_settings(default[key], value)
                else:
                    default[key] = value

    def save(self):
        """設定をファイルに保存"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"設定保存エラー: {e}")
            return False

    def get(self, *keys):
        """設定を取得（ネストされたキーに対応）"""
        value = self.settings
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return None
        return value

    def set(self, *keys, value):
        """設定を変更（ネストされたキーに対応）"""
        if len(keys) == 0:
            return False

        settings = self.settings
        for key in keys[:-1]:
            if key not in settings:
                settings[key] = {}
            settings = settings[key]

        settings[keys[-1]] = value
        return True

    def reset(self):
        """設定をデフォルトに戻す"""
        self.settings = self._load_default_settings()
        return self.save()


# テスト
if __name__ == "__main__":
    config = Config()

    # 設定の取得
    print(f"NTPサーバー: {config.get('ntp', 'server')}")
    print(f"ボーレート: {config.get('gps', 'baud_rate')}")

    # 設定の変更
    config.set('ntp', 'server', value='time.google.com')
    config.set('gps', 'com_port', value='COM3')

    # 保存
    config.save()
    print("設定を保存しました")

    # 読み込みテスト
    config2 = Config()
    print(f"読み込んだNTPサーバー: {config2.get('ntp', 'server')}")
