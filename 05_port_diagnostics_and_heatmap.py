import os
import importlib.util
import numpy as np
import pandas as pd
import folium
from folium.plugins import HeatMap

# 03_trajectory_segmentation.py içindeki load_marmara_ports fonksiyonunu yükle
spec = importlib.util.spec_from_file_location("seg_mod", "03_trajectory_segmentation.py")
seg_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seg_mod)


def main():
    ports_df = seg_mod.load_marmara_ports("Marmara_Final_Liman_Listesi.xlsx")
    print(f"-> {len(ports_df)} liman yüklendi.")

    traj_csv = "marmara_segmented_trajectories.csv"
    sum_csv = "marmara_segment_summary.csv"

    if not os.path.exists(traj_csv) or not os.path.exists(sum_csv):
        print("HATA: marmara_segmented_trajectories.csv veya marmara_segment_summary.csv bulunamadı.")
        return

    print("-> Segment özetleri okunuyor...")
    sum_df = pd.read_csv(sum_csv)

    print("-> Tüm temiz noktalar (marmara_curated_alpha.csv) okunuyor...")
    usecols = ["mmsi", "latitude", "longitude", "x_m", "y_m", "speed"]
    full_df = pd.read_csv("marmara_curated_alpha.csv", usecols=usecols)
    slow_df = full_df[full_df["speed"] <= 0.5].copy()
    del full_df
    idx, dist = seg_mod.find_nearest_ports_2d_chunked(
        slow_df["x_m"].to_numpy(), slow_df["y_m"].to_numpy(),
        ports_df["x_m"].to_numpy(), ports_df["y_m"].to_numpy(),
    )
    slow_df["nearest_port_code"] = ports_df["port_code"].to_numpy()[idx]
    slow_df["nearest_port_dist_m"] = dist
    print(f"-> Toplam duruş noktası (speed <= 0.5): {len(slow_df):,}")

    # Önerilen merkez: 2 km içindeki duran noktaların medyanı
    near2k = slow_df[slow_df["nearest_port_dist_m"] <= 2000.0]
    med = near2k.groupby("nearest_port_code")[["latitude", "longitude"]].median()
    ships_in = slow_df[slow_df["nearest_port_dist_m"] <= 500.0].groupby("nearest_port_code")["mmsi"].nunique()
    ships_ring = near2k[near2k["nearest_port_dist_m"] > 500.0].groupby("nearest_port_code")["mmsi"].nunique()
    p50_dist = near2k.groupby("nearest_port_code")["nearest_port_dist_m"].median()

    # 1. Liman Sağlık Raporu
    inside = slow_df[slow_df["nearest_port_dist_m"] <= 500.0].groupby("nearest_port_code").size()
    near_out = slow_df[
        (slow_df["nearest_port_dist_m"] > 500.0) & (slow_df["nearest_port_dist_m"] <= 2000.0)
    ].groupby("nearest_port_code").size()

    dep_counts = sum_df[sum_df["origin_type"] == "PORT"].groupby("origin_port_code").size()
    arr_counts = sum_df[sum_df["dest_type"] == "PORT"].groupby("dest_port_code").size()
    rt_counts = sum_df[sum_df["segment_category"] == "PORT_ROUNDTRIP"].groupby("origin_port_code").size()

    report_rows = []
    for _, row in ports_df.iterrows():
        code = row["port_code"]
        in_500 = int(inside.get(code, 0))
        out_500_2000 = int(near_out.get(code, 0))
        out_ratio = round(out_500_2000 / (in_500 + out_500_2000 + 1), 3)
        deps = int(dep_counts.get(code, 0))
        arrs = int(arr_counts.get(code, 0))
        rts = int(rt_counts.get(code, 0))

        flags = []
        if out_ratio > 0.5 and out_500_2000 > 100:
            flags.append("KAPSAMA_SORUNU")
        if rts >= 20:
            flags.append("PING_PONG_YUKSEK")
        if (deps + arrs) < 5:
            flags.append("DUSUK_AKTIVITE")
        status = " | ".join(flags) if flags else "OK"

        report_rows.append({
            "port_code": code,
            "port_name": row["port_name"],
            "lat": row["lat"],
            "lon": row["lon"],
            "inside_500m_stops": in_500,
            "near_500_2000m_stops": out_500_2000,
            "outside_ratio": out_ratio,
            "ships_stopped_in_500m": int(ships_in.get(code, 0)),
            "ships_stopped_500_2000m": int(ships_ring.get(code, 0)),
            "median_stop_dist_m": round(float(p50_dist.get(code, np.nan)), 0),
            "suggested_lat": round(float(med["latitude"].get(code, np.nan)), 5),
            "suggested_lon": round(float(med["longitude"].get(code, np.nan)), 5),
            "departures": deps,
            "arrivals": arrs,
            "roundtrips_pingpong": rts,
            "status_flag": status,
        })

    report_df = pd.DataFrame(report_rows).sort_values(
        by=["outside_ratio", "roundtrips_pingpong"], ascending=[False, False]
    )
    report_df.to_csv("liman_saglik_raporu.csv", index=False, encoding="utf-8-sig")
    print("-> 'liman_saglik_raporu.csv' kaydedildi.")
    print("\n--- ÖZET DURUM DAĞILIMI ---")
    print(report_df["status_flag"].value_counts().to_string())

    # 2. İnteraktif Denetim Haritası (Folium)
    print("\n-> İnteraktif harita oluşturuluyor...")
    m = folium.Map(location=[40.75, 28.50], zoom_start=9, tiles="OpenStreetMap")
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri World Imagery", name="Uydu (Esri)",
    ).add_to(m)

    # Katman 1: 41 Liman ve Daireleri
    fg_ports = folium.FeatureGroup(name="41 Liman (500m & 1500m Daireler)", show=True)
    for _, r in report_df.iterrows():
        color = "green" if r["status_flag"] == "OK" else ("red" if "KAPSAMA_SORUNU" in r["status_flag"] else "orange")
        popup_html = (
            f"<b>{r['port_code']} - {r['port_name']}</b><br>"
            f"Durum: <b>{r['status_flag']}</b><br>"
            f"0-500m Duruş: {r['inside_500m_stops']:,}<br>"
            f"500-2000m Duruş: {r['near_500_2000m_stops']:,} (Oran: {r['outside_ratio']:.2f})<br>"
            f"Kalkış/Varış: {r['departures']} / {r['arrivals']}<br>"
            f"Roundtrip (Ping-Pong): {r['roundtrips_pingpong']}"
        )
        folium.Circle(
            location=[r["lat"], r["lon"]],
            radius=500,
            color=color,
            fill=True,
            fill_opacity=0.25,
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=f"{r['port_code']} ({r['status_flag']})",
        ).add_to(fg_ports)

        folium.Circle(
            location=[r["lat"], r["lon"]],
            radius=1500,
            color=color,
            weight=1,
            dash_array="5, 5",
            fill=False,
        ).add_to(fg_ports)
        if not np.isnan(r["suggested_lat"]):
            folium.CircleMarker(
                location=[r["suggested_lat"], r["suggested_lon"]], radius=4, color="blue", fill=True,
                tooltip=f"{r['port_code']} önerilen merkez (duruş medyanı)",
            ).add_to(fg_ports)
    fg_ports.add_to(m)

    # Katman 2: Liman Çevresi (500-2000m) Duruş Kümeleri (Grid ile özetlenmiş)
    fg_near = folium.FeatureGroup(name="Liman Dışı Yakın Duruşlar (500-2000m)", show=True)
    near_pts = slow_df[(slow_df["nearest_port_dist_m"] > 500.0) & (slow_df["nearest_port_dist_m"] <= 2000.0)].copy()
    near_pts["lat_bin"] = near_pts["latitude"].round(3)
    near_pts["lon_bin"] = near_pts["longitude"].round(3)
    near_grid = near_pts.groupby(["lat_bin", "lon_bin"]).size().reset_index(name="cnt")
    near_grid = near_grid[near_grid["cnt"] >= 5]
    for _, g in near_grid.iterrows():
        folium.CircleMarker(
            location=[g["lat_bin"], g["lon_bin"]],
            radius=3,
            color="#d9534f",
            fill=True,
            fill_opacity=0.6,
            tooltip=f"Duruş noktası: {g['cnt']}",
        ).add_to(fg_near)
    fg_near.add_to(m)

    # Katman 3: Demirleme Isı Haritası (Anchorage Heatmap)
    fg_heat = folium.FeatureGroup(name="Demirleme Isı Haritası (Anchorage Heatmap)", show=True)
    anchor_pts = slow_df[slow_df["nearest_port_dist_m"] > 500.0].copy()
    anchor_pts["lat_bin"] = anchor_pts["latitude"].round(3)
    anchor_pts["lon_bin"] = anchor_pts["longitude"].round(3)
    heat_grid = anchor_pts.groupby(["lat_bin", "lon_bin"]).size().reset_index(name="cnt")
    # Log-ölçekli ağırlık ile hem yoğun hem orta yoğun demirleme sahaları net görünür
    heat_data = [
        [float(r["lat_bin"]), float(r["lon_bin"]), float(np.log1p(r["cnt"]))]
        for _, r in heat_grid.iterrows()
    ]
    HeatMap(heat_data, radius=14, blur=18, max_zoom=13).add_to(fg_heat)
    fg_heat.add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)
    out_html = "liman_ve_demirleme_denetim_haritasi.html"
    m.save(out_html)
    print(f"-> '{out_html}' başarıyla oluşturuldu!")


if __name__ == "__main__":
    main()
