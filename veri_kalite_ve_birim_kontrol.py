import os
import sys
import numpy as np
import pandas as pd

def analyze_dataset_quality_and_units(csv_path="marmara_columns_extracted.csv", chunksize=500000):
    """
    AIS Veri Seti Doluluk ve Birim Doğrulama Analizi:
    1. 01_extract_curated_columns.py çıktısı olan 7 temel kolon (mmsi, timestamp, latitude, longitude, speed, course, heading)
       üzerinde doluluk ve eksik veri istatistiklerini hesaplar.
    2. Denizcilik/AIS standartlarına göre min, max, ortalama değer aralıklarını çıkarıp birim teyidi sunar.
    """
    print("==================================================")
    print("  AIS VERİ SETİ DOLULUK VE BİRİM DOĞRULAMA ANALİZİ ")
    print(f"  Analiz Edilen Dosya: {csv_path}")
    print("==================================================")

    if not os.path.exists(csv_path):
        alt_paths = ["marmara_columns_extracted.csv", "marmara_curated.csv", "marmara_1week.csv", "marmara_raw.csv"]
        csv_path = next((f for f in alt_paths if os.path.exists(f)), csv_path)
        
    if not os.path.exists(csv_path):
        print(f"HATA: '{csv_path}' dosyası bulunamadı. Lütfen geçerli bir CSV dosya yolu belirtin.")
        return

    total_rows = 0
    col_null_counts = {}
    col_dtypes = {}
    col_mins = {}
    col_maxs = {}
    col_means = {}
    col_samples = {}

    first_chunk = True

    print("-> Veri seti okunuyor ve istatistikler hesaplanıyor...")
    for chunk in pd.read_csv(csv_path, chunksize=chunksize, low_memory=False):
        total_rows += len(chunk)
        
        if first_chunk:
            for col in chunk.columns:
                col_null_counts[col] = 0
                col_dtypes[col] = str(chunk[col].dtype)
                is_num = pd.api.types.is_numeric_dtype(chunk[col])
                col_mins[col] = float('inf') if is_num else None
                col_maxs[col] = float('-inf') if is_num else None
                col_means[col] = 0.0 if is_num else None
                valid_sample = chunk[col].dropna()
                col_samples[col] = valid_sample.iloc[0] if len(valid_sample) > 0 else "N/A"
            first_chunk = False

        for col in chunk.columns:
            null_cnt = chunk[col].isna().sum()
            col_null_counts[col] += null_cnt
            
            if pd.api.types.is_numeric_dtype(chunk[col]):
                valid_series = chunk[col].dropna()
                if len(valid_series) > 0:
                    c_min = valid_series.min()
                    c_max = valid_series.max()
                    c_sum = valid_series.sum()
                    
                    if col_mins[col] is None or c_min < col_mins[col]:
                        col_mins[col] = c_min
                    if col_maxs[col] is None or c_max > col_maxs[col]:
                        col_maxs[col] = c_max
                    if col_means[col] is not None:
                        col_means[col] += c_sum

    for col in col_means:
        if col_means[col] is not None:
            non_null_cnt = total_rows - col_null_counts[col]
            if non_null_cnt > 0:
                col_means[col] = col_means[col] / non_null_cnt

    # Maritime AIS Standard Units Reference Mapping (7 Essential Dynamic Motion Columns)
    expected_units = {
        'mmsi': ('Gemi Kimlik No (MMSI)', '9 Haneli Sayı (Örn: 271xxxxxx = Türkiye)'),
        'timestamp': ('Zaman Damgası', 'UTC Datetime (YYYY-MM-DD HH:MM:SS)'),
        'latitude': ('Enlem (Latitude)', 'Derece (N) [Marmara: 40.0° - 41.3°]'),
        'longitude': ('Boylam (Longitude)', 'Derece (E) [Marmara: 26.5° - 30.0°]'),
        'speed': ('Hız (SOG)', 'Knot (Deniz Mili / Saat) [0.0 - 50.0]'),
        'course': ('Hareket Yönü / Rota (COG)', 'Derece (0.0° - 359.9°)'),
        'heading': ('Gemi Pruva Açısı (HDG)', 'Derece (0° - 359°) [511 = Yok/Bozuk]')
    }

    report_rows = []
    for col in col_null_counts.keys():
        null_cnt = col_null_counts[col]
        filled_cnt = total_rows - null_cnt
        fill_rate = (filled_cnt / total_rows) * 100.0 if total_rows > 0 else 0.0
        
        c_min = col_mins.get(col)
        c_max = col_maxs.get(col)
        c_mean = col_means.get(col)
        
        if c_min is not None and not np.isinf(c_min):
            range_str = f"[{c_min:.2f} , {c_max:.2f}] (Ort: {c_mean:.2f})"
        else:
            range_str = "Metinsel / Tarihsel"
            
        unit_info = expected_units.get(col.lower(), (col, "Belirtilmemiş"))

        report_rows.append({
            'Kolon Adı': col,
            'Veri Tipi': col_dtypes[col],
            'Dolu Satır': f"{filled_cnt:,}",
            'Eksik Satır': f"{null_cnt:,}",
            'Doluluk (%)': f"%{fill_rate:.2f}",
            'Min - Max Değer Aralığı': range_str,
            'Standart Birim / Format': unit_info[1]
        })

    report_df = pd.DataFrame(report_rows)

    print(f"\n Toplam Satır Sayısı: {total_rows:,}\n")
    print("=========================================================================================================")
    print("                                  KOLON DOLULUK VE BİRİM RAPORU                                         ")
    print("=========================================================================================================")
    
    pd.set_option('display.max_columns', None)
    pd.set_option('display.max_colwidth', None)
    pd.set_option('display.width', 1000)
    print(report_df[['Kolon Adı', 'Veri Tipi', 'Dolu Satır', 'Eksik Satır', 'Doluluk (%)', 'Min - Max Değer Aralığı']].to_string(index=False))

    print("\n=========================================================================================================")
    print("                               AIS KOLON STANDART BİRİMİ VE DETAY TEYİDİ                                 ")
    print("=========================================================================================================")
    for col in col_null_counts.keys():
        unit_desc, unit_std = expected_units.get(col.lower(), (col, "Standart Tespiti Yapılmadı"))
        print(f"• {col.upper():<12} -> Açıklama: {unit_desc:<30} | Standart Birim: {unit_std}")

    print("\n Raporlama Tamamlandı.\n")

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "marmara_columns_extracted.csv"
    analyze_dataset_quality_and_units(target)
