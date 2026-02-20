"""
NTP クライアントモジュール（64bitタイムスタンプ + RFC5905 offset/delay算出版）

get_time() -> (server_time_utc, offset_ms)
- server_time_utc : datetime (tz-aware, UTC) サーバーの送信タイムスタンプ(t3)
- offset_ms       : クロックオフセット（ミリ秒）= (t2-t1 + t3-t4) / 2 * 1000
"""
import socket
import struct
import time
from datetime import datetime, timezone

NTP_DELTA = 2208988800  # 1900年〜1970年の秒数


class NTPClient:
    def __init__(self, server='pool.ntp.org', port=123, timeout=5.0):
        self.server = server
        self.port = port
        self.timeout = timeout

    def set_server(self, server):
        self.server = server

    def get_time(self):
        """
        NTPサーバーから時刻を取得。
        戻り値: (server_time_utc, offset_ms)
        失敗時は例外を送出（呼び出し側でキャッチすること）。
        """
        infos = socket.getaddrinfo(self.server, self.port, 0, socket.SOCK_DGRAM)
        if not infos:
            raise RuntimeError("DNS resolution failed for NTP server")

        family, socktype, proto, canonname, sockaddr = infos[0]

        # NTPパケット: LI=0, VN=4, Mode=3 → 0x23
        req = b'\x23' + 47 * b'\0'

        with socket.socket(family, socket.SOCK_DGRAM) as s:
            s.settimeout(self.timeout)
            t1 = time.time()
            s.sendto(req, sockaddr)
            data, _ = s.recvfrom(512)
            t4 = time.time()

        if len(data) < 48:
            raise RuntimeError("Invalid NTP response (too short)")

        try:
            unpacked = struct.unpack('!12I', data[0:48])
        except struct.error as e:
            raise RuntimeError("Failed to unpack NTP response") from e

        t2_sec, t2_frac = unpacked[8], unpacked[9]
        t3_sec, t3_frac = unpacked[10], unpacked[11]

        t2 = (t2_sec - NTP_DELTA) + (t2_frac / 2**32)
        t3 = (t3_sec - NTP_DELTA) + (t3_frac / 2**32)

        # RFC 5905
        offset = ((t2 - t1) + (t3 - t4)) / 2.0
        delay = (t4 - t1) - (t3 - t2)

        server_time = datetime.fromtimestamp(t3, tz=timezone.utc)
        return server_time, (offset * 1000.0)
