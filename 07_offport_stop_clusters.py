"""
Liman dışı duruş kümeleri analizi: liman mı, demirleme mi?
Ayırt edici: duruş epizodu içindeki konum saçılımı (swing).
  - Rıhtıma bağlı (moored) gemi: konum neredeyse sabit, p90 saçılım < ~60 m
  - Demirli (anchored) gemi: zincir etrafında salınır, p90 saçılım ~100-400 m
"""
import importlib.util
import numpy as np
import pandas as pd

spec = importlib.util.spec_from_file_location("seg_mod", "03_trajectory_segmentation.py")
seg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seg)

STOP_KN, GAP_S, MIN_EP_MIN, MOORED_M = 0.5, 12 * 60, 30, 60.0

ports = seg.load_marmara_ports("Marmara_Liman_Listesi_v2.csv")
df = pd.read_csv("marmara_curated_alpha.csv", usecols=["mmsi", "timestamp", "latitude", "longitude", "x_m", "y_m", "speed"])
df["ts"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce").dt.as_unit("ns").astype("int64") / 1e9
df = df.sort_values(["mmsi", "ts"]).reset_index(drop=True)

idx, dist = seg.find_nearest_ports_2d_chunked(df.x_m.to_numpy(), df.y_m.to_numpy(), ports.x_m.to_numpy(),
                                              ports.y_m.to_numpy(), port_radius_arr=ports.radius_m.to_numpy())
df["in_port"] = dist <= ports.radius_m.to_numpy()[idx]

slow = (df.speed.to_numpy() <= STOP_KN) & ~df.in_port.to_numpy()
mm, ts = df.mmsi.to_numpy(), df.ts.to_numpy()
brk = np.ones(len(df), bool)
brk[1:] = (~slow[1:]) | (~slow[:-1]) | (mm[1:] != mm[:-1]) | (ts[1:] - ts[:-1] > GAP_S)
ep = np.cumsum(brk)
s = df.loc[slow, ["mmsi", "ts", "latitude", "longitude", "x_m", "y_m"]].copy()
s["ep"] = ep[slow]

g = s.groupby("ep")
e = g.agg(mmsi=("mmsi", "first"), t0=("ts", "min"), t1=("ts", "max"), lat=("latitude", "median"),
          lon=("longitude", "median"), xm=("x_m", "median"), ym=("y_m", "median"), n=("ts", "size"))
e["dur_h"] = (e.t1 - e.t0) / 3600
e = e[(e.dur_h * 60 >= MIN_EP_MIN) & (e.n >= 5)]
s = s[s.ep.isin(e.index)]
s["d"] = np.hypot(s.x_m - s.ep.map(e.xm), s.y_m - s.ep.map(e.ym))
e["spread_p90_m"] = s.groupby("ep")["d"].quantile(0.9)
e["moored"] = e.spread_p90_m < MOORED_M
print(f"Liman dışı >=30 dk duruş epizodu: {len(e):,}")

# ~1.5 km grid kümeleme
e["cell"] = list(zip((e.lat / 0.0135).round().astype(int), (e.lon / 0.018).round().astype(int)))
c = e.groupby("cell").agg(lat=("lat", "median"), lon=("lon", "median"), ships=("mmsi", "nunique"),
                          episodes=("mmsi", "size"), dwell_med_h=("dur_h", "median"),
                          total_ship_h=("dur_h", "sum"), spread_med_m=("spread_p90_m", "median"),
                          moored_share=("moored", "mean")).reset_index(drop=True)
c = c[c.ships >= 5].sort_values("ships", ascending=False)


def region(r):
    la, lo = r.lat, r.lon
    if 40.84 <= la <= 40.90 and 29.03 <= lo <= 29.14: return "ADALAR (Prens Adaları)"
    if 40.40 <= la <= 40.56 and 27.70 <= lo <= 28.05: return "KAPIDAĞ YARIMADASI"
    if 40.55 <= la <= 40.70 and 27.45 <= lo <= 27.75: return "MARMARA ADASI"
    if 40.45 <= la <= 40.62 and 27.40 <= lo <= 27.70: return "AVŞA / PAŞALİMANI / EKİNLİK"
    if 40.96 <= la <= 41.02 and 28.97 <= lo <= 29.06: return "KADIKÖY–MODA–FENERBAHÇE"
    return ""


c["region"] = c.apply(region, axis=1)
c["verdict"] = np.select(
    [c.moored_share >= 0.5, c.moored_share <= 0.2],
    ["LİMAN-BENZERİ (rıhtıma bağlı)", "DEMİRLEME"], "KARIŞIK")
c = c.round({"lat": 4, "lon": 4, "dwell_med_h": 1, "total_ship_h": 0, "spread_med_m": 0, "moored_share": 2})
c.to_csv("liman_disi_durus_kumeleri.csv", index=False, encoding="utf-8-sig")
pd.set_option("display.width", 250)
print("\n=== EN ÇOK GEMİ DURAN 30 KÜME ===")
print(c.head(30).to_string(index=False))
print("\n=== ADA BÖLGELERİ ===")
print(c[c.region != ""].to_string(index=False))
