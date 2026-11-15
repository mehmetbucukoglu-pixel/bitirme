# Proje Asistanı Yönergesi (AI Onboarding)

Bu depoda çalışmaya başlamadan önce **ilk olarak** [`PROJE_ORTAK_DOKUMAN.md`](PROJE_ORTAK_DOKUMAN.md) dosyasını (özellikle **9. Güncel Kararlar ve Metodoloji Değişiklikleri** bölümünü) ve sunum özeti için [`ARA_SUNUM_YOL_HARITASI.md`](ARA_SUNUM_YOL_HARITASI.md) dosyasını okuyun.

Özet kurallar:
- Orijinal `Marmara_Final_Liman_Listesi.xlsx` dosyasını değiştirmeyin; güncel 42 limanlı liste `Marmara_Liman_Listesi_v2.csv` (`06_build_port_list_v2.py` ile üretilir) üzerinden çalışır (limana özel `radius_m`, normalize mesafe `dist_m / radius_m`).
- Demirleme (`ANCHOR_STOP`) segmenti kesmez; `anchorage_wait_min`, `anchorage_lat`, `anchorage_lon` öznitelikleri olarak `marmara_segment_summary.csv` dosyasına yazılır. Demirleme tespiti hem `SOG <= 0.5 kn` ($\ge 30\text{ dk}$) hem de **mekansal kalış (`SOG <= 1.5 kn`, salınım $\le 500\text{ m}$, $\ge 30\text{ dk}$)** kuralını kullanır.
- Segmentasyon eşikleri (`max_time_gap_min=12.0`, `max_bridge_gap_min=60.0`, `min_voyage_duration_min=10.0`), sanal kapılar (`VIRTUAL_GATE`) ve kinematik tutarlılık filtreleri (`detour_ratio <= 2.5` non-roundtrip, `speed_diff_kn <= 5.0`) `03_trajectory_segmentation.py` içindedir.
- Tahmin/regresyon aşamasında demirli (`anchorage_wait_min > 0`) ve demirsiz (`anchorage_wait_min == 0`) segmentler **ayrı modellere** ayrılır.
