# 🚢 Marmara Denizi AIS Veri Hattı, Kinematik Kürasyon ve Yörünge Segmentasyonu

Bu depo, Marmara Denizi ve Türk Boğazları bölgesindeki 1 haftalık ham AIS (Otomatik Tanımlama Sistemi) verilerini işleyen, fiziksel & kinematik filtrelerden geçiren, 2D Kartezyen düzlemde modelleyen ve liman/sefer segmentasyonu yapan uçtan uca veri hattını (pipeline) içerir.

> 📖 **Grup Çalışması Kapsamlı Dokümanı:** Tüm matematiksel formüller, metodolojik açıklamalar ve sunum savunma notları için [PROJE_ORTAK_DOKUMAN.md](PROJE_ORTAK_DOKUMAN.md) dosyasını inceleyin.

---

## 🛠️ Hızlı Kurulum

Gerekli Python paketlerini yükleyin:
```bash
pip install pandas numpy pyproj matplotlib folium openpyxl
```

---

## 🚀 Çalıştırma Sırası (Pipeline)

Sırasıyla aşağıdaki 4 adımı terminalden çalıştırın:

```bash
# Adım 1: Ham AIS dosyasından 7 temel dinamik hareketi kolonunu ayıkla
python 01_extract_curated_columns.py

# Adım 2: 2D AEQD Kartezyen düzlem dönüşümü, kinematik kürasyon, attrition tablosu ve Delta t analizi
python 02_physical_and_alpha_cleaning.py

# Adım 3: 2D Öklid mesafesiyle 41 liman tabanlı sefer segmentasyonu
python 03_trajectory_segmentation.py

# Adım 4: 100 örnekli kategori filtreli etkileşimli harita galerisini oluştur
python 04_visualize_segments.py
```

---

## 📁 Betikler ve Dosya Yapısı

| Dosya | Açıklama |
| :--- | :--- |
| `01_extract_curated_columns.py` | Ham 2.1 GB CSV'den 7 dinamik kolonu (`mmsi`, `timestamp`, `lat`, `lon`, `speed`, `course`, `heading`) süzer. |
| `02_physical_and_alpha_cleaning.py` | WGS84 $\rightarrow$ 2D AEQD Kartezyen dönüşümü, $V_{\max}=50\text{ kn}$, yanal/çizgisel ivme, tekil GPS sıçraması, $\alpha$-Methodu ile temizlik yapar; `temizlik_attrition_tablosu.md` ve `delta_t_histogram.png` üretir. |
| `03_trajectory_segmentation.py` | 41 limanın 500m daireleri, $\ge 5$ dk duruş, $\ge 30$ dk demirleme ve ampirik $12\text{ dk}$ (%99 kantili) sinyal kopukluğuyla yörüngeleri segmentlere ayırır. |
| `04_visualize_segments.py` | 100 seçkin segment örneği (Port-to-Port, Port-to-Anchor, Transit vb.) için butonlu ve filtreli etkileşimli HTML haritası (`marmara_segment_galerisi.html`) üretir. |
| `PROJE_ORTAK_DOKUMAN.md` | Projenin grup arkadaşları için hazırlanmış kapsamlı, öğrenci dostu metodoloji ve formül dokümanı. |
| `Marmara_Final_Liman_Listesi.xlsx`| Marmara Denizi ve Boğazlar'daki 41 resmi liman ve iskele koordinatı. |
| `marmara_segment_galerisi.html` | Tarayıcıda açılabilen, harita katmanları çalışan, hız grafikli görsel galeri. |
| `temizlik_attrition_tablosu.md` | Her temizleme adımında kaç satır elendiğini gösteren bilimsel eleme tablosu. |
| `delta_t_histogram.png` | Ardışık sinyaller arası sürenin histogramı ve %98-%99 eşik grafiği. |
