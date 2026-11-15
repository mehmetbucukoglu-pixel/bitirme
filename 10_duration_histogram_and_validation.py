import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("marmara_segment_summary.csv")
df["pure_sailing_min"] = (df["duration_min"] - df["anchorage_wait_min"]).clip(lower=0)

print("=== DEMİRLEMELİ vs DİREKT SEYİR KARŞILAŞTIRMASI (duration_min) ===")
for flag, grp in df.groupby(df["anchorage_wait_min"] > 0):
    lbl = "Demirlemeli (anchorage > 0)" if flag else "Direkt Seyir (anchorage == 0)"
    q = grp["duration_min"].quantile([0.25, 0.5, 0.75, 0.9]).round(1).to_dict()
    print(f"  {lbl:<30}: {len(grp):>6,} segment | medyan={q[0.5]} dk, p90={q[0.9]} dk")

print("\n=== BAŞLICA ROTA MEDYAN SÜRELERİ (Doğrulama) ===")
p2p = df[df["segment_category"].isin(["PORT_TO_PORT", "GATE_TO_GATE", "PORT_TO_GATE", "GATE_TO_PORT"])]
top_routes = (
    p2p.groupby(["origin_port_code", "dest_port_code"])
    .agg(n=("duration_min", "size"), med_min=("duration_min", "median"),
         med_pure_min=("pure_sailing_min", "median"), anch_pct=("anchorage_wait_min", lambda s: (s > 0).mean() * 100))
    .sort_values("n", ascending=False).head(10).round(1)
)
print(top_routes.to_string())

# Histogram (2 panel: 0-360 dk detay + log ölçekli tam dağılım)
fig, axes = plt.subplots(1, 2, figsize=(14, 5), dpi=130)

# Sol panel: 0 - 360 dk (6 saat) arası kategori bazlı
sub = df[df["duration_min"] <= 360]
cats = [
    ("PORT_TO_PORT", "#2ca02c"),
    ("GATE_TO_GATE", "#1f77b4"),
    ("PORT_TO_GATE / GATE_TO_PORT", "#9467bd"),
    ("PARTIAL", "#7f7f7f"),
]
for name, col in cats:
    if "/" in name:
        vals = sub[sub["segment_category"].isin(["PORT_TO_GATE", "GATE_TO_PORT"])]["duration_min"]
    else:
        vals = sub[sub["segment_category"] == name]["duration_min"]
    axes[0].hist(vals, bins=45, alpha=0.45, label=f"{name} (n={len(vals):,})", color=col, density=True)

axes[0].axvline(df["duration_min"].median(), color="red", linestyle="--", linewidth=1.5,
                label=f"Genel Medyan: {df['duration_min'].median():.1f} dk")
axes[0].set_title("Segment Süre Dağılımı (0 - 360 dk, Normalize)")
axes[0].set_xlabel("Süre (dakika)")
axes[0].set_ylabel("Yoğunluk")
axes[0].legend(fontsize=8)
axes[0].grid(alpha=0.25)

# Sağ panel: Log10 süre dağılımı (tüm segmentler: Direkt vs Demirlemeli)
d0 = np.log10(df[df["anchorage_wait_min"] == 0]["duration_min"].clip(lower=1))
d1 = np.log10(df[df["anchorage_wait_min"] > 0]["duration_min"].clip(lower=1))
axes[1].hist(d0, bins=40, alpha=0.6, color="#2ca02c", label=f"Direkt Seyir (n={len(d0):,})")
axes[1].hist(d1, bins=40, alpha=0.6, color="#ff7f0e", label=f"Demirlemeli (n={len(d1):,})")
xticks = [1, np.log10(30), np.log10(60), np.log10(180), np.log10(720), np.log10(1440), np.log10(4320)]
xlabels = ["10dk", "30dk", "1s", "3s", "12s", "24s", "3gün"]
axes[1].set_xticks(xticks)
axes[1].set_xticklabels(xlabels)
axes[1].set_title("Tüm Segmentler: Direkt vs Demirlemeli (Log Ölçek)")
axes[1].set_xlabel("Toplam Süre")
axes[1].set_ylabel("Segment Sayısı")
axes[1].legend(fontsize=9)
axes[1].grid(alpha=0.25)

plt.tight_layout()
plt.savefig("segment_sure_histogrami_v2.png")
print("\n-> 'segment_sure_histogrami_v2.png' kaydedildi.")
