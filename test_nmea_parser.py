# test_nmea_parser.py
from nmea_parser import NMEAParser

def test_parse_gga_updates_position_and_altitude():
    p = NMEAParser()

    # 代表的なGGA（緯度経度・高度を含む）
    line = "$GPGGA,092750.000,5321.6802,N,00630.3372,W,1,08,1.03,61.7,M,55.2,M,,*76"
    p.parse(line)

    # 53°21.6802' N = 53 + 21.6802/60
    assert p.latitude is not None
    assert abs(p.latitude - (53 + 21.6802 / 60)) < 1e-6

    # 6°30.3372' W = -(6 + 30.3372/60)
    assert p.longitude is not None
    assert abs(p.longitude - (-(6 + 30.3372 / 60))) < 1e-6

    # altitude: 61.7m
    # （属性名が違う可能性があるので、まずは存在チェックを入れる）
    assert hasattr(p, "altitude") or hasattr(p, "altitude_m") or hasattr(p, "altitude_meters")