# Marmara Denizi AIS Yörünge Segmentasyonu — Ara Sunum ve Metodoloji Yol Haritası

> **Amaç:** Ham AIS verisinden başlayarak ETA (varış süresi) tahmin modellerine hazır, fiziksel ve kinematik olarak doğrulanmış sefer segmentleri üretme sürecimiz; karşılaştığımız hatalı varsayımlar, veriyle yaptığımız teşhisler ve uyguladığımız çözümler.

---

## 1. Veri Seti ve Ön İşleme (Bölüm 1–2)
1. **Ham Veri (`marmara_1week.csv`):** 1 haftalık Marmara Denizi ve Boğazlar AIS verisi (~14 milyon satır, ~2.1 GB).
2. **Kolon Seçimi (`01_extract_curated_columns.py`):** 7 dinamik hareket kolonu (`mmsi, timestamp, latitude, longitude, speed, course, heading`) ayıklandı.
3. **2D AEQD Projeksiyonu & Kinematik Temizlik (`02_physical_and_alpha_cleaning.py`):**
   - Küresel Haversine yerine Marmara merkezli ($40.75^\circ\text{ N}, 28.50^\circ\text{ E}$) **Azimuthal Equidistant (AEQD)** 2D Kartezyen düzlemine geçildi (distorsiyon $< \%0.02$, Öklid `hypot` ile yüksek hız).
   - Tekrarlı zaman damgaları, fiziksel hız/ivme aykırılıkları ve $\alpha$-yöntemi (`v_calc - v_reported` %95 güven aralığı $[-1.04, +1.35]\text{ kn}$) ile **10.648.309 temiz AIS noktası** elde edildi.
4. **Ampirik Kopukluk Eşiği ($\Delta t$):** 10.6M ardışık $\Delta t$ dağılımının %99'unun **12 dakika** içinde geldiği görülerek `max_time_gap_min = 12.0` belirlendi (keyfi 30 dk yerine).

---

## 2. Karşılaşılan Problemler, Yanlış Adımlar ve Çözümlerimiz

### Adım A: "Sabit 500 m Liman Dairesi" Sorunu
- **İlk Yaklaşım:** World Port Index + manuel listeden 41 liman noktası ve herkese sabit `500 m` yarıçap.
- **Ortaya Çıkan Sorun:** Sağlık raporu (`05_port_diagnostics_and_heatmap.py`) 41 limandan **26'sında kapsama sorunu** olduğunu gösterdi (gemiler rıhtımda 600–1500 m dışarıda duruyor görünüyordu; ör. BOTAŞ, Derince, Haydarpaşa, Ambarlı). Bazı noktalar da kara üstündeydi (`F008`, `F035`).
- **Çözüm:** Uydu haritası + duruş medyanları üzerinden tüm limanlar tek tek fine-tune edildi; yakın terminaller birleştirildi, Boğaz dışındakiler çıkarıldı, eksik önemli iskeleler/tersaneler (Saraylar, Altınova, Adalar, Bostancı, Eskihisar vb.) veri kümelerinden (`07_offport_stop_clusters.py`, `08_offport_clusters_map.py`) eklenerek **42 limanlı, limana özel yarıçaplı (`650 m – 4000 m`)** yapıya geçildi. Çakışan dairelerde büyük limanın küçüğü yutmaması için normalize mesafe (`dist_m / radius_m`) kullanıldı.

### Adım B: "Demirlemenin Segmenti Kesmesi" Sorunu
- **İlk Yaklaşım:** Liman dışında $\ge 30\text{ dk}$ duran her gemiyi `ANCHORAGE` sayıp segmenti kestik.
- **Ortaya Çıkan Sorun:** Gerçek bir `PORT_TO_PORT` sefer yolda Ahırkapı'da 2 saat demirleyince 3 parçaya (`PORT_TO_ANCHOR` + `ANCHOR_TO_ANCHOR` + `ANCHOR_TO_PORT`) bölündü. Sonuçta `PORT_TO_PORT` sadece **101** kalırken `ANCHOR_TO_ANCHOR` **5.425** oldu.
- **Çözüm:** Demirleme **segment kesici olmaktan çıkarılıp ara durak (attribute)** yapıldı. `ANCHOR_TO_ANCHOR` gibi kategoriler kaldırıldı; demirleme bilgisi segmentin içine **`anchorage_wait_min`**, **`anchorage_lat`**, **`anchorage_lon`** olarak işlendi.

### Adım C: "12 Dakika Kopukluk Nedeniyle %83 `PARTIAL` Parçalanma"
- **Ortaya Çıkan Sorun:** `max_time_gap_min = 12.0` yapıldığında gemiler seyir halindeyken 15–40 dakikalık tek bir AIS boşluğunda segmentler gereksiz yere bölündü (%83.2 `TRANSIT_OR_PARTIAL`).
- **Çözüm (Gap Bridging):** 12 dk eşiği korunarak `12–60 dk` arasındaki fiziksel olarak tutarlı boşluklar köprülendi ($v_{\text{ima}} \le 30\text{ kn}$ ve $|v_{\text{ima}} - \bar{v}_{\text{SOG}}| \le \max(3\text{ kn}, 0.5\bar{v}_{\text{SOG}})$ veya yerinde bekleme $d \le 500\text{ m}$). Kopuklukların ~%80'i köprülendi.

### Adım D: "Sanal Kapılar ve `< 10 dk` Hatalı Segmentler"
- **İlk Yaklaşım:** Transit geçişler için 3 sanal kapı (`GATE-CANAKKALE`, `GATE-ISTANBUL`, `GATE-IZMIT`) eklendi, ancak kapıya değen segmentlerde `< 10 dk` kuralı baypas edilmişti.
- **Ortaya Çıkan Sorun:** Boğaz kapısının hemen dibindeki Üsküdar/Harem iskelesi (`#75`) ile `GATE-ISTANBUL` arasında `1.7–2.6 dk`'lık **978 adet**, `GATE-ISTANBUL -> GATE-ISTANBUL` arasında **61 adet** `< 10 dk` yapay segment oluştu.
- **Çözüm:** `#75` çıkarıldı ve `min_voyage_duration_min = 10.0` kuralı sanal kapılar dahil **tüm segmentler için zorunlu** hale getirildi.

### Adım E: "Kaçırılan Demirleme (Swinging/Drifting) ve Rota Aykırılıkları"
- **Ortaya Çıkan Sorun:** Direkt seyir (`anchorage_wait_min == 0`) görünen bazı 3–12+ saatlik segmentlerde gemilerin `0.6–1.5 kn` hızla demirde salınarak/sürüklenerek beklediği tespit edildi (`stop_speed_knots = 0.5` eşiğini atlıyorlardı). Ayrıca `PORT_ROUNDTRIP`lerin ~%20'si sınır titremesi, bazı segmentler ise `detour_ratio > 2.5` (balıkçı/römorkör dolanması) veya hız uyumsuzluğu (`> 5 kn`) içeriyordu.
- **Literatür Çözümü:**
  1. **Hız + Mekansal Kalış:** `SOG <= 1.5 kn` iken liman dışında $\ge 30\text{ dk}$ boyunca `500 m` salınım yarıçapı içinde kalan bloklar da `ANCHOR_STOP` kabul edildi.
  2. **Kinematik Tutarlılık Filtresi:** `detour_ratio > 2.5` (`PORT_ROUNDTRIP` hariç) ve `|mean_speed_kn - effective_speed_kn| > 5.0 kn` segmentler elendi.

---

## 3. Nihai Mimari ve Tahmin (Regresyon) Stratejisi
- **Temizlenmiş Segment Kategorileri:** `PORT_TO_PORT`, `GATE_TO_GATE`, `PORT_TO_GATE`, `GATE_TO_PORT`, `PORT_ROUNDTRIP` (iç ayrımıyla: doğal tur vs sınır titremesi), `PORT_DEPARTURE/ARRIVAL`, `GATE_DEPARTURE/ARRIVAL`, `PARTIAL`.
- **İki Aşamalı ETA / Süre Tahmin Modeli:**
  Verimizde **direkt seyir (`anchorage_wait_min == 0`, medyan ~32 dk)** ile **demirlemeli seyir (`anchorage_wait_min > 0`, medyan ~369 dk)** arasında **11.5 kat fark** olduğu için:
  1. **Demirsiz (Direkt) Seyirler:** Net seyir süresi (`pure_sailing_min`) için ayrı regresyon modeli.
  2. **Demirli Seyirler:** Demirleme olasılığı (sınıflandırma) + demirleme konum (`anchorage_lat, lon`) ve bekleme süresi (`anchorage_wait_min`) için ayrı model.
