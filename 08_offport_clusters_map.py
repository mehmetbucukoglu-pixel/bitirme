import pandas as pd
import folium

ports = pd.read_csv("Marmara_Liman_Listesi_v2.csv")
clusters = pd.read_csv("liman_disi_durus_kumeleri.csv").reset_index(drop=True)
clusters["cluster_no"] = clusters.index + 1

m = folium.Map(location=[40.75, 28.50], zoom_start=9, tiles="OpenStreetMap")
folium.TileLayer(
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attr="Esri World Imagery",
    name="Uydu (Esri)",
    show=True,
).add_to(m)

# Katman 1: Mevcut 27 v2 Liman
fg_ports = folium.FeatureGroup(name="Mevcut 27 Liman (v2)", show=True)
for _, p in ports.iterrows():
    folium.Circle(
        location=[p["lat"], p["lon"]],
        radius=float(p["radius_m"]),
        color="#2ca02c",
        weight=2,
        fill=True,
        fill_opacity=0.18,
        tooltip=f"{p['port_code']} - {p['port_name']} (R={int(p['radius_m'])}m)",
    ).add_to(fg_ports)
fg_ports.add_to(m)

# Katman 2: Numaralandırılmış Liman Dışı Kümeler
fg_moored = folium.FeatureGroup(name="Liman-Benzeri Kümeler (Numaralı)", show=True)
fg_anchor = folium.FeatureGroup(name="Demirleme & Karışık Kümeler (Numaralı)", show=True)

for _, c in clusters.iterrows():
    no = int(c["cluster_no"])
    verdict = str(c["verdict"])
    is_moored = "LİMAN-BENZERİ" in verdict
    bg = "#ff4d4d" if is_moored else ("#ffa500" if "KARIŞIK" in verdict else "#1e90ff")
    target_fg = fg_moored if is_moored else fg_anchor

    popup_html = (
        f"<b>Küme #{no}</b> ({verdict})<br>"
        f"Koordinat: <code>{c['lat']:.4f}, {c['lon']:.4f}</code><br>"
        f"Farklı Gemi: <b>{int(c['ships'])}</b> | Duruş Sayısı: <b>{int(c['episodes'])}</b><br>"
        f"Medyan Bekleme: {c['dwell_med_h']} saat | Toplam: {int(c['total_ship_h'])} gemi-saat<br>"
        f"Medyan Saçılım (p90): {int(c['spread_med_m'])} m | Moored Oranı: {c['moored_share']:.2f}"
    )

    icon_html = (
        f'<div style="background:{bg};color:#fff;font-weight:bold;font-size:11px;'
        f'border:1.5px solid #fff;border-radius:10px;padding:1px 5px;'
        f'box-shadow:0 1px 3px rgba(0,0,0,0.6);white-space:nowrap;">#{no}</div>'
    )
    folium.Marker(
        location=[c["lat"], c["lon"]],
        icon=folium.DivIcon(html=icon_html, icon_size=(30, 18), icon_anchor=(15, 9)),
        popup=folium.Popup(popup_html, max_width=320),
        tooltip=f"#{no} | {int(c['ships'])} gemi | {verdict}",
    ).add_to(target_fg)

fg_moored.add_to(m)
fg_anchor.add_to(m)

folium.LayerControl(collapsed=False).add_to(m)
out_html = "liman_disi_kumeler_haritasi.html"
m.save(out_html)
print(f"-> '{out_html}' oluşturuldu ({len(clusters)} numaralı küme).")
