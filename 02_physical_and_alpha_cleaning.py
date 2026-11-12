import os
import sys
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pyproj import CRS, Transformer

# ==============================================================================
# 1. MARMARA 2D DÜZLEM PROJEKSİYONU (AEQD: Azimuthal Equidistant)
# ==============================================================================
# Merkez: Marmara Denizi'nin coğrafi ağırlık merkezi (40.75° N, 28.50° E)
# Bu projeksiyonda harita 2D Kartezyen düzlem (x, y metre) kabul edilir.
# İki nokta arasındaki mesafe doğrudan Öklid formülü (hypot) ile hesaplanır.
MARMARA_AEQD_CRS = CRS.from_proj4(
    "+proj=aeqd +lat_0=40.75 +lon_0=28.50 "
    "+datum=WGS84 +units=m +type=crs"
)
TRANSFORMER_WGS84_TO_AEQD = Transformer.from_crs("EPSG:4326", MARMARA_AEQD_CRS, always_xy=True)

# IHO Marmara Denizi Resmi Çalışma Alanı Sınırları (DMS -> Ondalık Derece)
MARMARA_BOUNDS = {
    "lat_min": (39 * 3600 + 59 * 60 + 56.1) / 3600,  # ~39.998917 N
    "lat_max": (41 * 3600 + 13 * 60 + 58.6) / 3600,  # ~41.232944 N
    "lon_min": (26 * 3600 + 10 * 60 + 27.2) / 3600,  # ~26.174222 E
    "lon_max": (29 * 3600 + 56 * 60 + 31.9) / 3600,  # ~29.942194 E
}

MPS_TO_KNOTS = 3600.0 / 1852.0   # 1.94384449 (1 m/s = 1.943844 knot)
KNOT_TO_MPS = 1852.0 / 3600.0    # 0.51444444 (1 knot = 0.514444 m/s)


def project_to_marmara_xy(lons, lats):
    """
    WGS84 (EPSG:4326) derece koordinatlarını Marmara merkezli 2D düzleme
    metre (x, y) cinsinden vektörize dönüştürür.
    """
    return TRANSFORMER_WGS84_TO_AEQD.transform(lons, lats)


def euclidean_distance_m(x1, y1, x2, y2):
    """
    2D Kartezyen düzlemde iki nokta arasındaki Öklid mesafesi (metre):
    hypot(x2 - x1, y2 - y1)
    """
    return np.hypot(x2 - x1, y2 - y1)


def compute_minimal_cog_diff(cog1, cog2):
    """
    Dairesel rota farkını (Delta COG) derece cinsinden hesaplar:
    min(|COG2 - COG1|, 360 - |COG2 - COG1|)
    """
    diff = np.abs(cog2 - cog1)
    return np.minimum(diff, 360.0 - diff)


def plot_and_analyze_delta_t(dt_valid, output_hist_png="delta_t_histogram.png", output_json="delta_t_analizi.json"):
    """
    Ardışık AIS sinyalleri arasındaki sürelerin (Delta t) dağılımını analiz eder.
    Ampirik kantilleri (%50, %75, %90, %95, %98, %99, %99.5) çıkarır ve
    bilimsel bir histogram / kümülatif dağılım (CDF) grafiği kaydeder.
    """
    print("\n------------------------------------------------------------------")
    print("  [AMPİRİK ANALİZ] ARDIŞIK ZAMAN DAMGASI FARKI (DELTA t) DAĞILIMI ")
    print("------------------------------------------------------------------")

    dt_series = dt_valid[np.isfinite(dt_valid) & (dt_valid > 0)]
    if len(dt_series) == 0:
        return {}

    pct_keys = [50.0, 75.0, 90.0, 95.0, 98.0, 99.0, 99.5, 99.9]
    pct_vals = np.percentile(dt_series, pct_keys)

    quantiles_dict = {}
    for k, v in zip(pct_keys, pct_vals):
        quantiles_dict[f"p{k}"] = {
            "saniye": round(float(v), 2),
            "dakika": round(float(v / 60.0), 2)
        }
        print(f"  • Kantil %{k:<4.1f} : {v:>7.1f} sn ({v/60:>6.2f} dakika)")

    # 98% ve 99% değerleri
    p98_min = quantiles_dict["p98.0"]["dakika"]
    p99_min = quantiles_dict["p99.0"]["dakika"]
    print(f"\n  ==> Verinin %98'i için sinyal aralığı <= {p98_min} dakika ({quantiles_dict['p98.0']['saniye']} sn)")
    print(f"  ==> Verinin %99'u için sinyal aralığı <= {p99_min} dakika ({quantiles_dict['p99.0']['saniye']} sn)")
    print("  ==> Bu değer, keyfi eşik yerine veri odaklı 'Sinyal Kopma Eşiği' (Time Gap Threshold) olarak kullanılır.")

    # Grafik çizimi
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5), dpi=160)

    # 1. Histogram (0 - 30 dakika aralığı odaklı)
    dt_min = dt_series / 60.0
    dt_clipped = dt_min[dt_min <= 30.0]

    ax1.hist(dt_clipped, bins=60, color="#0284c7", edgecolor="#0f172a", alpha=0.85, density=True)
    ax1.axvline(p98_min, color="#f59e0b", linestyle="--", linewidth=1.8, label=f"%98 Eşiği: {p98_min:.1f} dk")
    ax1.axvline(p99_min, color="#dc2626", linestyle="--", linewidth=1.8, label=f"%99 Eşiği: {p99_min:.1f} dk")
    ax1.set_title("Ardışık AIS Sinyal Aralığı Histogramı (0 - 30 dk)", fontsize=11, fontweight="bold")
    ax1.set_xlabel(r"$\Delta t$ Süresi (Dakika)", fontsize=10)
    ax1.set_ylabel("Olasılık Yoğunluğu (Density)", fontsize=10)
    ax1.grid(True, linestyle="--", alpha=0.4)
    ax1.legend(loc="upper right", fontsize=9)

    # 2. Kümülatif Dağılım Fonksiyonu (ECDF)
    sorted_dt = np.sort(dt_min)
    cdf = np.arange(1, len(sorted_dt) + 1) / len(sorted_dt)

    # 0 - 60 dakika aralığında ECDF
    mask_60 = sorted_dt <= 60.0
    ax2.plot(sorted_dt[mask_60], cdf[mask_60] * 100.0, color="#16a34a", linewidth=2.0)
    ax2.axhline(98.0, color="#f59e0b", linestyle=":", linewidth=1.4)
    ax2.axhline(99.0, color="#dc2626", linestyle=":", linewidth=1.4)
    ax2.scatter([p98_min, p99_min], [98.0, 99.0], color=["#f59e0b", "#dc2626"], s=50, zorder=5)
    ax2.annotate(f"%98 ({p98_min:.1f} dk)", (p98_min, 94.0), color="#b45309", fontweight="bold", fontsize=9)
    ax2.annotate(f"%99 ({p99_min:.1f} dk)", (p99_min, 100.5), color="#b91c1c", fontweight="bold", fontsize=9)

    ax2.set_title("Kümülatif Dağılım Fonksiyonu (CDF - % Kapsama)", fontsize=11, fontweight="bold")
    ax2.set_xlabel(r"$\Delta t$ Süresi (Dakika)", fontsize=10)
    ax2.set_ylabel("Kümülatif Kapsama Oranı (%)", fontsize=10)
    ax2.set_ylim(0, 105)
    ax2.grid(True, linestyle="--", alpha=0.4)

    plt.tight_layout()
    plt.savefig(output_hist_png, bbox_inches="tight")
    plt.close(fig)
    print(f"  -> Histogram ve CDF grafiği kaydedildi: {output_hist_png}")

    payload = {
        "toplam_aralik_sayisi": int(len(dt_series)),
        "kantiller": quantiles_dict,
        "onerilen_esik_p98_dakika": p98_min,
        "onerilen_esik_p99_dakika": p99_min,
        "grafik_dosyasi": output_hist_png
    }
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"  -> Delta-t kantil sonuçları kaydedildi  : {output_json}")

    return payload


def apply_physical_and_alpha_cleaning(
    input_csv="marmara_columns_extracted.csv",
    output_csv="marmara_curated_alpha.csv",
    summary_json="kalite_ozeti.json",
    attrition_csv="temizlik_attrition_tablosu.csv",
    attrition_md="temizlik_attrition_tablosu.md",
    alpha=0.05,
    a_lat_max=1.0,           # m/s^2 maksimum yanal merkezcil ivme
    a_tangential_max=1.0,    # m/s^2 maksimum çizgisel (teğetsel) ivme
    v_max_knots=50.0,        # knot cinsinden mutlak fiziksel hız üst sınırı
    omega_max_deg_s=2.0,     # derece/sn cinsinden mutlak açısal dönüş hızı sınırı
    pos_tol_m=100.0,         # metre cinsinden GPS konum belirsizlik toleransı
    min_dt_s=2.0,            # ivme/dönüş testi için asgari zaman aralığı (sn)
    max_gap_s=600.0,         # yerel süreklilik ve hız tamamlama için azami boşluk (10 dk)
    max_fill_uncert_kn=5.0,  # eksik hız tamamlamada azami konum kaynaklı hız belirsizliği (knot)
):
    print("==================================================================")
    print("  AIS 2D ÖKLİD DÜZLEMİ KİNEMATİK VE ALPHA-METHOD KÜRASYON HATTI   ")
    print(f"  Girdi Dosyası        : {input_csv}")
    print(f"  Çıktı Dosyası        : {output_csv}")
    print("  Mesafe Yöntemi       : 2D Marmara AEQD Düzlemi (Öklid - hypot)")
    print("  Merkez Koordinat     : Lat=40.75° N, Lon=28.50° E")
    print("==================================================================")

    if not os.path.exists(input_csv):
        print(f"HATA: '{input_csv}' bulunamadı. Önce 01_extract_curated_columns.py çalıştırın.")
        return

    print("-> [1/8] Veri seti yükleniyor...")
    df = pd.read_csv(input_csv, low_memory=False)
    total_raw_rows = len(df)
    print(f"   Toplam Ham Kayıt: {total_raw_rows:,}")

    attrition_records = []

    # -------------------------------------------------------------------------
    # ADIM 1: TEMEL FORMAT, MMSI (9 Hane), ZAMAN VE DÜNYA KOORDİNAT DENETİMİ
    # -------------------------------------------------------------------------
    print("-> [2/8] MMSI (9 hane), zaman damgası ve WGS84 koordinat geçerliliği denetleniyor...")
    mmsi_num = pd.to_numeric(df["mmsi"], errors="coerce")
    valid_mmsi = mmsi_num.notna() & (mmsi_num >= 100_000_000) & (mmsi_num <= 999_999_999) & (mmsi_num == np.floor(mmsi_num))

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
    valid_ts = df["timestamp"].notna()

    lat_num = pd.to_numeric(df["latitude"], errors="coerce")
    lon_num = pd.to_numeric(df["longitude"], errors="coerce")
    valid_coord = (
        np.isfinite(lat_num) & lat_num.between(-90.0, 90.0) &
        np.isfinite(lon_num) & lon_num.between(-180.0, 180.0)
    )

    invalid_basic_mask = ~(valid_mmsi & valid_ts & valid_coord)
    invalid_basic_count = int(invalid_basic_mask.sum())

    df = df.loc[~invalid_basic_mask].copy()
    df["mmsi"] = mmsi_num.loc[df.index].astype(np.int64)
    df["latitude"] = lat_num.loc[df.index].astype(np.float64)
    df["longitude"] = lon_num.loc[df.index].astype(np.float64)

    curr_rows = len(df)
    attrition_records.append({
        "Adım": "1. Format & Geçerlilik",
        "Kural / Filtre": "9 Haneli MMSI, Geçerli Timestamp ve [-90,90],[-180,180] Koordinat",
        "Elenen Satır": invalid_basic_count,
        "Kalan Satır": curr_rows,
        "Adım Kaybı (%)": round(invalid_basic_count / total_raw_rows * 100.0, 4),
        "Kümülatif Kayıp (%)": round((total_raw_rows - curr_rows) / total_raw_rows * 100.0, 4),
        "Açıklama": "Metinsel/bozuk kimlik, geçersiz tarih ve yerküre dışı GPS noktaları elendi."
    })

    # Kronolojik sıralama
    df = df.sort_values(["mmsi", "timestamp"]).reset_index(drop=True)

    # -------------------------------------------------------------------------
    # ADIM 2: MARMARA SINIR KUTUSU VE BÖLGE GİRİŞ-ÇIKIŞ (area_pass_id) TAKİBİ
    # -------------------------------------------------------------------------
    print("-> [3/8] Marmara Denizi IHO sınır kontrolü ve giriş-çıkış bölümlemesi yapılıyor...")
    inside_marmara = (
        df["latitude"].between(MARMARA_BOUNDS["lat_min"], MARMARA_BOUNDS["lat_max"], inclusive="both") &
        df["longitude"].between(MARMARA_BOUNDS["lon_min"], MARMARA_BOUNDS["lon_max"], inclusive="both")
    )
    outside_marmara_count = int((~inside_marmara).sum())

    outside_int = (~inside_marmara).astype(np.int32)
    df["area_pass_id"] = outside_int.groupby(df["mmsi"], sort=False).cumsum()

    df = df.loc[inside_marmara].reset_index(drop=True)
    curr_rows = len(df)
    attrition_records.append({
        "Adım": "2. Marmara Sınır Kutusu",
        "Kural / Filtre": "IHO Marmara Dikdörtgeni (39.9989°-41.2329° N, 26.1742°-29.9422° E)",
        "Elenen Satır": outside_marmara_count,
        "Kalan Satır": curr_rows,
        "Adım Kaybı (%)": round(outside_marmara_count / total_raw_rows * 100.0, 4),
        "Kümülatif Kayıp (%)": round((total_raw_rows - curr_rows) / total_raw_rows * 100.0, 4),
        "Açıklama": "Marmara Denizi ve Boğazlar dışındaki çalışma alanı harici kayıtlar çıkarıldı."
    })

    # -------------------------------------------------------------------------
    # ADIM 3: 2D KARTEZYEN AEQD DÜZLEM DÖNÜŞÜMÜ (x, y metre)
    # -------------------------------------------------------------------------
    print("-> [4/8] WGS84 koordinatları Marmara 2D AEQD Kartezyen düzlemine (x, y metre) dönüştürülüyor...")
    ship_x, ship_y = project_to_marmara_xy(df["longitude"].to_numpy(), df["latitude"].to_numpy())
    df["x_m"] = ship_x
    df["y_m"] = ship_y

    # -------------------------------------------------------------------------
    # ADIM 4: TAM TEKRAR (DUPLICATE) VE AYRIŞTIRMA
    # -------------------------------------------------------------------------
    raw_speed = pd.to_numeric(df["speed"], errors="coerce")
    raw_course = pd.to_numeric(df["course"], errors="coerce")

    is_ais_1023 = np.isclose(raw_speed, 102.3, rtol=0.0, atol=1e-4)
    is_ais_1022 = np.isclose(raw_speed, 102.2, rtol=0.0, atol=1e-4)
    is_speed_negative = raw_speed < 0.0
    is_speed_invalid = np.isinf(raw_speed) | is_ais_1022 | is_speed_negative

    sog_missing = raw_speed.isna() | is_ais_1023
    sog_reported = raw_speed.mask(sog_missing | is_speed_invalid)
    df["sog_reported"] = sog_reported

    exact_dup_mask = df.duplicated(subset=["mmsi", "timestamp", "latitude", "longitude", "sog_reported"], keep="first")
    exact_dup_count = int(exact_dup_mask.sum())
    if exact_dup_count > 0:
        df = df.loc[~exact_dup_mask].reset_index(drop=True)
        sog_missing = sog_missing.loc[~exact_dup_mask].reset_index(drop=True)
        is_speed_invalid = is_speed_invalid.loc[~exact_dup_mask].reset_index(drop=True)
        raw_course = raw_course.loc[~exact_dup_mask].reset_index(drop=True)

    curr_rows = len(df)
    attrition_records.append({
        "Adım": "3. Tam Kopya (Duplicate)",
        "Kural / Filtre": "Birebir Aynı MMSI, Timestamp, Konum ve SOG Bilgisi",
        "Elenen Satır": exact_dup_count,
        "Kalan Satır": curr_rows,
        "Adım Kaybı (%)": round(exact_dup_count / total_raw_rows * 100.0, 4),
        "Kümülatif Kayıp (%)": round((total_raw_rows - curr_rows) / total_raw_rows * 100.0, 4),
        "Açıklama": "Tekrarlanan ham istasyon paketlerinin ilk kopyası korundu, mükerrerler temizlendi."
    })

    n = len(df)
    mmsi_arr = df["mmsi"].to_numpy()
    pass_arr = df["area_pass_id"].to_numpy()
    x_arr = df["x_m"].to_numpy(dtype=np.float64)
    y_arr = df["y_m"].to_numpy(dtype=np.float64)
    lat_arr = df["latitude"].to_numpy(dtype=np.float64)
    lon_arr = df["longitude"].to_numpy(dtype=np.float64)
    sog_arr = df["sog_reported"].to_numpy(dtype=np.float64)
    cog_arr = raw_course.to_numpy(dtype=np.float64)
    ts_sec = df["timestamp"].dt.as_unit("ns").astype("int64").to_numpy(dtype=np.float64) / 1e9

    # -------------------------------------------------------------------------
    # ADIM 5: ZAMANSAL VE KONUMSAL ÇAKIŞMA (Ta == Tb, Delta t == 0)
    # -------------------------------------------------------------------------
    time_conflict_mask = df.duplicated(subset=["mmsi", "timestamp"], keep=False).to_numpy()
    time_conflict_count = int(time_conflict_mask.sum())

    # -------------------------------------------------------------------------
    # ADIM 6: 2D ÖKLİD MESAFESİ VE A -> B -> C KÖPRÜ TESTİ (TEKİL GPS SIÇRAMASI)
    # -------------------------------------------------------------------------
    print("-> [5/8] 2D Düzlem Öklid mesafesi ve A->B->C tekil GPS sıçraması köprü testi uygulanıyor...")
    same_segment_base = np.zeros(n, dtype=bool)
    if n > 1:
        same_segment_base[1:] = (mmsi_arr[1:] == mmsi_arr[:-1]) & (pass_arr[1:] == pass_arr[:-1])

    dt_sec = np.full(n, np.nan, dtype=np.float64)
    dt_sec[1:] = np.where(same_segment_base[1:], ts_sec[1:] - ts_sec[:-1], np.nan)

    valid_pair = same_segment_base & (dt_sec > 0.0) & (~time_conflict_mask) & (~np.roll(time_conflict_mask, 1))

    dist_m = np.zeros(n, dtype=np.float64)
    v_calc_knots = np.zeros(n, dtype=np.float64)

    if np.any(valid_pair):
        d_m = euclidean_distance_m(
            np.roll(x_arr, 1)[valid_pair],
            np.roll(y_arr, 1)[valid_pair],
            x_arr[valid_pair],
            y_arr[valid_pair],
        )
        dist_m[valid_pair] = d_m
        # v_calc = (metre / sn) * 1.943844 knot
        v_calc_knots[valid_pair] = (d_m / dt_sec[valid_pair]) * MPS_TO_KNOTS

    geom_bad = valid_pair & (dist_m > (v_max_knots * KNOT_TO_MPS * dt_sec + pos_tol_m))

    # A -> B -> C Köprü Testi (2D Öklid ile)
    pos_spike = np.zeros(n, dtype=bool)
    if n >= 3:
        cand = np.zeros(n, dtype=bool)
        cand[1:-1] = geom_bad[1:-1] & geom_bad[2:]
        bridge_dt = np.roll(ts_sec, -1) - np.roll(ts_sec, 1)
        cand &= (bridge_dt > 0.0) & (bridge_dt <= max_gap_s)
        if np.any(cand):
            b_m = euclidean_distance_m(
                np.roll(x_arr, 1)[cand],
                np.roll(y_arr, 1)[cand],
                np.roll(x_arr, -1)[cand],
                np.roll(y_arr, -1)[cand],
            )
            b_ok = b_m <= (v_max_knots * KNOT_TO_MPS * bridge_dt[cand] + pos_tol_m)
            pos_spike[cand] = b_ok

            c_idx = np.where(pos_spike)[0] + 1
            c_idx = c_idx[c_idx < n]
            if len(c_idx) > 0:
                c_m = euclidean_distance_m(
                    x_arr[c_idx - 2], y_arr[c_idx - 2],
                    x_arr[c_idx], y_arr[c_idx]
                )
                c_dt = ts_sec[c_idx] - ts_sec[c_idx - 2]
                dist_m[c_idx] = c_m
                dt_sec[c_idx] = c_dt
                v_calc_knots[c_idx] = (c_m / c_dt) * MPS_TO_KNOTS
                geom_bad[c_idx] = False

    unresolved_geom = geom_bad & (~pos_spike) & (~np.roll(pos_spike, 1))
    position_suspicious = time_conflict_mask | pos_spike | unresolved_geom | np.roll(unresolved_geom, -1)

    # -------------------------------------------------------------------------
    # ADIM 7: EKSİK HIZLARIN (NaN ve 102.3) 2D ÖKLİD İLE TAMAMLANMASI
    # -------------------------------------------------------------------------
    local_edge = (
        valid_pair
        & (dt_sec >= min_dt_s)
        & (dt_sec <= max_gap_s)
        & (~geom_bad)
        & (~position_suspicious)
        & (~np.roll(position_suspicious, 1))
    )
    pos_uncert_kn = np.full(n, np.nan, dtype=np.float64)
    np.divide(pos_tol_m, dt_sec * KNOT_TO_MPS, out=pos_uncert_kn, where=valid_pair)

    fill_edge = local_edge & (v_calc_knots <= v_max_knots) & (pos_uncert_kn <= max_fill_uncert_kn)
    missing_arr = sog_missing.to_numpy(dtype=bool)

    fill_prev = missing_arr & fill_edge
    fill_next = missing_arr & (~fill_prev) & np.roll(fill_edge, -1)
    imputed_mask = fill_prev | fill_next

    used_sog = sog_arr.copy()
    used_sog[fill_prev] = v_calc_knots[fill_prev]
    used_sog[fill_next] = np.roll(v_calc_knots, -1)[fill_next]
    df["speed"] = used_sog

    unfilled_missing_speed = missing_arr & (~imputed_mask)
    imputed_count = int(imputed_mask.sum())
    print(f"   Eksik/102.3 Hızlardan 2D Öklid Hızıyla Kurtarılan: {imputed_count:,}")

    # -------------------------------------------------------------------------
    # ADIM 8: KİNEMATİK LİMİTLER (DÖNÜŞ, YANAL İVME, ÇİZGİSEL İVME) VE ALPHA-METHOD
    # -------------------------------------------------------------------------
    print("-> [6/8] Kinematik limitler ve 2D Öklid tabanlı Alpha-Method hesaplanıyor...")
    prev_sog_rep = np.roll(sog_arr, 1)
    prev_cog = np.roll(cog_arr, 1)
    if np.any(pos_spike):
        c_idx = np.where(pos_spike)[0] + 1
        c_idx = c_idx[c_idx < n]
        prev_sog_rep[c_idx] = sog_arr[c_idx - 2]
        prev_cog[c_idx] = cog_arr[c_idx - 2]

    # Yanal İvme & Açısal Dönüş
    valid_cog_pair = (
        local_edge
        & np.isfinite(cog_arr) & (cog_arr >= 0.0) & (cog_arr < 360.0)
        & np.isfinite(prev_cog) & (prev_cog >= 0.0) & (prev_cog < 360.0)
        & np.isfinite(used_sog)
    )
    omega_calc_deg_s = np.zeros(n, dtype=np.float64)
    a_lat_m_s2 = np.zeros(n, dtype=np.float64)

    if np.any(valid_cog_pair):
        delta_cogs = compute_minimal_cog_diff(prev_cog[valid_cog_pair], cog_arr[valid_cog_pair])
        om = delta_cogs / dt_sec[valid_cog_pair]
        v_mps = used_sog[valid_cog_pair] * KNOT_TO_MPS
        alat = v_mps * (om * (np.pi / 180.0))
        omega_calc_deg_s[valid_cog_pair] = om
        a_lat_m_s2[valid_cog_pair] = alat

    v_mps_safe = np.maximum(np.nan_to_num(used_sog, nan=0.0) * KNOT_TO_MPS, 0.1)
    w_max_dynamic = np.minimum(omega_max_deg_s, (a_lat_max / v_mps_safe) * (180.0 / np.pi))
    is_lateral_accel_exceeded = valid_cog_pair & ((a_lat_m_s2 > a_lat_max) | (omega_calc_deg_s > w_max_dynamic))

    # Mutlak Hız Sınırı (50 knot)
    is_max_speed_exceeded = (
        is_speed_invalid.to_numpy(dtype=bool)
        | (np.isfinite(sog_arr) & (sog_arr > v_max_knots))
        | (valid_pair & (v_calc_knots > v_max_knots))
    )

    # Çizgisel İvme
    both_sog_reported = local_edge & np.isfinite(sog_arr) & np.isfinite(prev_sog_rep)
    delta_v_time = np.zeros(n, dtype=np.float64)
    delta_v_time[both_sog_reported] = sog_arr[both_sog_reported] - prev_sog_rep[both_sog_reported]

    a_tangential_knots_s = a_tangential_max * MPS_TO_KNOTS  # ~1.94384 knots/sec
    lin_accel = np.zeros(n, dtype=np.float64)
    np.divide(np.abs(delta_v_time), dt_sec, out=lin_accel, where=both_sog_reported)
    is_linear_accel_exceeded = both_sog_reported & (lin_accel > a_tangential_knots_s)

    # Alpha-Method (2D Düzlem Hız Sapması)
    sog_pair_mean = 0.5 * (sog_arr + prev_sog_rep)
    delta_v_signed = np.zeros(n, dtype=np.float64)
    delta_v_signed[both_sog_reported] = v_calc_knots[both_sog_reported] - sog_pair_mean[both_sog_reported]

    valid_delta_v = delta_v_signed[both_sog_reported]
    lower_quantile_pct = (alpha / 2.0) * 100.0        # %2.5
    upper_quantile_pct = (1.0 - alpha / 2.0) * 100.0  # %97.5

    if len(valid_delta_v) >= 40:
        q_lower, q_upper = np.percentile(valid_delta_v, [lower_quantile_pct, upper_quantile_pct])
    else:
        q_lower, q_upper = -10.0, 10.0

    print(f"\n[2D ÖKLİD TABANLI ALPHA-METHOD (alpha={alpha})]")
    print(f"  • Karşılaştırılan Aralık Sayısı       : {len(valid_delta_v):,}")
    print(f"  • Lower Bound  (%{lower_quantile_pct:.1f})                : {q_lower:.3f} knot")
    print(f"  • Upper Bound (%{upper_quantile_pct:.1f})               : {q_upper:.3f} knot")

    is_alpha_outlier = both_sog_reported & ((delta_v_signed < q_lower) | (delta_v_signed > q_upper))

    # Anomali maskesi
    is_suspicious = (
        time_conflict_mask
        | pos_spike
        | unresolved_geom
        | unfilled_missing_speed
        | is_max_speed_exceeded
        | is_lateral_accel_exceeded
        | is_linear_accel_exceeded
        | is_alpha_outlier
    )

    total_suspicious = int(is_suspicious.sum())
    clean_count = n - total_suspicious

    # Attrition Tablosuna filtrelerin dökümü
    # Her kuralın tekil elenen sayısı
    filters_breakdown = [
        ("4. Zamansal Çakışma", "Ta == Tb (Delta t == 0, Farklı Konum/Hız)", int(time_conflict_mask.sum()), "Aynı saniyede çift sinyal gönderen çelişkili kayıtlar."),
        ("5. Tekil GPS Sıçraması", "A->B->C Köprü Testi (2D Düzlem Öklid)", int(pos_spike.sum()), "Yalnızca ortadaki hatalı B noktası ayıklandı, C korundu."),
        ("6. Fiziksel Hız / Mesafe Sınırı", "V_max > 50 knot veya Mesafe > V_max * dt + 100m", int((is_max_speed_exceeded | unresolved_geom).sum()), "Fiziksel 50 knot üst sınırını aşan sıçramalar."),
        ("7. Yanal İvme & Dönüş Hızı", "a_lat > 1.0 m/s² veya w_calc > w_max(v)", int(is_lateral_accel_exceeded.sum()), "Geminin dönüş manevrası fiziksel merkezcil kuvvet sınırı."),
        ("8. Çizgisel İvme Sınırı", "a_tangential > 1.0 m/s² (~1.94 knot/sn)", int(is_linear_accel_exceeded.sum()), "Motor gücüyle hızlanma/yavaşlama ivme sınırı."),
        ("9. Alpha-Method İstatistiği", f"Delta v < {q_lower:.2f} kn veya > {q_upper:.2f} kn", int(is_alpha_outlier.sum()), "%95 güven aralığının dışındaki sensör-konum uyuşmazlığı."),
        ("10. Tamamlanamayan Eksik Hız", "Sensör Hızı Boş/102.3 ve Mesafe Hesabı Uygun Değil", int(unfilled_missing_speed.sum()), "Konumdan hız türetilemeyen eksik hız kayıtları."),
    ]

    for name, rule, count, desc in filters_breakdown:
        attrition_records.append({
            "Adım": name,
            "Kural / Filtre": rule,
            "Elenen Satır": count,
            "Kalan Satır": "-",  # Çoklu kural örtüşmesi olduğu için kümülatif en son hesaplanır
            "Adım Kaybı (%)": round(count / total_raw_rows * 100.0, 4),
            "Kümülatif Kayıp (%)": "-",
            "Açıklama": desc
        })

    attrition_records.append({
        "Adım": "ÖZET BİLANÇO: ŞÜPHELİ/ELENEN",
        "Kural / Filtre": "Tüm Kinematik ve İstatistiksel Filtrelerin Birleşimi (OR)",
        "Elenen Satır": total_suspicious,
        "Kalan Satır": clean_count,
        "Adım Kaybı (%)": round(total_suspicious / total_raw_rows * 100.0, 4),
        "Kümülatif Kayıp (%)": round((total_raw_rows - clean_count) / total_raw_rows * 100.0, 4),
        "Açıklama": "Tekil şüpheli satırların tamamı nihai temiz çıktından çıkarıldı."
    })

    attrition_records.append({
        "Adım": "NİHAİ TEMİZ VERİ",
        "Kural / Filtre": "Doğrulanmış Kinematik ve 2D AEQD Koordinatlı Noktalar",
        "Elenen Satır": 0,
        "Kalan Satır": clean_count,
        "Adım Kaybı (%)": 0.0,
        "Kümülatif Kayıp (%)": round((total_raw_rows - clean_count) / total_raw_rows * 100.0, 4),
        "Açıklama": "Modelleme, interpolasyon ve segmentasyona hazır güvenilir veri seti."
    })

    attrition_df = pd.DataFrame(attrition_records)
    attrition_df.to_csv(attrition_csv, index=False, encoding="utf-8-sig")

    # Markdown formatında attrition tablosu
    try:
        md_table = attrition_df.to_markdown(index=False)
    except Exception:
        headers = list(attrition_df.columns)
        md_lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
        for _, row in attrition_df.iterrows():
            md_lines.append("| " + " | ".join(str(val) for val in row) + " |")
        md_table = "\n".join(md_lines)
    with open(attrition_md, "w", encoding="utf-8") as f:
        f.write("# AIS Kürasyon ve Veri Temizleme Adım Adım Attrition Tablosu\n\n")
        f.write(f"**Girdi Dosyası:** `{input_csv}` ({total_raw_rows:,} Satır)  \n")
        f.write(f"**Nihai Temiz Satır:** `{clean_count:,}` (%{clean_count/total_raw_rows*100:.2f})  \n\n")
        f.write(md_table)
        f.write("\n")

    print("\n==================================================================")
    print("      ADIM ADIM VERİ ELEME VE KÜRASYON ATTRITION TABLOSU          ")
    print("==================================================================")
    for rec in attrition_records:
        kalan_str = f"{rec['Kalan Satır']:,}" if isinstance(rec['Kalan Satır'], int) else str(rec['Kalan Satır'])
        print(f"{rec['Adım']:<30} | Elenen: {rec['Elenen Satır']:>9,} | Kalan: {kalan_str:>10} | Kayıp: %{rec['Adım Kaybı (%)']:<5}")
    print("==================================================================")
    print(f"-> Attrition tablosu CSV kaydedildi : {attrition_csv}")
    print(f"-> Attrition tablosu MD kaydedildi  : {attrition_md}")

    # -------------------------------------------------------------------------
    # ADIM 9: DELTA T HİSTOGRAMI VE KANTİL ANALİZİ (%98 - %99 EŞİK TESPİTİ)
    # -------------------------------------------------------------------------
    clean_mask = ~is_suspicious
    clean_mmsi = mmsi_arr[clean_mask]
    clean_ts = ts_sec[clean_mask]
    clean_same = clean_mmsi[1:] == clean_mmsi[:-1]
    clean_dt = clean_ts[1:] - clean_ts[:-1]
    clean_dt_valid = clean_dt[clean_same & (clean_dt > 0)]

    delta_t_res = plot_and_analyze_delta_t(clean_dt_valid)

    # Temiz veriyi diske kaydet
    out_cols = [
        "mmsi", "timestamp", "latitude", "longitude", "x_m", "y_m",
        "speed", "course", "heading"
    ]
    out_cols = [c for c in out_cols if c in df.columns]

    print(f"\n-> [8/8] Temizlenmiş 2D düzlem AIS verisi '{output_csv}' dosyasına yazılıyor...")
    df.loc[clean_mask, out_cols].to_csv(output_csv, index=False, chunksize=500_000)
    print(f"-> İŞLEM TAMAMLANDI! '{output_csv}' başarıyla oluşturuldu.\n")


if __name__ == "__main__":
    target_input = sys.argv[1] if len(sys.argv) > 1 else "marmara_columns_extracted.csv"
    target_output = sys.argv[2] if len(sys.argv) > 2 else "marmara_curated_alpha.csv"
    apply_physical_and_alpha_cleaning(target_input, target_output)
