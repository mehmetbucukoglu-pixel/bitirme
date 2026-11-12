import os
import sys
import json
import argparse
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import folium

from importlib.machinery import SourceFileLoader


def load_ports(excel_path="Marmara_Final_Liman_Listesi.xlsx"):
    seg_mod = SourceFileLoader("seg_mod", "03_trajectory_segmentation.py").load_module()
    return seg_mod.load_marmara_ports(excel_path)


def add_working_tile_layers(fmap):
    """
    OpenStreetMap'in yerel dosya (file://) açılışlarında verdiği '403 Access Blocked'
    hatasını önlemek için doğrudan çalışan Esri ve CartoDB harita katmanlarını ekler.
    """
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}",
        attr="Esri World Street Map",
        name="Esri Sokak / Deniz Haritası",
        overlay=False,
        control=True,
    ).add_to(fmap)

    folium.TileLayer(
        tiles="https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",
        attr="CartoDB Voyager",
        name="CartoDB Renkli Harita",
        subdomains="abcd",
        overlay=False,
        control=True,
    ).add_to(fmap)

    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri World Imagery",
        name="Esri Uydu Görüntüsü (Satellite)",
        overlay=False,
        control=True,
    ).add_to(fmap)

    folium.LayerControl(position="topright").add_to(fmap)


def select_diverse_segments(df_cat, target_count, min_speed=2.5):
    """
    Belirli bir kategoriden farklı gemilere (MMSI) öncelik vererek en temsili
    ve net rotaya sahip 'target_count' adet segment seçer.
    """
    good = df_cat[
        (df_cat["mean_speed_kn"] >= min_speed)
        & (df_cat["point_count"] >= 20)
        & (df_cat["duration_min"] >= 15.0)
    ].sort_values(["point_count", "duration_min"], ascending=[False, False])

    if len(good) < target_count:
        good = df_cat.sort_values(["point_count", "duration_min"], ascending=[False, False])

    # Önce her MMSI'dan en iyi 1-2 taneyi al ki hep aynı gemi tekrar etmesin
    diverse_first = good.groupby("mmsi", as_index=False).head(2)
    if len(diverse_first) >= target_count:
        return diverse_first.head(target_count)

    remaining = good.loc[~good.index.isin(diverse_first.index)]
    combined = pd.concat([diverse_first, remaining], ignore_index=True)
    return combined.head(target_count)


def build_interactive_gallery_html(
    segments_csv="marmara_segmented_trajectories.csv",
    summary_csv="marmara_segment_summary.csv",
    ports_excel="Marmara_Final_Liman_Listesi.xlsx",
    output_html="marmara_segment_galerisi.html",
    port_radius_m=500.0,
):
    """
    Kategori filtreli (Port-to-Port: 30 örnek, Port-to-Anchorage: 20 örnek,
    Anchor-to-Port: 15 örnek, Transit: 20 örnek) etkileşimli HTML galerisi üretir.
    """
    print("-> Kategori Filtreli Çoklu Segment Galerisi ('marmara_segment_galerisi.html') hazırlanıyor...")
    summary_df = pd.read_csv(summary_csv)
    ports_df = load_ports(ports_excel)

    # 1. PORT_TO_PORT: 30 örnek
    p2p_df = select_diverse_segments(
        summary_df[summary_df["segment_category"] == "PORT_TO_PORT"], target_count=30, min_speed=1.5
    )

    # 2. PORT_TO_ANCHOR (Limandan Demirlemeye): 20 örnek
    p2a_df = select_diverse_segments(
        summary_df[summary_df["segment_category"] == "PORT_TO_ANCHOR"], target_count=20, min_speed=3.0
    )

    # 3. ANCHOR_TO_PORT (Demirlemeden Limana): 15 örnek
    a2p_df = select_diverse_segments(
        summary_df[summary_df["segment_category"] == "ANCHOR_TO_PORT"], target_count=15, min_speed=3.0
    )

    # 4. TRANSIT_OR_PARTIAL (Transit Seferler): 20 örnek
    tr_df = select_diverse_segments(
        summary_df[summary_df["segment_category"] == "TRANSIT_OR_PARTIAL"], target_count=20, min_speed=6.0
    )

    # 5. PORT_DEPARTURE / PORT_ARRIVAL: 15 örnek
    dep_arr_df = select_diverse_segments(
        summary_df[summary_df["segment_category"].isin(["PORT_DEPARTURE", "PORT_ARRIVAL"])],
        target_count=15,
        min_speed=4.0,
    )

    selected_df = pd.concat([p2p_df, p2a_df, a2p_df, tr_df, dep_arr_df], ignore_index=True)
    selected_df = selected_df.drop_duplicates(subset=["global_segment_id"]).reset_index(drop=True)

    print(f"   • PORT_TO_PORT seçilen        : {len(p2p_df)} örnek")
    print(f"   • PORT_TO_ANCHOR seçilen      : {len(p2a_df)} örnek")
    print(f"   • ANCHOR_TO_PORT seçilen      : {len(a2p_df)} örnek")
    print(f"   • TRANSIT_OR_PARTIAL seçilen  : {len(tr_df)} örnek")
    print(f"   • PORT_DEPARTURE/ARRIVAL      : {len(dep_arr_df)} örnek")
    print(f"   • TOPLAM GALERİ SEGMENT SAYISI: {len(selected_df)} örnek")

    target_mmsis = set(selected_df["mmsi"].astype(int).unique())

    # Bu gemilerin tüm segment noktalarını tek geçişte oku
    chunks = []
    for chunk in pd.read_csv(segments_csv, chunksize=500_000, low_memory=False):
        sub = chunk[chunk["mmsi"].isin(target_mmsis)]
        if not sub.empty:
            chunks.append(sub)
    pts_df = pd.concat(chunks, ignore_index=True)
    pts_df["timestamp"] = pd.to_datetime(pts_df["timestamp"], utc=True)
    pts_df = pts_df.sort_values(["mmsi", "timestamp"]).reset_index(drop=True)

    # Hızlı erişim için (mmsi, mmsi_seg_no) bazında grupla
    grouped_pts = {k: v for k, v in pts_df.groupby(["mmsi", "mmsi_seg_no"], sort=False)}
    vessel_all_segs = {m: v for m, v in pts_df.groupby("mmsi", sort=False)}

    # Liman verisini JSON'a hazırla
    ports_json = []
    for _, p in ports_df.iterrows():
        ports_json.append({
            "code": str(p["port_code"]),
            "name": str(p["port_name"]),
            "lat": round(float(p["lat"]), 6),
            "lon": round(float(p["lon"]), 6),
            "scope": str(p["scope"]),
        })

    # Seçilen her segment için JSON verisi hazırla
    segments_json = []
    for _, r in selected_df.iterrows():
        m = int(r["mmsi"])
        s_no = int(r["mmsi_seg_no"])
        s_pts = grouped_pts.get((m, s_no))
        if s_pts is None or s_pts.empty:
            continue

        # Tarayıcı akıcılığı için maks 220 nokta örnekle (ilk ve son nokta dahil)
        if len(s_pts) > 220:
            keep_idx = np.unique(np.linspace(0, len(s_pts) - 1, 220).astype(int))
            s_pts = s_pts.iloc[keep_idx]

        # Aynı geminin diğer segmentlerinin özet izleri (arka planda kesikli çizgi için, en fazla 8 komşu segment)
        other_segs = []
        v_df = vessel_all_segs.get(m)
        if v_df is not None:
            for o_no, o_grp in v_df.groupby("mmsi_seg_no"):
                if int(o_no) == s_no:
                    continue
                if abs(int(o_no) - s_no) > 5 and len(other_segs) >= 6:
                    continue
                step = max(1, len(o_grp) // 60)
                o_sub = o_grp.iloc[::step]
                other_segs.append({
                    "seg_no": int(o_no),
                    "cat": str(o_grp["segment_category"].iloc[0]),
                    "coords": [[round(float(lat), 5), round(float(lon), 5)] for lat, lon in zip(o_sub["latitude"], o_sub["longitude"])]
                })

        points_list = []
        for _, pt in s_pts.iterrows():
            points_list.append({
                "lat": round(float(pt["latitude"]), 5),
                "lon": round(float(pt["longitude"]), 5),
                "spd": round(float(pt["speed"]), 1),
                "t": pt["timestamp"].strftime("%Y-%m-%d %H:%M:%S"),
                "hm": pt["timestamp"].strftime("%H:%M"),
                "dist_m": round(float(pt["nearest_port_dist_m"]), 0),
                "near_port": str(pt["nearest_port_code"]),
            })

        orig_name = str(r["origin_port_name"]) if pd.notna(r["origin_port_name"]) and str(r["origin_port_name"]).strip() else str(r["origin_type"])
        dest_name = str(r["dest_port_name"]) if pd.notna(r["dest_port_name"]) and str(r["dest_port_name"]).strip() else str(r["dest_type"])
        orig_code = str(r["origin_port_code"]) if pd.notna(r["origin_port_code"]) else ""
        dest_code = str(r["dest_port_code"]) if pd.notna(r["dest_port_code"]) else ""

        segments_json.append({
            "idx": len(segments_json) + 1,
            "global_id": int(r["global_segment_id"]),
            "mmsi": m,
            "seg_no": s_no,
            "category": str(r["segment_category"]),
            "orig_type": str(r["origin_type"]),
            "orig_code": orig_code,
            "orig_name": orig_name,
            "dest_type": str(r["dest_type"]),
            "dest_code": dest_code,
            "dest_name": dest_name,
            "start_time": str(r["start_time_utc"]),
            "end_time": str(r["end_time_utc"]),
            "duration_min": float(r["duration_min"]),
            "point_count": int(r["point_count"]),
            "mean_speed": float(r["mean_speed_kn"]),
            "max_speed": float(r["max_speed_kn"]),
            "points": points_list,
            "other_segments": other_segs,
        })

    html_content = f"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Marmara AIS Yörünge Segmentasyon Galerisi</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; }}
  body {{ display: flex; height: 100vh; width: 100vw; overflow: hidden; background: #0f172a; color: #f8fafc; }}
  #sidebar {{ width: 430px; min-width: 430px; height: 100vh; background: #1e293b; border-right: 1px solid #334155; display: flex; flex-direction: column; z-index: 1000; box-shadow: 4px 0 15px rgba(0,0,0,0.4); }}
  .header {{ padding: 14px 18px; background: #0f172a; border-bottom: 1px solid #334155; }}
  .header h1 {{ font-size: 16px; font-weight: 700; color: #38bdf8; margin-bottom: 4px; }}
  .header p {{ font-size: 11.5px; color: #94a3b8; }}
  .nav-controls {{ padding: 12px 18px; background: #1e293b; border-bottom: 1px solid #334155; }}
  .filter-label {{ font-size: 11px; font-weight: 700; color: #94a3b8; text-transform: uppercase; margin-bottom: 6px; letter-spacing: 0.5px; display: flex; justify-content: space-between; }}
  .filter-pills {{ display: flex; flex-wrap: wrap; gap: 5px; margin-bottom: 11px; }}
  .pill {{ padding: 5px 9px; border-radius: 5px; font-size: 11.5px; font-weight: 600; background: #0f172a; color: #cbd5e1; border: 1px solid #334155; cursor: pointer; transition: 0.15s; }}
  .pill:hover {{ border-color: #38bdf8; color: #fff; }}
  .pill.active {{ background: #0284c7; color: #fff; border-color: #38bdf8; }}
  .btn-row {{ display: flex; gap: 10px; margin-bottom: 9px; }}
  .nav-btn {{ flex: 1; padding: 9px 12px; background: #2563eb; color: white; border: none; border-radius: 6px; font-weight: 600; font-size: 13px; cursor: pointer; transition: 0.15s; }}
  .nav-btn:hover {{ background: #1d4ed8; }}
  .nav-btn.secondary {{ background: #334155; }}
  .nav-btn.secondary:hover {{ background: #475569; }}
  select#segSelect {{ width: 100%; padding: 8px 10px; background: #0f172a; color: #f8fafc; border: 1px solid #475569; border-radius: 6px; font-size: 12px; cursor: pointer; }}
  .toggle-row {{ display: flex; align-items: center; gap: 8px; margin-top: 9px; font-size: 12px; color: #cbd5e1; cursor: pointer; }}
  .details {{ padding: 12px 18px; overflow-y: auto; flex: 1; }}
  .top-status {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }}
  .badge {{ display: inline-block; padding: 4px 9px; border-radius: 4px; font-size: 11px; font-weight: 700; letter-spacing: 0.4px; }}
  .badge.PORT_TO_PORT {{ background: #16a34a; color: white; }}
  .badge.PORT_ARRIVAL, .badge.PORT_DEPARTURE {{ background: #0284c7; color: white; }}
  .badge.ANCHOR_TO_PORT, .badge.PORT_TO_ANCHOR {{ background: #d97706; color: white; }}
  .badge.TRANSIT_OR_PARTIAL {{ background: #64748b; color: white; }}
  .counter-text {{ font-size: 12px; font-weight: 600; color: #38bdf8; }}
  .card {{ background: #0f172a; border: 1px solid #334155; border-radius: 8px; padding: 11px 14px; margin-bottom: 10px; }}
  .card-row {{ display: flex; justify-content: space-between; font-size: 12px; padding: 4.5px 0; border-bottom: 1px solid #1e293b; }}
  .card-row:last-child {{ border-bottom: none; }}
  .card-label {{ color: #94a3b8; }}
  .card-val {{ font-weight: 600; color: #f1f5f9; text-align: right; max-width: 230px; }}
  .route-box {{ display: flex; flex-direction: column; gap: 6px; }}
  .route-step {{ display: flex; align-items: center; gap: 8px; font-size: 12px; padding: 6px 8px; border-radius: 5px; background: #1e293b; }}
  .dot-green {{ width: 10px; height: 10px; border-radius: 50%; background: #22c55e; flex-shrink: 0; }}
  .dot-red {{ width: 10px; height: 10px; border-radius: 50%; background: #ef4444; flex-shrink: 0; }}
  canvas#spdChart {{ width: 100%; height: 125px; background: #0f172a; border: 1px solid #334155; border-radius: 8px; margin-top: 5px; }}
  .legend-box {{ font-size: 11px; color: #94a3b8; line-height: 1.55; }}
  #map {{ flex: 1; height: 100vh; }}
</style>
</head>
<body>
<div id="sidebar">
  <div class="header">
    <h1>Marmara AIS Segmentasyon Galerisi (100 Örnek)</h1>
    <p>Liman R=500m | Liman Duruş ≥ 5dk | Demirleme ≥ 30dk | Kopukluk > 30dk</p>
  </div>
  <div class="nav-controls">
    <div class="filter-label">
      <span>KATEGORİ FİLTRESİ</span>
      <span id="filterSummaryText">100 Segment</span>
    </div>
    <div class="filter-pills">
      <button class="pill active" onclick="setCategoryFilter('ALL', this)">Tümü (100)</button>
      <button class="pill" onclick="setCategoryFilter('PORT_TO_PORT', this)">Port-to-Port (30)</button>
      <button class="pill" onclick="setCategoryFilter('PORT_TO_ANCHOR', this)">Port-to-Anchor (20)</button>
      <button class="pill" onclick="setCategoryFilter('ANCHOR_TO_PORT', this)">Anchor-to-Port (15)</button>
      <button class="pill" onclick="setCategoryFilter('TRANSIT_OR_PARTIAL', this)">Transit (20)</button>
      <button class="pill" onclick="setCategoryFilter('PORT_DEP_ARR', this)">Port Giriş/Çıkış (15)</button>
    </div>
    <div class="btn-row">
      <button class="nav-btn secondary" onclick="prevSegment()">◀ Önceki Örnek</button>
      <button class="nav-btn" onclick="nextSegment()">Sonraki Örnek ▶</button>
    </div>
    <select id="segSelect" onchange="selectSegment(this.value)"></select>
    <label class="toggle-row">
      <input type="checkbox" id="showAllSegs" checked onchange="renderCurrentSegment()">
      Aynı geminin komşu segmentlerini kesikli çizgiyle göster
    </label>
  </div>
  <div class="details">
    <div class="top-status">
      <div id="catBadge" class="badge">PORT_TO_PORT</div>
      <div id="counterText" class="counter-text">Örnek 1 / 30</div>
    </div>
    <div class="card">
      <div class="route-box">
        <div class="route-step"><span class="dot-green"></span><div><div style="font-size:10px;color:#94a3b8;">KALKIŞ (ORIGIN)</div><strong id="origText">-</strong></div></div>
        <div class="route-step"><span class="dot-red"></span><div><div style="font-size:10px;color:#94a3b8;">VARIŞ (DESTINATION)</div><strong id="destText">-</strong></div></div>
      </div>
    </div>
    <div class="card">
      <div class="card-row"><span class="card-label">Gemi MMSI</span><span class="card-val" id="mmsiText">-</span></div>
      <div class="card-row"><span class="card-label">Gemi Segment No</span><span class="card-val" id="segNoText">-</span></div>
      <div class="card-row"><span class="card-label">Başlangıç (UTC)</span><span class="card-val" id="startText">-</span></div>
      <div class="card-row"><span class="card-label">Bitiş (UTC)</span><span class="card-val" id="endText">-</span></div>
      <div class="card-row"><span class="card-label">Seyir Süresi</span><span class="card-val" id="durText">-</span></div>
      <div class="card-row"><span class="card-label">AIS Nokta Sayısı</span><span class="card-val" id="ptsText">-</span></div>
      <div class="card-row"><span class="card-label">Ort. / Maks. Hız</span><span class="card-val" id="spdText">-</span></div>
    </div>
    <div style="font-size:11.5px;font-weight:600;color:#cbd5e1;">Hız (SOG) Değişim Grafiği (knot)</div>
    <canvas id="spdChart" width="380" height="125"></canvas>
    <div class="card legend-box" style="margin-top:10px;">
      <div>🟢 <b>Yeşil Daire (500m):</b> Kalkış Limanı</div>
      <div>🔴 <b>Kırmızı Daire (500m):</b> Varış Limanı</div>
      <div>🔵 <b>Mavi Daireler (500m):</b> Diğer 41 Marmara Limanı</div>
      <div>➖ <b>Kesikli Çizgiler:</b> Geminin Önceki/Sonraki Segmentleri</div>
    </div>
  </div>
</div>
<div id="map"></div>

<script>
const PORTS = {json.dumps(ports_json, ensure_ascii=False)};
const ALL_SEGMENTS = {json.dumps(segments_json, ensure_ascii=False)};
const PORT_RADIUS_M = {port_radius_m};

const esriStreet = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
  attribution: 'Tiles &copy; Esri'
}});
const cartoVoyager = L.tileLayer('https://{{s}}.basemaps.cartocdn.com/rastertiles/voyager/{{z}}/{{x}}/{{y}}{{r}}.png', {{
  attribution: '&copy; CartoDB', subdomains: 'abcd'
}});
const esriSat = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
  attribution: 'Tiles &copy; Esri Satellite'
}});

const map = L.map('map', {{
  center: [40.72, 28.80],
  zoom: 9,
  layers: [esriStreet]
}});

L.control.layers({{
  "Esri Deniz & Sokak Haritası": esriStreet,
  "CartoDB Renkli Harita": cartoVoyager,
  "Esri Uydu Görüntüsü": esriSat
}}, null, {{ position: 'topright' }}).addTo(map);

const portLayerGroup = L.layerGroup().addTo(map);
const routeLayerGroup = L.layerGroup().addTo(map);

let currentFilter = 'ALL';
let filteredSegments = ALL_SEGMENTS.slice();
let currentIndex = 0;

const selectEl = document.getElementById('segSelect');

function setCategoryFilter(cat, btnEl) {{
  currentFilter = cat;
  document.querySelectorAll('.pill').forEach(b => b.classList.remove('active'));
  if (btnEl) btnEl.classList.add('active');

  if (cat === 'ALL') {{
    filteredSegments = ALL_SEGMENTS.slice();
  }} else if (cat === 'PORT_DEP_ARR') {{
    filteredSegments = ALL_SEGMENTS.filter(s => s.category === 'PORT_DEPARTURE' || s.category === 'PORT_ARRIVAL');
  }} else {{
    filteredSegments = ALL_SEGMENTS.filter(s => s.category === cat);
  }}

  document.getElementById('filterSummaryText').textContent = `${{filteredSegments.length}} Segment`;
  populateDropdown();
  currentIndex = 0;
  renderCurrentSegment();
}}

function populateDropdown() {{
  selectEl.innerHTML = '';
  filteredSegments.forEach((seg, idx) => {{
    const opt = document.createElement('option');
    opt.value = idx;
    opt.textContent = `[${{idx+1}}/${{filteredSegments.length}}] MMSI ${{seg.mmsi}} (Seg ${{seg.seg_no}}) - ${{seg.orig_name}} ➔ ${{seg.dest_name}} (${{seg.duration_min.toFixed(0)}} dk)`;
    selectEl.appendChild(opt);
  }});
}}

function speedColor(spd) {{
  if (spd < 2) return '#38bdf8';
  if (spd < 7) return '#22c55e';
  if (spd < 12) return '#eab308';
  return '#f97316';
}}

function drawSpeedChart(points) {{
  const canvas = document.getElementById('spdChart');
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (!points || points.length < 2) return;

  const padL = 32, padR = 12, padT = 14, padB = 22;
  const w = canvas.width - padL - padR;
  const h = canvas.height - padT - padB;
  const maxSpd = Math.max(15, ...points.map(p => p.spd));

  ctx.strokeStyle = '#334155';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(padL, padT);
  ctx.lineTo(padL, padT + h);
  ctx.lineTo(padL + w, padT + h);
  ctx.stroke();

  ctx.fillStyle = '#94a3b8';
  ctx.font = '10px sans-serif';
  ctx.fillText(maxSpd.toFixed(0) + ' kn', 2, padT + 8);
  ctx.fillText('0 kn', 6, padT + h);
  ctx.fillText(points[0].hm, padL, canvas.height - 5);
  ctx.fillText(points[points.length - 1].hm, padL + w - 28, canvas.height - 5);

  ctx.strokeStyle = '#38bdf8';
  ctx.lineWidth = 2;
  ctx.beginPath();
  points.forEach((p, i) => {{
    const x = padL + (i / (points.length - 1)) * w;
    const y = padT + h - (p.spd / maxSpd) * h;
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }});
  ctx.stroke();
}}

function renderCurrentSegment() {{
  if (!filteredSegments.length) return;
  const seg = filteredSegments[currentIndex];
  selectEl.value = currentIndex;

  const badge = document.getElementById('catBadge');
  badge.textContent = seg.category;
  badge.className = 'badge ' + seg.category;

  document.getElementById('counterText').textContent = `Örnek ${{currentIndex + 1}} / ${{filteredSegments.length}}`;
  document.getElementById('origText').textContent = seg.orig_name + (seg.orig_code ? ` (${{seg.orig_code}})` : '');
  document.getElementById('destText').textContent = seg.dest_name + (seg.dest_code ? ` (${{seg.dest_code}})` : '');
  document.getElementById('mmsiText').textContent = seg.mmsi;
  document.getElementById('segNoText').textContent = `Segment ${{seg.seg_no}} (Global ID: ${{seg.global_id}})`;
  document.getElementById('startText').textContent = seg.start_time.replace('+00:00', ' UTC');
  document.getElementById('endText').textContent = seg.end_time.replace('+00:00', ' UTC');
  document.getElementById('durText').textContent = `${{seg.duration_min.toFixed(1)}} dk (${{(seg.duration_min/60).toFixed(1)}} saat)`;
  document.getElementById('ptsText').textContent = seg.point_count;
  document.getElementById('spdText').textContent = `${{seg.mean_speed}} kn / ${{seg.max_speed}} kn`;

  drawSpeedChart(seg.points);

  portLayerGroup.clearLayers();
  routeLayerGroup.clearLayers();

  PORTS.forEach(p => {{
    const isOrig = (p.code === seg.orig_code && seg.orig_code !== '');
    const isDest = (p.code === seg.dest_code && seg.dest_code !== '');
    let color = '#3b82f6';
    let fillOp = 0.15;
    let weight = 1.5;
    let prefix = 'Liman: ';

    if (isOrig) {{
      color = '#16a34a'; fillOp = 0.45; weight = 3; prefix = 'KALKIŞ LİMANI: ';
    }} else if (isDest) {{
      color = '#dc2626'; fillOp = 0.45; weight = 3; prefix = 'VARIŞ LİMANI: ';
    }}

    L.circle([p.lat, p.lon], {{
      radius: PORT_RADIUS_M,
      color: color,
      weight: weight,
      fillColor: color,
      fillOpacity: fillOp
    }}).bindTooltip(`<b>${{prefix}}${{p.name}}</b> (${{p.code}})<br>Yarıçap: ${{PORT_RADIUS_M}} m`).addTo(portLayerGroup);
  }});

  const showOthers = document.getElementById('showAllSegs').checked;
  if (showOthers && seg.other_segments) {{
    const colors = ['#94a3b8', '#a855f7', '#ec4899', '#14b8a6'];
    seg.other_segments.forEach((os, idx) => {{
      if (os.coords.length >= 2) {{
        L.polyline(os.coords, {{
          color: colors[idx % colors.length],
          weight: 2.5,
          opacity: 0.65,
          dashArray: '6, 6'
        }}).bindTooltip(`MMSI ${{seg.mmsi}} - Diğer Segment ${{os.seg_no}} (${{os.cat}})`).addTo(routeLayerGroup);
      }}
    }});
  }}

  const coords = seg.points.map(pt => [pt.lat, pt.lon]);
  const mainLine = L.polyline(coords, {{
    color: '#1d4ed8',
    weight: 4.5,
    opacity: 0.9
  }}).bindTooltip(`MMSI ${{seg.mmsi}} - Segment ${{seg.seg_no}}`).addTo(routeLayerGroup);

  seg.points.forEach((pt, idx) => {{
    if (idx % 2 === 0 || idx === 0 || idx === seg.points.length - 1) {{
      L.circleMarker([pt.lat, pt.lon], {{
        radius: 4,
        color: '#0f172a',
        weight: 1,
        fillColor: speedColor(pt.spd),
        fillOpacity: 0.95
      }}).bindTooltip(
        `<b>MMSI ${{seg.mmsi}} | Seg ${{seg.seg_no}}</b><br>Zaman: ${{pt.t}}<br>Hız: ${{pt.spd}} knot<br>En Yakın Liman: ${{pt.near_port}} (${{pt.dist_m}} m)`
      ).addTo(routeLayerGroup);
    }}
  }});

  const pStart = seg.points[0];
  const pEnd = seg.points[seg.points.length - 1];

  L.circleMarker([pStart.lat, pStart.lon], {{
    radius: 9, color: '#ffffff', weight: 2.5, fillColor: '#16a34a', fillOpacity: 1.0
  }}).bindPopup(`<b>KALKIŞ (BAŞLANGIÇ)</b><br>MMSI: ${{seg.mmsi}} - Seg ${{seg.seg_no}}<br>Konum: ${{seg.orig_name}}<br>Zaman: ${{pStart.t}}<br>Hız: ${{pStart.spd}} kn`).addTo(routeLayerGroup);

  L.circleMarker([pEnd.lat, pEnd.lon], {{
    radius: 9, color: '#ffffff', weight: 2.5, fillColor: '#dc2626', fillOpacity: 1.0
  }}).bindPopup(`<b>VARIŞ (BİTİŞ)</b><br>MMSI: ${{seg.mmsi}} - Seg ${{seg.seg_no}}<br>Konum: ${{seg.dest_name}}<br>Zaman: ${{pEnd.t}}<br>Hız: ${{pEnd.spd}} kn`).addTo(routeLayerGroup);

  map.fitBounds(mainLine.getBounds(), {{ padding: [45, 45] }});
}}

function prevSegment() {{
  if (!filteredSegments.length) return;
  currentIndex = (currentIndex - 1 + filteredSegments.length) % filteredSegments.length;
  renderCurrentSegment();
}}

function nextSegment() {{
  if (!filteredSegments.length) return;
  currentIndex = (currentIndex + 1) % filteredSegments.length;
  renderCurrentSegment();
}}

function selectSegment(val) {{
  currentIndex = parseInt(val, 10);
  renderCurrentSegment();
}}

document.addEventListener('keydown', (e) => {{
  if (e.key === 'ArrowRight') nextSegment();
  if (e.key === 'ArrowLeft') prevSegment();
}});

populateDropdown();
renderCurrentSegment();
</script>
</body>
</html>
"""
    with open(output_html, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"-> TAMAMLANDI! 100 Örnekli Etkileşimli Segment Galerisi kaydedildi: {output_html}\n")


def visualize_vessel_segment(
    mmsi=None,
    mmsi_seg_no=1,
    global_segment_id=None,
    segments_csv="marmara_segmented_trajectories.csv",
    summary_csv="marmara_segment_summary.csv",
    ports_excel="Marmara_Final_Liman_Listesi.xlsx",
    port_radius_m=500.0,
):
    if not os.path.exists(summary_csv) or not os.path.exists(segments_csv):
        print("HATA: Önce 'python 03_trajectory_segmentation.py' çalıştırılmalıdır.")
        return

    summary_df = pd.read_csv(summary_csv)
    ports_df = load_ports(ports_excel)

    if global_segment_id is not None:
        sel = summary_df[summary_df["global_segment_id"] == global_segment_id]
        if sel.empty:
            print(f"HATA: global_segment_id={global_segment_id} bulunamadı.")
            return
        target_row = sel.iloc[0]
        mmsi = int(target_row["mmsi"])
        mmsi_seg_no = int(target_row["mmsi_seg_no"])
    elif mmsi is not None:
        sel = summary_df[(summary_df["mmsi"] == int(mmsi)) & (summary_df["mmsi_seg_no"] == int(mmsi_seg_no))]
        if sel.empty:
            vessel_segs = summary_df[summary_df["mmsi"] == int(mmsi)]
            if vessel_segs.empty:
                print(f"HATA: MMSI={mmsi} için geçerli segment bulunamadı.")
                return
            target_row = vessel_segs.iloc[0]
            mmsi_seg_no = int(target_row["mmsi_seg_no"])
        else:
            target_row = sel.iloc[0]
    else:
        p2p = summary_df[
            (summary_df["segment_category"] == "PORT_TO_PORT")
            & (summary_df["mmsi_seg_no"] == 1)
        ].sort_values("point_count", ascending=False)
        if p2p.empty:
            p2p = summary_df
        target_row = p2p.iloc[0]
        mmsi = int(target_row["mmsi"])
        mmsi_seg_no = int(target_row["mmsi_seg_no"])

    vessel_chunks = []
    for chunk in pd.read_csv(segments_csv, chunksize=500_000, low_memory=False):
        sub = chunk[chunk["mmsi"] == mmsi]
        if not sub.empty:
            vessel_chunks.append(sub)

    vessel_df = pd.concat(vessel_chunks, ignore_index=True)
    vessel_df["timestamp"] = pd.to_datetime(vessel_df["timestamp"], utc=True)
    vessel_df = vessel_df.sort_values("timestamp").reset_index(drop=True)

    seg_points = vessel_df[vessel_df["mmsi_seg_no"] == mmsi_seg_no].copy().reset_index(drop=True)
    if seg_points.empty:
        return

    center_lat = float(seg_points["latitude"].mean())
    center_lon = float(seg_points["longitude"].mean())
    fmap = folium.Map(location=[center_lat, center_lon], zoom_start=10, tiles=None)
    add_working_tile_layers(fmap)

    orig_code = str(target_row.get("origin_port_code", ""))
    dest_code = str(target_row.get("dest_port_code", ""))

    for _, p in ports_df.iterrows():
        p_code = str(p["port_code"])
        p_name = str(p["port_name"])
        is_orig = (p_code == orig_code)
        is_dest = (p_code == dest_code)

        if is_orig:
            circle_color = "#16a34a"
            fill_op = 0.40
            label_prefix = "KALKIŞ LİMANI: "
        elif is_dest:
            circle_color = "#dc2626"
            fill_op = 0.40
            label_prefix = "VARIŞ LİMANI: "
        else:
            circle_color = "#3b82f6"
            fill_op = 0.15
            label_prefix = "Liman: "

        folium.Circle(
            location=[float(p["lat"]), float(p["lon"])],
            radius=port_radius_m,
            color=circle_color,
            weight=2,
            fill=True,
            fill_color=circle_color,
            fill_opacity=fill_op,
            tooltip=f"{label_prefix}{p_name} ({p_code} - R={port_radius_m:.0f}m)",
        ).add_to(fmap)

    target_coords = list(zip(seg_points["latitude"].astype(float), seg_points["longitude"].astype(float)))
    folium.PolyLine(
        target_coords,
        color="#2563eb",
        weight=4.5,
        opacity=0.9,
        tooltip=f"MMSI {mmsi} - SEGMENT {mmsi_seg_no} ({target_row['segment_category']})",
    ).add_to(fmap)

    p_start = seg_points.iloc[0]
    p_end = seg_points.iloc[-1]
    folium.Marker(
        location=[float(p_start["latitude"]), float(p_start["longitude"])],
        tooltip=f"BAŞLANGIÇ (MMSI {mmsi} - Segment {mmsi_seg_no})",
        icon=folium.Icon(color="green", icon="play"),
    ).add_to(fmap)

    folium.Marker(
        location=[float(p_end["latitude"]), float(p_end["longitude"])],
        tooltip=f"BİTİŞ (MMSI {mmsi} - Segment {mmsi_seg_no})",
        icon=folium.Icon(color="red", icon="stop"),
    ).add_to(fmap)

    html_out = f"segment_harita_{mmsi}_S{mmsi_seg_no}.html"
    fmap.save(html_out)
    print(f"-> Tekil Harita güncellendi (403 hatasız): {html_out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AIS Segment Görselleştirme ve Galeri Betiği")
    parser.add_argument("--mmsi", type=int, default=None, help="Görselleştirilecek gemi MMSI numarası")
    parser.add_argument("--seg", type=int, default=1, help="Geminin kaçıncı segmenti (varsayılan: 1)")
    parser.add_argument("--segment-id", type=int, default=None, help="Doğrudan global_segment_id ile seçim")
    args = parser.parse_args()

    build_interactive_gallery_html()
    if args.mmsi is not None or args.segment_id is not None:
        visualize_vessel_segment(mmsi=args.mmsi, mmsi_seg_no=args.seg, global_segment_id=args.segment_id)
