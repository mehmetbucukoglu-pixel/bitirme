import os
import sys
import json
import numpy as np
import pandas as pd
from pyproj import CRS, Transformer

# ==============================================================================
# MARMARA 2D DÜZLEM PROJEKSİYONU (AEQD: Azimuthal Equidistant)
# ==============================================================================
MARMARA_AEQD_CRS = CRS.from_proj4(
    "+proj=aeqd +lat_0=40.75 +lon_0=28.50 "
    "+datum=WGS84 +units=m +type=crs"
)
TRANSFORMER_WGS84_TO_AEQD = Transformer.from_crs("EPSG:4326", MARMARA_AEQD_CRS, always_xy=True)

# WGS84 (boylam, enlem). Uçlardan sonraki değer kapının Marmara'ya göre
# hangi tarafta olduğunu, son değer Marmara'ya girişte segment başlatmayı belirtir.
VIRTUAL_GATES = (
    ("GATE-CANAKKALE", "Çanakkale Boğazı Kapısı", (26.99651, 40.56754), (27.07985, 40.44217), -1, True),
    ("GATE-ISTANBUL", "İstanbul Boğazı Kapısı", (28.95296, 41.02112), (29.02600, 40.99345), 1, True),
    ("GATE-IZMIT", "İzmit Körfezi Kapısı", (29.50841, 40.78865), (29.51127, 40.71913), 1, False),
)


def project_to_marmara_xy(lons, lats):
    """
    WGS84 (lon, lat) derece koordinatlarını Marmara merkezli 2D Kartezyen
    düzleme (x, y metre) dönüştürür.
    """
    return TRANSFORMER_WGS84_TO_AEQD.transform(lons, lats)


def load_marmara_ports(excel_path="Marmara_Final_Liman_Listesi.xlsx"):
    """
    Marmara_Final_Liman_Listesi.xlsx dosyasındaki 41 liman noktasını okur,
    temizler ve Marmara 2D AEQD düzlemine (x_m, y_m) dönüştürür.
    """
    if not os.path.exists(excel_path):
        raise FileNotFoundError(f"Liman listesi bulunamadı: {excel_path}")

    if excel_path.lower().endswith(".csv"):
        # Fine-tune edilmiş liman listesi (port_code, port_name, lat, lon, radius_m)
        ports_df = pd.read_csv(excel_path)
        ports_df["radius_m"] = pd.to_numeric(ports_df.get("radius_m", 500.0), errors="coerce").fillna(500.0)
        ports_df["port_id"] = np.arange(len(ports_df), dtype=np.int32)
        p_x, p_y = project_to_marmara_xy(ports_df["lon"].to_numpy(), ports_df["lat"].to_numpy())
        ports_df["x_m"] = p_x
        ports_df["y_m"] = p_y
        return ports_df

    raw = pd.read_excel(excel_path)
    col0 = raw.iloc[:, 0].astype(str).str.strip()
    mask = col0.str.fullmatch(r"MRM-F[0-9]{3}", na=False)
    ports = raw.loc[mask].copy().reset_index(drop=True)

    ports_df = pd.DataFrame({
        "port_id": np.arange(len(ports), dtype=np.int32),
        "port_code": ports.iloc[:, 0].astype(str).str.strip(),
        "port_name": ports.iloc[:, 1].astype(str).str.strip(),
        "lat": pd.to_numeric(ports.iloc[:, 2], errors="coerce").astype(np.float64),
        "lon": pd.to_numeric(ports.iloc[:, 3], errors="coerce").astype(np.float64),
        "scope": ports.iloc[:, 4].astype(str).str.strip(),
    }).dropna(subset=["lat", "lon"]).reset_index(drop=True)
    ports_df["port_id"] = np.arange(len(ports_df), dtype=np.int32)

    # 2D Düzlem Kartezyen Koordinatları (metre)
    p_x, p_y = project_to_marmara_xy(ports_df["lon"].to_numpy(), ports_df["lat"].to_numpy())
    ports_df["x_m"] = p_x
    ports_df["y_m"] = p_y
    ports_df["radius_m"] = 500.0

    return ports_df


def find_nearest_ports_2d_chunked(ship_x_arr, ship_y_arr, port_x_arr, port_y_arr, chunk_size=500_000, port_radius_arr=None):
    """
    10+ milyon AIS noktası için 41 limana olan 2D Kartezyen Öklid mesafesini:
    hypot(gemi_x - liman_x, gemi_y - liman_y) [metre]
    RAM'i koruyarak parça parça (chunked) ve vektörize hesaplar.
    port_radius_arr verilirse liman seçimi mesafe/yarıçap oranına göre yapılır
    (iç içe geçen farklı yarıçaplı dairelerde büyük limanın küçüğü yutmaması için).
    """
    n = len(ship_x_arr)
    nearest_port_idx = np.empty(n, dtype=np.int16)
    nearest_port_dist_m = np.empty(n, dtype=np.float32)

    p_x = port_x_arr[None, :]  # (1, P)
    p_y = port_y_arr[None, :]  # (1, P)
    p_r = None if port_radius_arr is None else np.asarray(port_radius_arr, dtype=np.float64)[None, :]

    for start in range(0, n, chunk_size):
        end = min(start + chunk_size, n)
        s_x = ship_x_arr[start:end, None]  # (C, 1)
        s_y = ship_y_arr[start:end, None]  # (C, 1)

        # 2D Öklid Mesafesi: hypot(dx, dy)
        dx = s_x - p_x
        dy = s_y - p_y
        dists = np.hypot(dx, dy)

        min_idx = np.argmin(dists if p_r is None else dists / p_r, axis=1)
        min_val = dists[np.arange(end - start), min_idx]

        nearest_port_idx[start:end] = min_idx.astype(np.int16)
        nearest_port_dist_m[start:end] = min_val.astype(np.float32)

    return nearest_port_idx, nearest_port_dist_m


def find_virtual_gate_crossings(ship_x, ship_y, ts_sec, is_time_gap):
    """Ardışık AIS noktalarından kapının izin verdiği yöndeki geçişleri bulur."""
    events = []
    for code, name, end_a, end_b, gate_side, starts_on_entry in VIRTUAL_GATES:
        x, y = project_to_marmara_xy([end_a[0], end_b[0]], [end_a[1], end_b[1]])
        dx, dy = x[1] - x[0], y[1] - y[0]
        length = np.hypot(dx, dy)
        # Sadece kapının çevre kutusuna ulaşan AIS kenarlarında kesişim hesapla.
        left = ship_x[:-1]
        right = ship_x[1:]
        bottom = ship_y[:-1]
        top = ship_y[1:]
        possible = (
            ~is_time_gap[1:] & (ts_sec[1:] > ts_sec[:-1])
            & ((left >= min(x)) | (right >= min(x)))
            & ((left <= max(x)) | (right <= max(x)))
            & ((bottom >= min(y)) | (top >= min(y)))
            & ((bottom <= max(y)) | (top <= max(y)))
        )
        previous = np.flatnonzero(possible)
        following = previous + 1
        before = gate_side * (dx * (ship_y[previous] - y[0]) - dy * (ship_x[previous] - x[0])) / length
        after = gate_side * (dx * (ship_y[following] - y[0]) - dy * (ship_x[following] - x[0])) / length
        on_line_tolerance_m = 1e-6
        from_marmara = before < -on_line_tolerance_m
        from_gate = before > on_line_tolerance_m
        changes_side = (
            (from_marmara & (after > on_line_tolerance_m))
            | (starts_on_entry & from_gate & (after < -on_line_tolerance_m))
        )
        i = previous[changes_side]
        fraction = before[changes_side] / (before[changes_side] - after[changes_side])
        crossing_x = ship_x[i] + fraction * (ship_x[i + 1] - ship_x[i])
        crossing_y = ship_y[i] + fraction * (ship_y[i + 1] - ship_y[i])
        along = ((crossing_x - x[0]) * dx + (crossing_y - y[0]) * dy) / length
        cuts_gate = (along >= 0) & (along <= length)
        crossing_ts = ts_sec[i] + fraction * (ts_sec[i + 1] - ts_sec[i])
        for idx, time, is_arrival in zip(i[cuts_gate] + 1, crossing_ts[cuts_gate], from_marmara[changes_side][cuts_gate]):
            events.append((idx, time, code, name, is_arrival))

        # Nokta çizginin üzerindeyse, geminin gerçekten öbür tarafa devam ettiğini
        # görmeden geçiş sayma. Çizgiye değip geri dönen gemiyi böylece ele.
        touches = (from_marmara | (starts_on_entry & from_gate)) & (np.abs(after) <= on_line_tolerance_m)
        for idx, is_arrival in zip(following[touches], from_marmara[touches]):
            along = ((ship_x[idx] - x[0]) * dx + (ship_y[idx] - y[0]) * dy) / length
            if not 0 <= along <= length:
                continue
            for following_idx in range(idx + 1, len(ts_sec)):
                if is_time_gap[following_idx] or ts_sec[following_idx] <= ts_sec[following_idx - 1]:
                    break
                px, py = ship_x[following_idx] - x[0], ship_y[following_idx] - y[0]
                side = gate_side * (dx * py - dy * px) / length
                if not np.isfinite(side):
                    break
                if abs(side) > on_line_tolerance_m:
                    if (side > 0) == is_arrival:
                        events.append((idx, ts_sec[idx], code, name, is_arrival))
                    break
                if not 0 <= (px * dx + py * dy) / length <= length:
                    break

    return (
        pd.DataFrame(events, columns=["idx", "ts", "code", "name", "is_arrival"])
        .drop_duplicates(subset="idx", keep=False)
        .sort_values("idx")
    )


def flag_long_port_voyages(
    segments, ports_df, ts_sec, ship_x, ship_y, nearest_port_idx,
    in_port_circle, is_port_stop, is_anchor_stop, is_time_gap, port_radius_m,
    min_route_voyages, gate_crossings, gate_boundary,
):
    """Ardışık liman uğraklarını eşleştirir ve üst süre eşiğini rota bazında hesaplar."""
    port_stop = is_port_stop & in_port_circle
    visit_boundary = (
        is_time_gap[1:] | gate_boundary[1:]
        | (nearest_port_idx[1:] != nearest_port_idx[:-1])
    )
    visit_starts = np.flatnonzero(port_stop & np.r_[True, ~port_stop[:-1] | visit_boundary])
    visit_ends = np.flatnonzero(port_stop & np.r_[~port_stop[1:] | visit_boundary, True])

    port_codes = ports_df["port_code"].to_numpy()
    port_x = ports_df["x_m"].to_numpy()
    port_y = ports_df["y_m"].to_numpy()
    # Fiziksel uğrakta iki yön de mümkündür. Kapıda yönü geçiş belirler.
    visits = [
        (start, end, port_codes[port], port, ts_sec[start], True, True)
        for start, end, port in zip(visit_starts, visit_ends, nearest_port_idx[visit_starts])
    ]
    visits.extend(
        (event.idx, event.idx - 1, event.code, None, event.ts,
         not event.is_arrival, event.is_arrival)
        for event in gate_crossings.itertuples(index=False)
    )
    visits.sort(key=lambda event: (event[0], event[4]))
    blocks = np.flatnonzero(is_time_gap)
    rows = []
    for start, end in zip(visits, visits[1:]):
        origin_idx, stop_end, origin_code, origin, departure_ts, can_depart, _ = start
        arrival, _, dest_code, _, arrival_ts, _, can_arrive = end
        after_stop = stop_end + 1
        if not can_depart or not can_arrive or origin_code == dest_code or after_stop >= arrival:
            continue
        if np.searchsorted(blocks, origin_idx, side="right") != np.searchsorted(blocks, arrival, side="right"):
            continue
        departure = after_stop
        if origin is not None:
            distance_m = np.hypot(
                ship_x[after_stop:arrival] - port_x[origin],
                ship_y[after_stop:arrival] - port_y[origin],
            )
            outside = np.flatnonzero(distance_m > np.broadcast_to(port_radius_m, port_x.shape)[origin])
            if not outside.size:
                continue
            departure = after_stop + outside[0]
            departure_ts = ts_sec[departure]
        if departure_ts < arrival_ts:
            rows.append((after_stop, arrival, origin_code, dest_code, departure_ts,
                         arrival_ts, is_anchor_stop[departure:arrival].any()))

    voyages = pd.DataFrame(rows, columns=[
        "after_stop_idx", "arrival_idx", "voyage_origin_port_code",
        "voyage_dest_port_code", "departure_ts", "arrival_ts", "has_anchorage",
    ])
    voyages.index = pd.RangeIndex(1, len(voyages) + 1, name="port_voyage_id")

    # Bir sefer birkaç mevcut seyir segmenti içerebilir. Referansta seferi bir kez say.
    arrival_indices = voyages["arrival_idx"].to_numpy()
    candidate = np.searchsorted(arrival_indices, segments["end_idx"], side="right")
    segment_positions = np.flatnonzero(candidate < len(voyages))
    voyage_positions = candidate[segment_positions]
    inside = (
        segments["start_idx"].to_numpy()[segment_positions]
        >= voyages["after_stop_idx"].to_numpy()[voyage_positions]
    )
    segment_positions = segment_positions[inside]
    voyage_ids = voyage_positions[inside] + 1
    segments["port_voyage_id"] = pd.Series(pd.NA, index=segments.index, dtype="Int64")
    segments.loc[segments.index[segment_positions], "port_voyage_id"] = voyage_ids
    voyages = voyages.loc[voyages.index.isin(voyage_ids)].copy()

    voyages["voyage_departure_time_utc"] = pd.to_datetime(voyages.pop("departure_ts"), unit="s", utc=True)
    voyages["voyage_arrival_time_utc"] = pd.to_datetime(voyages.pop("arrival_ts"), unit="s", utc=True)
    voyages["voyage_duration_min"] = (
        (voyages["voyage_arrival_time_utc"] - voyages["voyage_departure_time_utc"])
        .dt.total_seconds() / 60.0
    )
    anchored = voyages["has_anchorage"].to_numpy(dtype=bool)
    # Demirlemesiz A → B seferleri, rotanın süre eşiğini belirler.
    voyages["reference_duration_min"] = voyages["voyage_duration_min"].where(~anchored)
    route_durations = voyages.groupby(
        ["voyage_origin_port_code", "voyage_dest_port_code"], sort=False
    )["reference_duration_min"]
    voyages["route_reference_count"] = route_durations.transform("count").astype("Int64")
    enough = voyages["route_reference_count"].to_numpy(dtype=np.int64) >= min_route_voyages
    assess_duration = enough & ~anchored
    median = route_durations.transform("median").where(assess_duration)
    q1 = route_durations.transform(lambda times: times.quantile(0.25))
    q3 = route_durations.transform(lambda times: times.quantile(0.75))
    # NIST kutu grafiği: https://www.itl.nist.gov/div898/handbook/prc/section1/prc16.htm
    upper_limit = (q3 + 3.0 * (q3 - q1)).where(assess_duration)
    long_duration = assess_duration & (voyages["voyage_duration_min"] > upper_limit)
    voyages["route_median_duration_min"] = median
    voyages["duration_upper_limit_min"] = upper_limit
    voyages["duration_ratio"] = voyages["voyage_duration_min"] / median
    voyages["duration_ratio_limit"] = upper_limit / median
    voyages["long_duration_flag"] = long_duration.astype("boolean").where(assess_duration | anchored)
    voyages["duration_check_status"] = np.select(
        [anchored, ~enough, long_duration],
        ["ANCHORAGE", "INSUFFICIENT_REFERENCE", "LONG"],
        default="WITHIN_LIMIT",
    )

    voyage_columns = [
        "voyage_origin_port_code", "voyage_dest_port_code",
        "voyage_departure_time_utc", "voyage_arrival_time_utc", "voyage_duration_min",
        "route_reference_count", "route_median_duration_min", "duration_upper_limit_min",
        "duration_ratio", "duration_ratio_limit", "long_duration_flag", "duration_check_status",
    ]
    for column in voyage_columns:
        segments[column] = segments["port_voyage_id"].map(voyages[column])
    segments["duration_check_status"] = segments["duration_check_status"].fillna("NO_COMPLETE_VOYAGE")
    return ["port_voyage_id", *voyage_columns], voyages["duration_check_status"].value_counts().to_dict()


def segment_trajectories(
    input_csv="marmara_curated_alpha.csv",
    ports_excel="Marmara_Liman_Listesi_v2.csv",
    output_segments_csv="marmara_segmented_trajectories.csv",
    output_summary_csv="marmara_segment_summary.csv",
    output_port_events_csv="marmara_liman_ugrak_ve_cikislar.csv",
    output_stats_json="segmentasyon_ozeti.json",
    port_radius_m=500.0,          # Liman dairesi yarıçapı: 500 metre
    min_port_stop_min=5.0,        # Limanda min duruş süresi: 5 dakika
    min_anchor_stop_min=30.0,     # Demirde min bekleme süresi: 30 dakika
    min_voyage_duration_min=10.0, # Min seyir geçerlilik süresi: 10 dakika
    max_time_gap_min=12.0,        # Ampirik %99 sinyal kopukluk eşiği: 12.0 dakika (veya 30 dk)
    stop_speed_knots=0.5,         # Durma / demirleme hız eşiği: 0.5 knot
    min_route_voyages=5,         # Aynı yöndeki rotada süre eşiği için asgari sefer sayısı
):
    if min_route_voyages < 2:
        raise ValueError("Süre eşiği için rota başına en az 2 sefer gerekir.")
    print("==================================================================")
    print("  AIS 2D ÖKLİD YÖRÜNGE VE LİMAN SEGMENTASYONU                    ")
    print(f"  Girdi Dosyası        : {input_csv}")
    print(f"  Liman Listesi        : {ports_excel}")
    print(f"  Mesafe / Düzlem      : Marmara 2D AEQD Projeksiyonu (Öklid - hypot)")
    print(f"  Liman Yarıçapı       : limana özel (radius_m sütunu) | Min Liman Duruşu: {min_port_stop_min:.0f} dk")
    print(f"  Demirleme Süresi     : {min_anchor_stop_min:.0f} dk | Sinyal Kopukluğu: {max_time_gap_min:.1f} dk (%99 Eşiği)")
    print(f"  Min Seyir Süresi     : {min_voyage_duration_min:.0f} dk")
    print("==================================================================")

    if not os.path.exists(input_csv):
        print(f"HATA: '{input_csv}' bulunamadı!")
        return

    # 1. Limanları yükle ve 2D düzleme izdüşür
    ports_df = load_marmara_ports(ports_excel)
    num_ports = len(ports_df)
    print(f"-> [1/6] {num_ports} adet Marmara liman noktası yüklendi ve 2D AEQD düzlemine izdüşürüldü.")

    # 2. Temizlenmiş AIS verisini yükle
    print("-> [2/6] Temizlenmiş AIS verisi okunuyor ve 2D koordinatları kontrol ediliyor...")
    df = pd.read_csv(input_csv, low_memory=False)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
    df = df.dropna(subset=["mmsi", "timestamp", "latitude", "longitude"]).copy()
    df["mmsi"] = df["mmsi"].astype(np.int64)
    df["speed"] = pd.to_numeric(df["speed"], errors="coerce").fillna(0.0)

    # 2D Kartezyen koordinatlar dosyada yoksa hesapla
    if "x_m" not in df.columns or "y_m" not in df.columns:
        print("   -> 2D Kartezyen (x_m, y_m) türetiliyor...")
        sx, sy = project_to_marmara_xy(df["longitude"].to_numpy(), df["latitude"].to_numpy())
        df["x_m"] = sx
        df["y_m"] = sy

    df = df.sort_values(["mmsi", "timestamp"]).reset_index(drop=True)
    n = len(df)
    print(f"   Toplam Temiz Nokta Sayısı: {n:,}")

    # 3. 2D Öklid Mesafesi ile En Yakın Liman Tespiti
    print(f"-> [3/6] 2D Öklid formülü (hypot) ile {num_ports} limana mesafeler hesaplanıyor (limana özel yarıçap)...")
    ship_x = df["x_m"].to_numpy(dtype=np.float64)
    ship_y = df["y_m"].to_numpy(dtype=np.float64)
    port_x = ports_df["x_m"].to_numpy(dtype=np.float64)
    port_y = ports_df["y_m"].to_numpy(dtype=np.float64)

    port_radius_arr = ports_df["radius_m"].to_numpy(dtype=np.float64)

    nearest_port_idx, nearest_port_dist_m = find_nearest_ports_2d_chunked(
        ship_x, ship_y, port_x, port_y, port_radius_arr=port_radius_arr
    )
    in_port_circle = nearest_port_dist_m <= port_radius_arr[nearest_port_idx]
    port_radius_m = port_radius_arr  # limana özel yarıçaplar (sefer süre kontrolünde de kullanılır)
    print(f"   Liman Dairesi (limana özel yarıçap) İçindeki Nokta Sayısı: {int(in_port_circle.sum()):,}")

    # 4. Zaman farkları, Duruş (Port Stop >= 5 dk) ve Demirleme (Anchor Stop >= 30 dk)
    print("-> [4/6] Liman duruşları, demirlemeler ve sinyal kopuklukları tespit ediliyor...")
    mmsi_arr = df["mmsi"].to_numpy()
    speed_arr = df["speed"].to_numpy(dtype=np.float64)
    ts_sec = df["timestamp"].dt.as_unit("ns").astype("int64").to_numpy(dtype=np.float64) / 1e9

    same_mmsi = np.zeros(n, dtype=bool)
    same_mmsi[1:] = mmsi_arr[1:] == mmsi_arr[:-1]

    dt_sec = np.zeros(n, dtype=np.float64)
    dt_sec[1:] = np.where(same_mmsi[1:], ts_sec[1:] - ts_sec[:-1], 0.0)

    max_gap_sec = max_time_gap_min * 60.0
    min_port_stop_sec = min_port_stop_min * 60.0
    min_anchor_stop_sec = min_anchor_stop_min * 60.0
    min_voyage_sec = min_voyage_duration_min * 60.0

    is_time_gap = (~same_mmsi) | (dt_sec > max_gap_sec)

    gate_crossings = find_virtual_gate_crossings(ship_x, ship_y, ts_sec, is_time_gap)
    gate_boundary = np.zeros(n, dtype=bool)
    gate_boundary[gate_crossings["idx"].to_numpy(dtype=np.intp)] = True
    is_gate_arrival = gate_crossings["is_arrival"].astype(bool)
    gate_arrivals = gate_crossings.loc[is_gate_arrival].set_index("idx")
    gate_departures = gate_crossings.loc[~is_gate_arrival].set_index("idx")

    # A) Liman Dairesi Ziyaret Grupları
    port_visit_break = (
        is_time_gap | gate_boundary
        | (in_port_circle != np.roll(in_port_circle, 1))
        | (in_port_circle & (nearest_port_idx != np.roll(nearest_port_idx, 1)))
    )
    port_visit_break[0] = True
    port_visit_id = np.cumsum(port_visit_break)

    visit_df = pd.DataFrame({
        "visit_id": port_visit_id,
        "ts": ts_sec,
        "in_port": in_port_circle,
        "speed": speed_arr,
    })
    visit_stats = visit_df.groupby("visit_id", sort=False).agg(
        t_min=("ts", "min"),
        t_max=("ts", "max"),
        in_port=("in_port", "first"),
        min_speed=("speed", "min"),
    )
    visit_dur = visit_stats["t_max"] - visit_stats["t_min"]
    valid_port_visit_ids = visit_stats.index[
        visit_stats["in_port"] & (visit_dur >= min_port_stop_sec) & (visit_stats["min_speed"] <= max(stop_speed_knots, 1.5))
    ]
    is_port_dwell = np.isin(port_visit_id, valid_port_visit_ids)

    # B) Düşük Hız (< 0.5 knot) Blokları (Liman içi >= 5 dk veya Açıkta Demirleme >= 30 dk)
    is_slow = speed_arr <= stop_speed_knots
    slow_break = is_time_gap | gate_boundary | (is_slow != np.roll(is_slow, 1))
    slow_break[0] = True
    slow_run_id = np.cumsum(slow_break)

    slow_df = pd.DataFrame({
        "run_id": slow_run_id,
        "ts": ts_sec,
        "is_slow": is_slow,
        "in_port": in_port_circle,
    })
    slow_stats = slow_df.groupby("run_id", sort=False).agg(
        t_min=("ts", "min"),
        t_max=("ts", "max"),
        is_slow=("is_slow", "first"),
        any_in_port=("in_port", "any"),
    )
    slow_dur = slow_stats["t_max"] - slow_stats["t_min"]

    port_stop_runs = slow_stats.index[
        slow_stats["is_slow"] & slow_stats["any_in_port"] & (slow_dur >= min_port_stop_sec)
    ]
    anchor_stop_runs = slow_stats.index[
        slow_stats["is_slow"] & (~slow_stats["any_in_port"]) & (slow_dur >= min_anchor_stop_sec)
    ]

    is_port_stop = is_port_dwell | np.isin(slow_run_id, port_stop_runs)
    is_anchor_stop = (~is_port_stop) & np.isin(slow_run_id, anchor_stop_runs)
    is_underway = (~is_port_stop) & (~is_anchor_stop)

    # 0 = UNDERWAY (Seyir), 1 = PORT_STOP (Liman Duruşu), 2 = ANCHOR_STOP (Demirleme)
    point_state = np.zeros(n, dtype=np.int8)
    point_state[is_port_stop] = 1
    point_state[is_anchor_stop] = 2

    print(f"   • Aktif Seyir (Underway) Noktaları   : {int(is_underway.sum()):,}")
    print(f"   • Liman Duruşu (Port Stop >= 5dk)    : {int(is_port_stop.sum()):,}")
    print(f"   • Demirde Bekleme (Anchor >= 30dk)   : {int(is_anchor_stop.sum()):,}")

    # 5. Seyir Segmentleri Oluşturma (Demirleme segmenti kesmez, ara durak olarak sayılır)
    print("-> [5/6] Seyir segmentleri oluşturuluyor ve kalkış/varış limanları etiketleniyor...")
    # Demirleme segmenti kesmez: yalnızca liman duruşu, sinyal kopukluğu ve sanal kapı keser
    in_port_state = is_port_stop.astype(np.int8)
    state_change = (in_port_state != np.roll(in_port_state, 1))
    raw_seg_break = is_time_gap | gate_boundary | state_change
    raw_seg_break[0] = True
    raw_seg_id = np.cumsum(raw_seg_break)

    uw_mask = ~is_port_stop
    uw_indices = np.where(uw_mask)[0]

    df["nearest_port_code"] = ports_df["port_code"].to_numpy()[nearest_port_idx]
    df["nearest_port_name"] = ports_df["port_name"].to_numpy()[nearest_port_idx]
    df["nearest_port_dist_m"] = np.round(nearest_port_dist_m, 1)

    anchor_dt_sec = np.where(is_anchor_stop & (~is_time_gap), dt_sec, 0.0)

    uw_df = pd.DataFrame({
        "idx": uw_indices,
        "raw_seg_id": raw_seg_id[uw_indices],
        "mmsi": mmsi_arr[uw_indices],
        "ts": ts_sec[uw_indices],
        "x": ship_x[uw_indices],
        "y": ship_y[uw_indices],
        "speed": speed_arr[uw_indices],
        "in_port": in_port_circle[uw_indices],
        "port_idx": nearest_port_idx[uw_indices],
        "anchor_dt_sec": anchor_dt_sec[uw_indices],
    })

    seg_agg = uw_df.groupby("raw_seg_id", sort=False).agg(
        mmsi=("mmsi", "first"),
        start_idx=("idx", "first"),
        end_idx=("idx", "last"),
        point_count=("idx", "count"),
        start_ts=("ts", "min"),
        end_ts=("ts", "max"),
        mean_speed_kn=("speed", "mean"),
        max_speed_kn=("speed", "max"),
        first_in_port=("in_port", "first"),
        last_in_port=("in_port", "last"),
        first_port_idx=("port_idx", "first"),
        last_port_idx=("port_idx", "last"),
        anchorage_wait_sec=("anchor_dt_sec", "sum"),
    ).reset_index()

    arrival_idx = seg_agg["end_idx"] + 1
    start_gate_ts = seg_agg["start_idx"].map(gate_departures["ts"])
    end_gate_ts = arrival_idx.map(gate_arrivals["ts"])
    seg_agg["start_ts"] = start_gate_ts.fillna(seg_agg["start_ts"])
    seg_agg["end_ts"] = end_gate_ts.fillna(seg_agg["end_ts"])
    seg_agg["duration_sec"] = seg_agg["end_ts"] - seg_agg["start_ts"]
    seg_agg["duration_min"] = seg_agg["duration_sec"] / 60.0
    seg_agg["anchorage_wait_min"] = np.round(seg_agg["anchorage_wait_sec"] / 60.0, 2)

    valid_segs = seg_agg[
        (seg_agg["duration_sec"] >= min_voyage_sec) & (seg_agg["point_count"] >= 3)
        | ((start_gate_ts.notna() | end_gate_ts.notna()) & (seg_agg["duration_sec"] > 0))
    ].copy().reset_index(drop=True)

    start_indices = valid_segs["start_idx"].to_numpy()
    end_indices = valid_segs["end_idx"].to_numpy()

    prev_idx = np.maximum(start_indices - 1, 0)
    next_idx = np.minimum(end_indices + 1, n - 1)

    has_prev_same_ship = (start_indices > 0) & (mmsi_arr[prev_idx] == mmsi_arr[start_indices]) & ((ts_sec[start_indices] - ts_sec[prev_idx]) <= max_gap_sec)
    has_next_same_ship = (end_indices < n - 1) & (mmsi_arr[next_idx] == mmsi_arr[end_indices]) & ((ts_sec[next_idx] - ts_sec[end_indices]) <= max_gap_sec)

    prev_state = np.where(has_prev_same_ship, point_state[prev_idx], -1)
    next_state = np.where(has_next_same_ship, point_state[next_idx], -1)

    origin_is_port = (prev_state == 1) | valid_segs["first_in_port"].to_numpy()
    origin_is_anchor = (~origin_is_port) & (prev_state == 2)
    origin_port_idx = np.where(prev_state == 1, nearest_port_idx[prev_idx], valid_segs["first_port_idx"].to_numpy())

    dest_is_port = (next_state == 1) | valid_segs["last_in_port"].to_numpy()
    dest_is_anchor = (~dest_is_port) & (next_state == 2)
    dest_port_idx = np.where(next_state == 1, nearest_port_idx[next_idx], valid_segs["last_port_idx"].to_numpy())

    origin_gate_code = valid_segs["start_idx"].map(gate_departures["code"])
    dest_gate_code = (valid_segs["end_idx"] + 1).map(gate_arrivals["code"])
    origin_is_gate = origin_gate_code.notna().to_numpy()
    dest_is_gate = dest_gate_code.notna().to_numpy()
    origin_is_port |= origin_is_gate
    dest_is_port |= dest_is_gate
    origin_is_anchor &= ~origin_is_gate
    dest_is_anchor &= ~dest_is_gate

    port_codes = ports_df["port_code"].to_numpy()
    port_names = ports_df["port_name"].to_numpy()

    valid_segs["origin_type"] = np.where(origin_is_port, "PORT", np.where(origin_is_anchor, "ANCHORAGE", "GAP_OR_ENTRY"))
    valid_segs["origin_port_code"] = np.where(origin_is_port, port_codes[origin_port_idx], "")
    valid_segs["origin_port_name"] = np.where(origin_is_port, port_names[origin_port_idx], "")

    valid_segs["dest_type"] = np.where(dest_is_port, "PORT", np.where(dest_is_anchor, "ANCHORAGE", "GAP_OR_EXIT"))
    valid_segs["dest_port_code"] = np.where(dest_is_port, port_codes[dest_port_idx], "")
    valid_segs["dest_port_name"] = np.where(dest_is_port, port_names[dest_port_idx], "")

    valid_segs.loc[origin_is_gate, "origin_type"] = "VIRTUAL_GATE"
    valid_segs.loc[origin_is_gate, "origin_port_code"] = origin_gate_code[origin_is_gate]
    valid_segs.loc[origin_is_gate, "origin_port_name"] = valid_segs.loc[origin_is_gate, "start_idx"].map(gate_departures["name"])
    valid_segs.loc[dest_is_gate, "dest_type"] = "VIRTUAL_GATE"
    valid_segs.loc[dest_is_gate, "dest_port_code"] = dest_gate_code[dest_is_gate]
    valid_segs.loc[dest_is_gate, "dest_port_name"] = (valid_segs.loc[dest_is_gate, "end_idx"] + 1).map(gate_arrivals["name"])

    seg_category = np.full(len(valid_segs), "TRANSIT_OR_PARTIAL", dtype=object)
    seg_category[origin_is_port & (~dest_is_port) & (~dest_is_anchor)] = "PORT_DEPARTURE"
    seg_category[(~origin_is_port) & (~origin_is_anchor) & dest_is_port] = "PORT_ARRIVAL"
    seg_category[origin_is_port & dest_is_anchor] = "PORT_TO_ANCHOR"
    seg_category[origin_is_anchor & dest_is_port] = "ANCHOR_TO_PORT"
    seg_category[origin_is_anchor & dest_is_anchor] = "ANCHOR_TO_ANCHOR"
    seg_category[origin_is_port & dest_is_port & (valid_segs["origin_port_code"] == valid_segs["dest_port_code"])] = "PORT_ROUNDTRIP"
    seg_category[origin_is_port & dest_is_port & (valid_segs["origin_port_code"] != valid_segs["dest_port_code"])] = "PORT_TO_PORT"
    valid_segs["segment_category"] = seg_category

    duration_cols, duration_counts = flag_long_port_voyages(
        valid_segs, ports_df, ts_sec, ship_x, ship_y, nearest_port_idx,
        in_port_circle, is_port_stop, is_anchor_stop, is_time_gap, port_radius_m,
        min_route_voyages, gate_crossings, gate_boundary,
    )

    valid_segs["mmsi_seg_no"] = valid_segs.groupby("mmsi").cumcount() + 1
    valid_segs["global_segment_id"] = np.arange(1, len(valid_segs) + 1, dtype=np.int32)
    valid_segs["segment_label"] = (
        valid_segs["mmsi"].astype(str) + "_S" + valid_segs["mmsi_seg_no"].astype(str).str.zfill(3)
    )

    valid_segs["start_time_utc"] = pd.to_datetime(valid_segs["start_ts"], unit="s", utc=True)
    valid_segs["end_time_utc"] = pd.to_datetime(valid_segs["end_ts"], unit="s", utc=True)
    valid_segs["duration_min"] = valid_segs["duration_min"].round(2)
    valid_segs["mean_speed_kn"] = valid_segs["mean_speed_kn"].round(2)
    valid_segs["max_speed_kn"] = valid_segs["max_speed_kn"].round(2)

    raw_to_global = dict(zip(valid_segs["raw_seg_id"], valid_segs["global_segment_id"]))
    raw_to_mmsi_seg = dict(zip(valid_segs["raw_seg_id"], valid_segs["mmsi_seg_no"]))
    raw_to_cat = dict(zip(valid_segs["raw_seg_id"], valid_segs["segment_category"]))
    raw_to_orig = dict(zip(valid_segs["raw_seg_id"], valid_segs["origin_port_name"]))
    raw_to_dest = dict(zip(valid_segs["raw_seg_id"], valid_segs["dest_port_name"]))

    df["raw_seg_id"] = raw_seg_id
    df["point_state"] = np.where(point_state == 0, "UNDERWAY", np.where(point_state == 1, "PORT_STOP", "ANCHOR_STOP"))

    seg_df = df[df["raw_seg_id"].isin(raw_to_global)].copy()
    seg_df["segment_id"] = seg_df["raw_seg_id"].map(raw_to_global).astype(np.int32)
    seg_df["mmsi_seg_no"] = seg_df["raw_seg_id"].map(raw_to_mmsi_seg).astype(np.int32)
    seg_df["segment_category"] = seg_df["raw_seg_id"].map(raw_to_cat)
    seg_df["origin_port"] = seg_df["raw_seg_id"].map(raw_to_orig)
    seg_df["dest_port"] = seg_df["raw_seg_id"].map(raw_to_dest)
    point_duration_cols = ["port_voyage_id", "long_duration_flag", "duration_check_status"]
    duration_by_raw_segment = valid_segs.set_index("raw_seg_id")[point_duration_cols]
    for column in point_duration_cols:
        seg_df[column] = seg_df["raw_seg_id"].map(duration_by_raw_segment[column])

    cat_counts = valid_segs["segment_category"].value_counts().to_dict()

    print("\n==================================================================")
    print("        2D ÖKLİD YÖRÜNGE SEGMENTASYON BİLANÇO ÖZETİ               ")
    print("==================================================================")
    print(f"1. Toplam Temiz AIS Noktası                   : {n:,}")
    print(f"2. Segmentlere Dahil Edilen Seyir Noktası     : {len(seg_df):,} (%{len(seg_df)/n*100:.2f})")
    print(f"3. Toplam Geçerli Seyir Segmenti              : {len(valid_segs):,}")
    print(f"4. Benzersiz Gemi (MMSI) Sayısı               : {valid_segs['mmsi'].nunique():,}")
    print("------------------------------------------------------------------")
    print("5. Segment Kategorisi Dağılımı:")
    for cat_name, cnt in cat_counts.items():
        print(f"   • {cat_name:<24} : {cnt:,} segment (%{cnt/len(valid_segs)*100:.1f})")
    print(f"6. Süre Aykırılığı İşaretlenen Limanlar Arası Sefer: {duration_counts.get('LONG', 0):,}")
    print(f"7. Sanal Kapı Geçişleri                       : {len(gate_crossings):,}")
    print("==================================================================")

    # Özet ve nokta dosyalarını kaydet
    summary_cols = [
        "global_segment_id", "segment_label", "mmsi", "mmsi_seg_no", "segment_category",
        "origin_type", "origin_port_code", "origin_port_name",
        "dest_type", "dest_port_code", "dest_port_name",
        "start_time_utc", "end_time_utc", "duration_min", "point_count",
        "mean_speed_kn", "max_speed_kn", "anchorage_wait_min",
        *duration_cols,
    ]
    valid_segs[summary_cols].to_csv(output_summary_csv, index=False, encoding="utf-8-sig")
    print(f"-> Segment özet tablosu kaydedildi : {output_summary_csv}")

    out_point_cols = [
        "mmsi", "timestamp", "latitude", "longitude", "x_m", "y_m",
        "speed", "course", "heading",
        "segment_id", "mmsi_seg_no", "segment_category", "origin_port", "dest_port",
        "nearest_port_code", "nearest_port_dist_m", *point_duration_cols,
    ]
    out_point_cols = [c for c in out_point_cols if c in seg_df.columns]
    print(f"-> [6/6] Segmentlenmiş nokta verisi '{output_segments_csv}' dosyasına yazılıyor...")
    seg_df[out_point_cols].to_csv(output_segments_csv, index=False, chunksize=500_000)

    stats_payload = {
        "projeksiyon": "AEQD_Marmara_lat0_40.75_lon0_28.50",
        "parametreler": {
            "port_radius_m": "limana_ozel (Marmara_Liman_Listesi_v2.csv)",
            "min_port_stop_min": min_port_stop_min,
            "min_anchor_stop_min": min_anchor_stop_min,
            "min_voyage_duration_min": min_voyage_duration_min,
            "max_time_gap_min": max_time_gap_min,
            "stop_speed_knots": stop_speed_knots,
            "min_route_voyages": min_route_voyages,
        },
        "toplam_temiz_nokta": int(n),
        "segment_ici_seyir_noktasi": int(len(seg_df)),
        "liman_durusu_noktasi": int(is_port_stop.sum()),
        "demirleme_noktasi": int(is_anchor_stop.sum()),
        "toplam_gecerli_segment": int(len(valid_segs)),
        "benzersiz_gemi_sayisi": int(valid_segs["mmsi"].nunique()),
        "kategori_dagilimi": {str(k): int(v) for k, v in cat_counts.items()},
        "sanal_kapi_gecisleri": {
            code: {
                "marmaradan_kapiya": int((gate_arrivals["code"] == code).sum()),
                "kapidan_marmaraya": int((gate_departures["code"] == code).sum()),
            }
            for code, *_ in VIRTUAL_GATES
        },
        "limanlar_arasi_sefer_sure_kontrolu": {
            str(status): int(count) for status, count in duration_counts.items()
        },
    }
    with open(output_stats_json, "w", encoding="utf-8") as f:
        json.dump(stats_payload, f, ensure_ascii=False, indent=2)
    print(f"-> İstatistik özeti '{output_stats_json}' dosyasına kaydedildi.\n")


if __name__ == "__main__":
    segment_trajectories()
