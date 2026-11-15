"""
PORT_ROUNDTRIP neden araştırması:
Doğal gidiş-dönüş (römorkör/vapur/açık deniz çıkıp dönme) vs sınırda titreme/segmentasyon hatası ayrımı.
"""
import numpy as np
import pandas as pd

sum_df = pd.read_csv("marmara_segment_summary.csv")
rt = sum_df[sum_df["segment_category"] == "PORT_ROUNDTRIP"].copy()
print(f"Toplam PORT_ROUNDTRIP: {len(rt):,}")

# 1. Süre ve hız dağılımı
print("\n--- Süre (dk) ve Ortalama Hız (kn) Dağılımı ---")
print(rt[["duration_min", "mean_speed_kn", "max_speed_kn", "anchorage_wait_min"]].describe().round(2).to_string())

# 2. MMSI ve Liman bazında yoğunluk
print("\n--- En Çok PORT_ROUNDTRIP Yapan 15 Liman ---")
print(rt.groupby(["origin_port_code", "origin_port_name"]).agg(
    roundtrip=("global_segment_id", "size"),
    unique_mmsi=("mmsi", "nunique"),
    med_dur_min=("duration_min", "median"),
    med_max_kn=("max_speed_kn", "median"),
).sort_values("roundtrip", ascending=False).head(15).to_string())

# 3. Nokta verisinden liman merkezine max uzaklaşma (daire dışına ne kadar çıkmış?)
print("\n--- Yörünge nokta verisinden daire dışına taşma mesafesi hesaplanıyor ---")
pts = pd.read_csv(
    "marmara_segmented_trajectories.csv",
    usecols=["segment_id", "segment_category", "nearest_port_dist_m"],
)
pts_rt = pts[pts["segment_category"] == "PORT_ROUNDTRIP"]
max_dist = pts_rt.groupby("segment_id")["nearest_port_dist_m"].max()
rt["max_dist_from_port_m"] = rt["global_segment_id"].map(max_dist)

ports = pd.read_csv("Marmara_Liman_Listesi_v2.csv").set_index("port_code")
rt["port_radius_m"] = rt["origin_port_code"].map(ports["radius_m"])
rt["overshoot_m"] = rt["max_dist_from_port_m"] - rt["port_radius_m"]

# Sınıflandırma:
# A) Sınır Titremesi (Segmentasyon Hatası): daire dışına <= 500 m taşmış veya süresi < 20 dk
# B) Doğal Kısa Tur / Römorkör / Vapur: dışarı > 500 m çıkmış ve >= 20 dk, <= 120 dk
# C) Uzun Açık Deniz + Dönüş / Demirleyip Dönüş: > 120 dk veya demirleme var
conds = [
    (rt["overshoot_m"] <= 500.0) | (rt["duration_min"] < 20.0),
    (rt["duration_min"] > 120.0) | (rt["anchorage_wait_min"] > 0),
]
choices = ["SINIR_TITREMESI_VEYA_KISA_CIK_GIR", "UZUN_VEYA_DEMIRLI_DONUS"]
rt["rt_type"] = np.select(conds, choices, default="DOGAL_ORTA_TUR")

print("\n--- PORT_ROUNDTRIP TİP DAĞILIMI ---")
print(rt["rt_type"].value_counts().to_string())
print("\nOranlar:")
print((rt["rt_type"].value_counts(normalize=True) * 100).round(1).to_string())

rt.to_csv("port_roundtrip_analizi.csv", index=False, encoding="utf-8-sig")
print("\n-> 'port_roundtrip_analizi.csv' kaydedildi.")
