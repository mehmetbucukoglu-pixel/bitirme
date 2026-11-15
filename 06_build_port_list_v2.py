"""
Fine-tune edilmiş liman listesi üretir -> Marmara_Liman_Listesi_v2.csv
Kaynak: Marmara_Final_Liman_Listesi.xlsx (orijinal, değiştirilmez) + liman_saglik_raporu.csv (önerilen merkezler)
Yön kuralı: yukarı = kuzey (+y), sağ = doğu (+x). 1 yarıçap (R) = 500 m.
"""
import importlib.util
import numpy as np
import pandas as pd
from pyproj import Transformer

spec = importlib.util.spec_from_file_location("seg_mod", "03_trajectory_segmentation.py")
seg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seg)
INV = Transformer.from_crs(seg.MARMARA_AEQD_CRS, "EPSG:4326", always_xy=True)
R = 500.0

orig = seg.load_marmara_ports("Marmara_Final_Liman_Listesi.xlsx").set_index("port_code")
rep = pd.read_csv("liman_saglik_raporu.csv").set_index("port_code")


def xy(lat, lon):
    x, y = seg.project_to_marmara_xy([lon], [lat])
    return float(x[0]), float(y[0])


def O(code):  # orijinal merkez (x, y)
    return orig.loc[code, "x_m"], orig.loc[code, "y_m"]


def S(code):  # önerilen merkez (x, y)
    return xy(rep.loc[code, "suggested_lat"], rep.loc[code, "suggested_lon"])


def shift(p, dx=0.0, dy=0.0):
    return p[0] + dx, p[1] + dy


def median(*pts):
    a = np.array(pts)
    return float(np.median(a[:, 0])), float(np.median(a[:, 1]))


# (yeni kod, ad, merkez(x,y), yarıçap_m, birleştirilen kodlar, not)
rows = [
    ("MRM-F004", orig.loc["MRM-F004", "port_name"], S("MRM-F004"), 1000, "F004", "önerilen merkez"),
    ("MRM-F005", orig.loc["MRM-F005", "port_name"], shift(O("MRM-F005"), dy=2 * R), 2000, "F005", "2R kuzey (VARSAYIM: çelişen 2 talimattan ikincisi)"),
    ("MRM-F006", orig.loc["MRM-F006", "port_name"], S("MRM-F006"), 2000, "F006", "önerilen merkez"),
    ("MRM-F007", orig.loc["MRM-F007", "port_name"], shift(O("MRM-F007"), dy=R), 2000, "F007", "1R kuzey; F008 silindi"),
    ("MRM-F009", orig.loc["MRM-F009", "port_name"], shift(O("MRM-F009"), dx=R), 500, "F009", "1R doğu"),
    ("MRM-F042", "Marmara Adası Kuzey — Saraylar", xy(40.660, 27.662), 1000, "YENI", "veri kümesinden"),
    ("MRM-F010", orig.loc["MRM-F010", "port_name"], S("MRM-F010"), 2000, "F010", "önerilen merkez"),
    ("MRM-F011", orig.loc["MRM-F011", "port_name"], S("MRM-F011"), 650, "F011", "önerilen merkez"),
    ("MRM-F012", "Bandırma (Çelebi + WPI)", S("MRM-F012"), 2500, "F012+F013", "F012 önerilen merkez"),
    ("MRM-F014", orig.loc["MRM-F014", "port_name"], S("MRM-F014"), 650, "F014", "önerilen merkez"),
    ("MRM-F015", orig.loc["MRM-F015", "port_name"], shift(O("MRM-F015"), dx=-2 * R / np.sqrt(2), dy=2 * R / np.sqrt(2)), 500, "F015", "2R kuzeybatı"),
    ("MRM-F016", "Ambarlı (Marport + WPI)", O("MRM-F016"), 2000, "F016+F017", "F016 merkezi"),
    ("MRM-F018", orig.loc["MRM-F018", "port_name"], O("MRM-F018"), 500, "F018", "DEĞİŞMEDİ (talimat yok)"),
    ("MRM-F019", orig.loc["MRM-F019", "port_name"], shift(O("MRM-F019"), dx=-R), 500, "F019", "1R batı (VARSAYIM: 'biraz')"),
    ("MRM-F023", orig.loc["MRM-F023", "port_name"], O("MRM-F023"), 500, "F023", "DEĞİŞMEDİ (talimat yok, boğaz kapısının kuzeyinde)"),
    ("MRM-F024", "Gemlik (Borusan + Gemport + WPI)", shift(O("MRM-F024"), dx=-R), 3000, "F024+F025+F026", "F024 dairesinin en batı noktası"),
    ("MRM-F028", orig.loc["MRM-F028", "port_name"], S("MRM-F028"), 650, "F028", "önerilen merkez"),
    ("MRM-F029", "Pendik–Tuzla (DFDS + Tuzla)", (0.65 * S("MRM-F029")[0] + 0.35 * S("MRM-F027")[0], 0.65 * S("MRM-F029")[1] + 0.35 * S("MRM-F027")[1]), 2000, "F027+F029", "önerilen merkezler, F029 %65"),
    ("MRM-F030", orig.loc["MRM-F030", "port_name"], shift(S("MRM-F030"), dx=R), 2000, "F030", "önerilen merkez + 1R doğu"),
    ("MRM-F043", "Altınova Tersaneler Bölgesi", xy(40.713, 29.472), 2500, "YENI", "veri kümesinden (İzmit kapısının batısında kalacak şekilde)"),
    ("MRM-F031", "Gebze–Dilovası (Kaba Burnu + Yılport Gebze + Gebze)", median(S("MRM-F031"), S("MRM-F032"), S("MRM-F033")), 2500, "F031+F032+F033", "önerilen merkezlerin medyanı"),
    ("MRM-F034", orig.loc["MRM-F034", "port_name"], shift(O("MRM-F034"), dx=2 * R * np.cos(np.radians(60)), dy=2 * R * np.sin(np.radians(60))), 1200, "F034", "2R, 60° kuzeydoğu"),
    ("MRM-F036", orig.loc["MRM-F036", "port_name"], shift(O("MRM-F036"), dx=4 * R), 4000, "F036", "4R doğu"),
    ("MRM-F037", orig.loc["MRM-F037", "port_name"], S("MRM-F037"), 500, "F037", "önerilen merkez"),
    ("MRM-F038", "Derince (Burun + Koruma Klor)", median(S("MRM-F038"), S("MRM-F039")), 1500, "F038+F039", "önerilen merkezlerin ortalaması"),
    ("MRM-F040", orig.loc["MRM-F040", "port_name"], S("MRM-F040"), 2000, "F040", "önerilen merkez"),
    ("MRM-F041", orig.loc["MRM-F041", "port_name"], S("MRM-F041"), 650, "F041", "önerilen merkez"),
]
# Silinenler: F001-F003 (Çanakkale kapısı dışı), F008 (kara), F020-F022 (İstanbul kapısı üstü), F035 (kara)

out = []
for code, name, (x, y), r, merged, note in rows:
    lon, lat = INV.transform(x, y)
    out.append({"port_code": code, "port_name": name, "lat": round(lat, 6), "lon": round(lon, 6),
                "radius_m": r, "merged_from": merged, "note": note})
out = pd.DataFrame(out)
out.to_csv("Marmara_Liman_Listesi_v2.csv", index=False, encoding="utf-8-sig")
print(out.to_string())

# Çakışma kontrolü
P = seg.project_to_marmara_xy(out["lon"].to_numpy(), out["lat"].to_numpy())
for i in range(len(out)):
    for j in range(i + 1, len(out)):
        d = np.hypot(P[0][i] - P[0][j], P[1][i] - P[1][j])
        if d < out.radius_m[i] + out.radius_m[j]:
            print(f"ÇAKIŞMA: {out.port_code[i]} - {out.port_code[j]}  mesafe {d:.0f} m < {out.radius_m[i] + out.radius_m[j]} m")
