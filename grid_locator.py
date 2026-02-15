"""
グリッドロケーター（Maidenhead Locator System）計算モジュール
10桁対応（例：PM95vr12ab）
修正版：正確な計算式
"""

def latlon_to_grid(lat, lon, precision=5):
    """
    緯度経度をグリッドロケーターに変換
    
    Args:
        lat: 緯度（度）北緯が正
        lon: 経度（度）東経が正
        precision: 精度（1-5）5で10桁
    
    Returns:
        グリッドロケーター文字列
    """
    # 経度を0-360に正規化
    adj_lon = lon + 180.0
    # 緯度を0-180に正規化
    adj_lat = lat + 90.0
    
    grid = ""
    
    # フィールド（1-2桁目）：20度×10度
    field_lon = int(adj_lon / 20.0)
    field_lat = int(adj_lat / 10.0)
    grid += chr(ord('A') + field_lon) + chr(ord('A') + field_lat)
    adj_lon -= field_lon * 20.0
    adj_lat -= field_lat * 10.0
    
    # スクエア（3-4桁目）：2度×1度
    square_lon = int(adj_lon / 2.0)
    square_lat = int(adj_lat / 1.0)
    grid += str(square_lon) + str(square_lat)
    adj_lon -= square_lon * 2.0
    adj_lat -= square_lat * 1.0
    
    if precision >= 3:
        # サブスクエア（5-6桁目）：5分×2.5分 = 1/12度×1/24度
        subsq_lon = int(adj_lon * 12.0)
        subsq_lat = int(adj_lat * 24.0)
        grid += chr(ord('a') + subsq_lon) + chr(ord('a') + subsq_lat)
        adj_lon -= subsq_lon / 12.0
        adj_lat -= subsq_lat / 24.0
    
    if precision >= 4:
        # 拡張スクエア（7-8桁目）：1/120度×1/240度
        ext_lon = int(adj_lon * 120.0)
        ext_lat = int(adj_lat * 240.0)
        grid += str(ext_lon) + str(ext_lat)
        adj_lon -= ext_lon / 120.0
        adj_lat -= ext_lat / 240.0
    
    if precision >= 5:
        # 拡張サブスクエア（9-10桁目）：1/2880度×1/5760度
        extsub_lon = int(adj_lon * 2880.0)
        extsub_lat = int(adj_lat * 5760.0)
        grid += chr(ord('a') + extsub_lon) + chr(ord('a') + extsub_lat)
    
    return grid

def parse_nmea_latlon(lat_str, lat_dir, lon_str, lon_dir):
    """
    NMEA形式の緯度経度を10進数に変換
    
    Args:
        lat_str: 緯度文字列（ddmm.mmmm形式）
        lat_dir: N or S
        lon_str: 経度文字列（dddmm.mmmm形式）
        lon_dir: E or W
    
    Returns:
        (緯度, 経度) のタプル（10進数）
    """
    try:
        # 緯度：ddmm.mmmm → dd + mm.mmmm/60
        lat_deg = int(lat_str[:2])
        lat_min = float(lat_str[2:])
        lat = lat_deg + lat_min / 60.0
        if lat_dir == 'S':
            lat = -lat
        
        # 経度：dddmm.mmmm → ddd + mm.mmmm/60
        lon_deg = int(lon_str[:3])
        lon_min = float(lon_str[3:])
        lon = lon_deg + lon_min / 60.0
        if lon_dir == 'W':
            lon = -lon
        
        return lat, lon
    except:
        return None, None

# テスト
if __name__ == "__main__":
    # 東京タワーでテスト
    lat = 35.6585805
    lon = 139.7454329
    grid = latlon_to_grid(lat, lon, precision=5)
    print(f"東京タワー: {grid}")
    # 期待値：PM95vr12ab または近似値
    
    # ユーザーの位置でテスト（PM95tq47gc）
    # 逆算してみる
    test_lat = 35.625  # 仮の値
    test_lon = 139.625  # 仮の値
    test_grid = latlon_to_grid(test_lat, test_lon, precision=5)
    print(f"テスト: lat={test_lat}, lon={test_lon} -> {test_grid}")