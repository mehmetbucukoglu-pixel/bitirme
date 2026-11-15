"""
Segment Süre Aykırılığı, Hız Tutarlılığı ve Kaçırılan Yavaş Sürüklenme (0.5-1.5 kn) Denetimi
"""
import numpy as np
import pandas as pd

print("-> Segment özetleri okunuyor...")
sum_df = pd.read_csv("marmara_segment_summary.csv")

print("-> Yörünge nokta verisinden gerçek yol, kuş uçuşu mesafe ve 0.5-1.5 kn süre hesaplanıyor...")
pts = pd.read_csv(
    "marmara_segmented_trajectories.csv",
    usecols=["segment_id", "timestamp", "x_m", "y_m", "speed"],
)
pts["ts"] = pd.to_datetime(pts["timestamp"], utc=True, errors="coerce").dt.as_unit("ns").astype("int64") / 1e9

seg_id = pts["segment_id"].to_numpy()
x = pts["x_m"].to_numpy(dtype=np.float64)
y = pts["y_m"].to_numpy(dtype=np.float64)
ts = pts["ts"].to_numpy(dtype=np.float64)
spd = pts["speed"].to_numpy(dtype=np.float64)

same = np.zeros(len(pts), dtype=bool)
same[1:] = seg_id[1:] == seg_id[:-1]

step_dist = np.zeros(len(pts), dtype=np.float64)
step_dist[1:] = np.where(same[1:], np.hypot(x[1:] - x[:-1], y[1:] - y[:-1]), 0.0)

dt = np.zeros(len(pts), dtype=np.float64)
dt[1:] = np.where(same[1:], np.maximum(ts[1:] - ts[:-1], 0.0), 0.0)

slow_05_15_dt = np.where((spd > 0.5) & (spd <= 1.5), dt, 0.0)

pts["step_dist"] = step_dist
pts["slow_05_15_dt"] = slow_05_15_dt

agg = pts.groupby("segment_id", sort=False).agg(
    actual_dist_m=("step_dist", "sum"),
    x0=("x_m", "first"),
    y0=("y_m", "first"),
    x1=("x_m", "last"),
    y1=("y_m", "last"),
    slow_05_15_sec=("slow_05_15_dt", "sum"),
).reset_index().rename(columns={"segment_id": "global_segment_id"})

df = sum_df.merge(agg, on="global_segment_id", how="left")
df["straight_dist_m"] = np.hypot(df["x1"] - df["x0"], df["y1"] - df["y0"])
df["detour_ratio"] = np.where(df["straight_dist_m"] >= 500.0, df["actual_dist_m"] / df["straight_dist_m"], np.nan)
df["effective_speed_kn"] = np.where(df["duration_min"] > 0, (df["actual_dist_m"] / (df["duration_min"] * 60.0)) * 1.943844, 0.0)
df["speed_diff_kn"] = (df["mean_speed_kn"] - df["effective_speed_kn"]).abs()
df["slow_05_15_min"] = (df["slow_05_15_sec"] / 60.0).round(2)

# Tutarlılık bayrakları
flags = []
for _, r in df.iterrows():
    f = []
    if r["duration_min"] < 10.0:
        f.append("TOO_SHORT_LT_10M")
    if r["anchorage_wait_min"] == 0 and r["slow_05_15_min"] >= 30.0:
        f.append("MISSED_SLOW_DRIFT_05_15KN")
    if r.get("duration_check_status") == "LONG":
        f.append("ROUTE_DURATION_LONG")
    if r["speed_diff_kn"] > 5.0 and r["duration_min"] >= 10.0:
        f.append("SPEED_MISMATCH_GT_5KN")
    if pd.notna(r["detour_ratio"]) and r["detour_ratio"] > 2.5 and r["segment_category"] != "PORT_ROUNDTRIP":
        f.append("HIGH_DETOUR_GT_2_5")
    flags.append(" | ".join(f) if f else "OK")

df["audit_flag"] = flags

print("\n=== TUTARLILIK DENETİM ÖZETİ ===")
print(df["audit_flag"].value_counts().head(15).to_string())

print("\n=== DİREKT SEYİR (>= 180 DK, anch == 0) İÇİNDEKİ BULGULAR ===")
d3 = df[(df["anchorage_wait_min"] == 0) & (df["duration_min"] >= 180)]
print(f"Toplam >= 3 saat direkt seyir: {len(d3):,}")
print(d3["audit_flag"].value_counts().to_string())

out_cols = [
    "global_segment_id", "mmsi", "segment_category", "origin_port_code", "dest_port_code",
    "duration_min", "anchorage_wait_min", "slow_05_15_min", "mean_speed_kn",
    "effective_speed_kn", "speed_diff_kn", "actual_dist_m", "straight_dist_m",
    "detour_ratio", "duration_check_status", "audit_flag",
]
df[out_cols].to_csv("segment_tutarlilik_raporu.csv", index=False, encoding="utf-8-sig")
print("\n-> 'segment_tutarlilik_raporu.csv' kaydedildi.")
