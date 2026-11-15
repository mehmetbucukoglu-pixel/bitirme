import numpy as np, pandas as pd
df = pd.read_csv("marmara_curated_alpha.csv", usecols=["mmsi", "latitude", "longitude", "speed"])
s = df[df["speed"] <= 0.5]
boxes = {
    "MARMARA_ADASI_KUZEY": (40.60, 40.70, 27.45, 27.75),
    "ALTINOVA_IZMIT_KOPRU_SOLALT": (40.66, 40.76, 29.38, 29.52),
}
for name, (la0, la1, lo0, lo1) in boxes.items():
    b = s[(s.latitude.between(la0, la1)) & (s.longitude.between(lo0, lo1))].copy()
    b["la"] = (b.latitude / 0.005).round() * 0.005
    b["lo"] = (b.longitude / 0.005).round() * 0.005
    g = b.groupby(["la", "lo"]).agg(n=("mmsi", "size"), ships=("mmsi", "nunique")).reset_index()
    print(name, len(b), "points")
    print(g.sort_values("ships", ascending=False).head(15).to_string())
