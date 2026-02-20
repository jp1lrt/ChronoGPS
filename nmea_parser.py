"""
NMEA 0183パーサー（論理再構築版）
- 10桁高精度グリッドロケーター維持
- Talker IDを絶対優先し、衛星番号による誤判定を排除
"""
from datetime import datetime, timezone


class NMEAParser:
    def __init__(self):
        self.last_time = None
        self.latitude = None
        self.longitude = None
        self.altitude = None
        self.grid_locator = None
        # (system_id, sat_id) のセットで管理
        self.satellites_in_use = set()
        self.satellites = {}
        self.last_time_update = None

    def parse(self, nmea_sentence):
        if not nmea_sentence.startswith('$'):
            return None
        parts = nmea_sentence.split(',')
        msg_type = parts[0]

        if 'RMC' in msg_type:
            return self._parse_rmc(parts)
        elif 'GGA' in msg_type:
            self._parse_gga(parts)
        elif 'GSA' in msg_type:
            self._parse_gsa(parts)
        elif 'GSV' in msg_type:
            self._parse_gsv(parts, msg_type)
        return None

    def _parse_rmc(self, parts):
        try:
            if len(parts) < 10 or parts[2] != 'A':
                return None
            dt = datetime.strptime(parts[9] + parts[1][:6], "%d%m%y%H%M%S").replace(tzinfo=timezone.utc)
            if self.last_time_update == dt:
                return None
            self.last_time = self.last_time_update = dt
            if parts[3] and parts[5]:
                self.latitude = self._parse_coordinate(parts[3], parts[4])
                self.longitude = self._parse_coordinate(parts[5], parts[6])
                self._calculate_grid_locator()
            return dt
        except BaseException:
            pass
        return None

    def _parse_gga(self, parts):
        try:
            if len(parts) > 9 and parts[2] and parts[4]:
                self.latitude = self._parse_coordinate(parts[2], parts[3])
                self.longitude = self._parse_coordinate(parts[4], parts[5])
                self._calculate_grid_locator()
            if len(parts) > 9 and parts[9]:
                self.altitude = float(parts[9])
        except BaseException:
            pass

    def _parse_gsa(self, parts):
        """使用中の衛星：Talker IDからシステムを厳密に特定"""
        try:
            msg_header = parts[0]
            if '$GP' in msg_header:
                sys_id = 1
            elif '$GL' in msg_header:
                sys_id = 2
            elif '$GA' in msg_header:
                sys_id = 3
            elif '$GB' in msg_header:
                sys_id = 4
            elif '$GQ' in msg_header:
                sys_id = 6
            else:
                # $GNの場合は末尾のSystem IDを見る
                last_field = parts[-1].split('*')[0]
                sys_id = int(last_field) if last_field.isdigit() else 1

            for i in range(3, 15):
                if parts[i]:
                    self.satellites_in_use.add((sys_id, parts[i].zfill(2)))
        except BaseException:
            pass

    def _parse_gsv(self, parts, msg_type):
        """衛星情報：Talker IDが示すシステムを信じ、番号での上書きをしない"""
        try:
            if len(parts) < 8:
                return

            # Talker IDによる絶対判定
            if '$GP' in msg_type:
                sys_id = 1    # GPS
            elif '$GL' in msg_type:
                sys_id = 2  # GLONASS
            elif '$GA' in msg_type:
                sys_id = 3  # Galileo
            elif '$GB' in msg_type:
                sys_id = 4  # BeiDou
            elif '$GQ' in msg_type:
                sys_id = 6  # QZSS
            else:
                sys_id = 1  # 不明はGPSへ

            for i in range(4, len(parts) - 3, 4):
                if not parts[i]:
                    continue
                sat_id = parts[i].zfill(2)

                # SBAS（33-64, 120-158）だけはGPS($GP)の中で例外処理
                current_sys = sys_id
                sat_num = int(sat_id)
                if sys_id == 1 and (33 <= sat_num <= 64 or 120 <= sat_num <= 158):
                    current_sys = 5

                snr_raw = parts[i + 3].split('*')[0]
                snr = int(snr_raw) if snr_raw and snr_raw.isdigit() else 0

                # (システム, ID) のペアで保存。他国衛星との衝突を完全回避
                key = (current_sys, sat_id)
                self.satellites[key] = {
                    'id': sat_id,
                    'elevation': int(parts[i + 1]) if parts[i + 1] else 0,
                    'azimuth': int(parts[i + 2]) if parts[i + 2] else 0,
                    'snr': snr,
                    'system_id': current_sys,
                    'in_use': key in self.satellites_in_use
                }
        except BaseException:
            pass

    def get_satellites_by_system(self):
        """保存された system_id をそのまま信じて分類"""
        res = {'GPS': [], 'SBAS': [], 'GLONASS': [], 'BeiDou': [], 'Galileo': [], 'QZSS': []}
        mapping = {1: 'GPS', 2: 'GLONASS', 3: 'Galileo', 4: 'BeiDou', 5: 'SBAS', 6: 'QZSS'}

        for (sys_id, _), info in self.satellites.items():
            sys_name = mapping.get(info['system_id'], 'GPS')
            res[sys_name].append(info)

        for s in res:
            res[s].sort(key=lambda x: int(x['id']))
        return res

    def get_satellite_count(self):
        return len(self.satellites_in_use), len(self.satellites)

    def _parse_coordinate(self, s, d):
        try:
            dot = s.index('.')
            dec = int(s[:dot - 2]) + float(s[dot - 2:]) / 60.0
            return -dec if d in ['S', 'W'] else dec
        except BaseException:
            return None

    def _calculate_grid_locator(self):
        """10桁グリッドロケーター"""
        if self.latitude is None or self.longitude is None:
            return
        try:
            lon, lat = self.longitude + 180, self.latitude + 90
            grid = chr(int(lon / 20) + ord('A')) + chr(int(lat / 10) + ord('A'))
            grid += str(int((lon % 20) / 2)) + str(int(lat % 10))
            grid += chr(int((lon % 2) / (2 / 24)) + ord('a')) + chr(int((lat % 1) / (1 / 24)) + ord('a'))
            grid += str(int((lon % (2 / 24)) / (2 / 240))) + str(int((lat % (1 / 24)) / (1 / 240)))
            grid += chr(int((lon % (2 / 240)) / (2 / 5760)) + ord('a')) + \
                chr(int((lat % (1 / 240)) / (1 / 5760)) + ord('a'))
            self.grid_locator = grid.upper()
        except BaseException:
            pass
