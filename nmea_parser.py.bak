"""
NMEA 0183パーサー（完全版：GPS, GLONASS, BeiDou, Galileo, SBAS/MSAS対応）
システムIDベースの正確な分類 + 時刻重複同期防止
"""
from datetime import datetime, timezone

class NMEAParser:
    def __init__(self):
        self.last_time = None
        self.latitude = None
        self.longitude = None
        self.altitude = None
        self.grid_locator = None
        self.satellites_in_use = {}  # {sat_id: system_id} 形式に変更
        self.satellites = {}
        self.last_time_update = None  # 時刻更新の重複防止用
    
    def parse(self, nmea_sentence):
        """NMEAセンテンスを解析"""
        if not nmea_sentence.startswith('$'):
            return None
        
        parts = nmea_sentence.split(',')
        msg_type = parts[0]
        
        # 時刻情報 (RMC のみ - GGAは位置情報のみ)
        if msg_type in ['$GPRMC', '$GNRMC']:
            return self._parse_rmc(parts)
        
        # 位置情報 (GGA)
        elif msg_type in ['$GPGGA', '$GNGGA']:
            self._parse_gga(parts)
            return None  # 時刻は返さない（重複防止）
        
        # 使用中の衛星 (GSA) - システムID付き
        elif 'GSA' in msg_type:
            self._parse_gsa(parts)
        
        # 衛星情報 (GSV) - システム別
        elif 'GSV' in msg_type:
            self._parse_gsv(parts, msg_type)
        
        return None
    
    def _parse_rmc(self, parts):
        """RMCセンテンス解析（時刻のみ返す）"""
        try:
            if len(parts) < 10 or parts[2] != 'A':
                return None
            
            time_str = parts[1]
            date_str = parts[9]
            
            if len(time_str) >= 6 and len(date_str) == 6:
                dt = datetime.strptime(date_str + time_str[:6], "%d%m%y%H%M%S")
                dt = dt.replace(tzinfo=timezone.utc)
                
                # 同じ時刻が既に返されていたら返さない
                if self.last_time_update == dt:
                    return None
                
                self.last_time = dt
                self.last_time_update = dt
                
                # 位置情報
                if parts[3] and parts[5]:
                    self.latitude = self._parse_coordinate(parts[3], parts[4])
                    self.longitude = self._parse_coordinate(parts[5], parts[6])
                    self._calculate_grid_locator()
                
                return dt
        except:
            pass
        return None
    
    def _parse_gga(self, parts):
        """GGAセンテンス解析（位置と高度のみ）"""
        try:
            if len(parts) < 15:
                return
            
            # 位置情報
            if parts[2] and parts[4]:
                self.latitude = self._parse_coordinate(parts[2], parts[3])
                self.longitude = self._parse_coordinate(parts[4], parts[5])
                self._calculate_grid_locator()
            
            # 高度
            if parts[9]:
                self.altitude = float(parts[9])
        except:
            pass
    
    def _parse_gsa(self, parts):
        """GSAセンテンス解析（使用中の衛星 + システムID）"""
        try:
            if len(parts) < 18:
                return
            
            # 最後のフィールド（チェックサム付き）からシステムIDを取得
            # 例: "1.40,0.65,1.24,1*0F" → システムID = 1
            last_field = parts[-1].split('*')[0] if '*' in parts[-1] else parts[-1]
            
            try:
                system_id = int(last_field)
            except:
                system_id = 1  # デフォルトはGPS
            
            # 使用中の衛星ID（フィールド3-14）
            for i in range(3, 15):
                if parts[i]:
                    sat_id = parts[i].zfill(2)
                    self.satellites_in_use[sat_id] = system_id
        except:
            pass
    
    def _parse_gsv(self, parts, msg_type):
        """GSVセンテンス解析（衛星情報 + システム判定）"""
        try:
            if len(parts) < 8:
                return
            
            # メッセージタイプからシステムを判定
            # $GPGSV = GPS, $GLGSV = GLONASS, $GAGSV = Galileo, $GBGSV = BeiDou
            if msg_type.startswith('$GP'):
                system_id = 1  # GPS
            elif msg_type.startswith('$GL'):
                system_id = 2  # GLONASS
            elif msg_type.startswith('$GA'):
                system_id = 3  # Galileo
            elif msg_type.startswith('$GB'):
                system_id = 4  # BeiDou
            elif msg_type.startswith('$GN'):
                system_id = 0  # 混合（個別判定が必要）
            else:
                system_id = 1  # デフォルトGPS
            
            # 衛星情報（4個ずつ）
            for i in range(4, len(parts) - 3, 4):
                if not parts[i]:
                    continue
                
                sat_id = parts[i].zfill(2)
                elevation = int(parts[i+1]) if parts[i+1] else 0
                azimuth = int(parts[i+2]) if parts[i+2] else 0
                snr = int(parts[i+3].split('*')[0]) if parts[i+3] and parts[i+3].split('*')[0] else 0
                
                # システムIDが0（混合）の場合は衛星番号で判定
                if system_id == 0:
                    sat_num = int(sat_id)
                    if sat_num <= 32:
                        system_id = 1  # GPS
                    elif 33 <= sat_num <= 64 or 120 <= sat_num <= 158:
                        system_id = 5  # SBAS
                    elif 65 <= sat_num <= 96:
                        system_id = 2  # GLONASS
                    else:
                        system_id = 1  # デフォルト
                
                self.satellites[sat_id] = {
                    'id': sat_id,
                    'elevation': elevation,
                    'azimuth': azimuth,
                    'snr': snr,
                    'system_id': system_id,
                    'in_use': sat_id in self.satellites_in_use
                }
        except:
            pass
    
    def get_satellites_by_system(self):
        """衛星をシステム別に分類（システムIDベース）"""
        result = {
            'GPS': [],
            'SBAS': [],
            'GLONASS': [],
            'BeiDou': [],
            'Galileo': []
        }
        
        for sat_id, sat_info in self.satellites.items():
            system_id = sat_info.get('system_id', 1)
            sat_num = int(sat_id)
            
            # システムIDで分類
            if system_id == 1:
                # GPS
                if sat_num <= 32:
                    result['GPS'].append(sat_info)
                # GPS範囲外の番号はSBASの可能性
                elif 33 <= sat_num <= 64 or 120 <= sat_num <= 158:
                    result['SBAS'].append(sat_info)
                else:
                    result['GPS'].append(sat_info)
            
            elif system_id == 2:
                # GLONASS
                result['GLONASS'].append(sat_info)
            
            elif system_id == 3:
                # Galileo
                result['Galileo'].append(sat_info)
            
            elif system_id == 4:
                # BeiDou
                result['BeiDou'].append(sat_info)
            
            elif system_id == 5:
                # SBAS（明示的）
                result['SBAS'].append(sat_info)
            
            else:
                # 不明な場合は衛星番号で推測
                if sat_num <= 32:
                    result['GPS'].append(sat_info)
                elif 33 <= sat_num <= 64 or 120 <= sat_num <= 158:
                    result['SBAS'].append(sat_info)
                elif 65 <= sat_num <= 96:
                    result['GLONASS'].append(sat_info)
                else:
                    result['GPS'].append(sat_info)
        
        # 各システムの衛星をIDでソート
        for system in result:
            result[system].sort(key=lambda x: int(x['id']))
        
        return result
    
    def get_satellite_count(self):
        """衛星数を取得"""
        in_use = len(self.satellites_in_use)
        total = len(self.satellites)
        return in_use, total
    
    def _parse_coordinate(self, coord_str, direction):
        """座標文字列を10進数に変換"""
        try:
            if not coord_str:
                return None
            
            # 度分形式を10進数に変換
            if len(coord_str) > 4:
                if '.' in coord_str:
                    dot_pos = coord_str.index('.')
                    if direction in ['N', 'S']:
                        degrees = int(coord_str[:dot_pos-2])
                        minutes = float(coord_str[dot_pos-2:])
                    else:
                        degrees = int(coord_str[:dot_pos-2])
                        minutes = float(coord_str[dot_pos-2:])
                    
                    decimal = degrees + minutes / 60.0
                    
                    if direction in ['S', 'W']:
                        decimal = -decimal
                    
                    return decimal
        except:
            pass
        return None
    
    def _calculate_grid_locator(self):
        """Maidenhead Grid Locatorを計算（10桁高精度版）"""
        if self.latitude is None or self.longitude is None:
            return
        
        try:
            lon = self.longitude + 180
            lat = self.latitude + 90
            
            grid = ''
            
            # 1-2桁目：フィールド（A-R）
            grid += chr(int(lon / 20) + ord('A'))
            grid += chr(int(lat / 10) + ord('A'))
            
            # 3-4桁目：スクエア（0-9）
            grid += str(int((lon % 20) / 2))
            grid += str(int(lat % 10))
            
            # 5-6桁目：サブスクエア（a-x）
            grid += chr(int((lon % 2) / (2/24)) + ord('a'))
            grid += chr(int((lat % 1) / (1/24)) + ord('a'))
            
            # 7-8桁目：拡張スクエア（0-9）
            grid += str(int((lon % (2/24)) / (2/240)))
            grid += str(int((lat % (1/24)) / (1/240)))
            
            # 9-10桁目：拡張サブスクエア（a-x）
            grid += chr(int((lon % (2/240)) / (2/5760)) + ord('a'))
            grid += chr(int((lat % (1/240)) / (1/5760)) + ord('a'))
            
            self.grid_locator = grid.upper()
        except:
            pass