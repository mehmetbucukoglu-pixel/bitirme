import os
import sys
import pandas as pd

def extract_selected_dynamic_columns(input_csv_path, output_csv_path="marmara_columns_extracted.csv", chunksize=250000):
    """
    AIS Ham Veri Kolon Ayıklama Betiği (Filtresiz & Tam Veri):
    - Hiçbir satır silmez, coğrafi sınır, hız veya sıçrama filtresi uygulamaz.
    - Sadece ilk 7 temel dinamik hareket kolonunu ayıklar.
    """
    print("==================================================")
    print("   AIS HAM VERİ KOLON AYIKLAMA (Sadece 7 Dinamik Kolon)")
    print(f"   Girdi Dosyası : {input_csv_path}")
    print(f"   Çıktı Dosyası : {output_csv_path}")
    print("==================================================")

    if not os.path.exists(input_csv_path):
        # Fallback search for common filenames
        possible_inputs = ["marmara_1week.csv", "marmara_1week", "marmara_raw.csv"]
        input_csv_path = next((f for f in possible_inputs if os.path.exists(f)), input_csv_path)

    if not os.path.exists(input_csv_path):
        print(f"HATA: '{input_csv_path}' dosyası bulunamadı. Lütfen geçerli bir dosya yolu girin.")
        return

    # Sadece ilk 7 temel dinamik hareket ve konum kolonu
    target_columns = [
        'mmsi', 'timestamp', 'latitude', 'longitude', 'speed', 'course', 'heading'
    ]

    # Muhtemel farklı kolon isimlerini yakalamak için haritalama
    alias_map = {
        'sog': 'speed',
        'cog': 'course',
        'hdg': 'heading',
        'lat': 'latitude',
        'lon': 'longitude',
        'time': 'timestamp',
        'date_time': 'timestamp'
    }

    first_chunk = True
    total_extracted_rows = 0
    selected_cols_found = []

    print("\n-> Veri işleniyor ve sadece ilk 7 dinamik hareket kolonu aktarılıyor...")

    for i, chunk in enumerate(pd.read_csv(input_csv_path, chunksize=chunksize, low_memory=False)):
        total_extracted_rows += len(chunk)

        renamed_cols = {col: alias_map[col.lower()] for col in chunk.columns if col.lower() in alias_map}
        if renamed_cols:
            chunk = chunk.rename(columns=renamed_cols)

        if first_chunk:
            selected_cols_found = [c for c in target_columns if c in chunk.columns]
            print(f"   Bulunan ve Seçilen Kolonlar ({len(selected_cols_found)}/7):")
            for col in selected_cols_found:
                print(f"     • '{col}'")
            first_chunk = False

        # Sadece bulunan hedef kolonları seç (satır filtresi yok)
        extracted_chunk = chunk[selected_cols_found].copy()

        mode = 'w' if i == 0 else 'a'
        header = (i == 0)
        extracted_chunk.to_csv(output_csv_path, mode=mode, header=header, index=False)
        print(f"   Chunk {i+1}: {len(extracted_chunk):,} satır aktarıldı.")

    print("\n==================================================")
    print("         KOLON AYIKLAMA İŞLEMİ TAMAMLANDI         ")
    print("==================================================")
    print(f"1. Toplam Aktarılan Satır Sayısı : {total_extracted_rows:,}")
    print(f"2. Seçilen Kolon Sayısı           : {len(selected_cols_found)} / 7")
    print(f"3. Oluşturulan Çıktı Dosyası      : {output_csv_path}")
    print("   (Not: Hiçbir satır silinmemiş, filtre uygulanmamıştır.)")
    print("==================================================\n")

if __name__ == "__main__":
    in_file = sys.argv[1] if len(sys.argv) > 1 else "marmara_1week.csv"
    out_file = sys.argv[2] if len(sys.argv) > 2 else "marmara_columns_extracted.csv"
    extract_selected_dynamic_columns(in_file, out_file)
