#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AIS hız temizliği, Haversine ile eksik hız tahmini ve denetim (Python >=3.10).

KURULUM
    python -m pip install "pandas>=2.0" numpy

ÇALIŞTIRMA (sütun adları yaygın adlardan otomatik bulunur)
    python ais_temizle.py veriler.csv --out sonuc

SÜTUNLARI ELLE SEÇME
    python ais_temizle.py veriler.csv --mmsi MMSI --time timestamp \
        --lat latitude --lon longitude --sog SOG --out sonuc

BİRİMLER / CSV BİÇİMİ
    --sog-unit knot       Çözülmüş knot; varsayılan. 153 = 153 knot!
    --sog-unit kmh        km/h; hesaplamadan önce 1.852'ye bölünür.
    --sog-unit raw10      Ham 0.1 knot AIS alanı; 153 = 15.3 knot.
    --time-unit iso       Tarih metni; saat dilimsiz tarihler UTC kabul edilir.
    --time-unit s         Unix saniye. AIS mesajındaki yalnız 0-59 saniye alanı
                         tam tarih/saat yerine kullanılamaz.
    --time-unit ms        Unix milisaniye.
    --time-format '%d.%m.%Y %H:%M:%S'  Belirsiz tarih metni için açık biçim.
    --sep ';' --decimal ','           Noktalı virgül / ondalık virgül.
    SOG sütunu yoksa bütün hızlar eksik kabul edilir. Diğer dört alan gerekir.

İŞLEM SIRASI
  1. Boş/null/NaN ve AIS 1023 (çözülmüş 102.3 knot) kodunu EKSİK olarak
     koru. Sayısal olmayan, +/-sonsuz, negatif ve 1022 kodunu ele.
  2. SOG > 50 knot. Tam 50 ve 0 korunur. Girdi hız birimini siz belirtmelisiniz.
  3. MMSI, koordinat ve tarih denetimi.
  4. Kullanıcının kabul ettiği Marmara çalışma dikdörtgeni dışındaki kayıtları
     sil; çıktı tablolarının hiçbirine alma. Özette yalnız sayısını tut.
     Sınır üzerindeki noktalar içeride kabul edilir. Sınır dışına çıkıp dönen
     geminin kayıtlarını yeni bir bölümde başlat; çıkışın üzerinden hız türetme.
  5. Aynı ölçüm tekrarlarından birini tut. Aynı MMSI ve zamanda farklı
     konum/hız varsa hepsini incelemeye ayır.
  6. Haversine mesafesi: d > 50*1852/3600*dt + konum_toleransi ise şüpheli.
     A-B ve B-C geçmiyor, A-C geçiyorsa B konum sıçraması adayıdır.
     Diğer sorunlu bağlantılarda iki uç da işaretlenir; yanlış uç varsayılmaz.
  7. Eksik SOG için uygun bitişik aralığın ortalama hızını tahmin olarak yaz.
     Önce önceki aralık seçilir; uygun değilse sonraki aralık denenir.
     Hatalı konum, dt<=0, çok kısa/uzun aralık, yüksek belirsizlik veya
     hesaplanan hız>50 olduğunda o aralık eksik hız tamamlamada kullanılmaz.
  8. Yalnız BİLDİRİLMİŞ iki SOG'un ortalamasını aralığın hesaplanan hızıyla
     karşılaştır. Tahmin edilmiş hızlar bağımsız doğrulama verisi sayılmaz.
  9. |SOG_B-SOG_A| ve zamana bölünmüş değişim ile ani hız değişimi taraması.
     A ve C'nin hızları yakınsa ve B'ye geliş/gidiş ani ve ters işaretliyse
     B tekil hız sıçraması adayıdır. Çözülemeyen değişimlerde iki uç işaretlenir.

MARMARA ÇALIŞMA ALANI (kullanıcının kabul ettiği sınırlar; ek seçenek gerekmez)
    Güney: 39°59'56.1" N  (yaklaşık 39.99891667°)
    Kuzey: 41°13'58.6" N  (yaklaşık 41.23294444°)
    Batı:  26°10'27.2" E  (yaklaşık 26.17422222°)
    Doğu:  29°56'31.9" E  (yaklaşık 29.94219444°)
    Hesaplamada DMS'den dönüştürülmüş tam float değerleri kullanılır; gösterim
    için yuvarlanmış koordinatlar sınır hesabında kullanılmaz.
    Bu bir bounding-box filtresidir; gerçek kıyı/deniz poligonu veya kara maskesi
    değildir. İçindeki kara noktalarını, koyları veya boğazları ayrıca ayırmaz.
    Bölge dışında olmak AIS ölçümünün yanlış olduğunu göstermez. Çalışma
    kapsamı dışında olduğundan doğrudan silinir; elenen_ais.csv dahil hiçbir
    çıktı tablosuna yazılmaz. Girdi dosyası değiştirilmez.
    Geçersiz/eksik koordinatlar konum_gecersiz olarak elenen_ais.csv'de tutulur;
    nerede oldukları belirlenemediği için kesin bölge dışı sayılmaz.

FORMÜL VE ANLAMI
    Açılar radyana çevrilir. R=6371 km ile Haversine mesafesi hesaplanır.
    v_calc_kn = (d_m / 1852) / (dt_s / 3600)
    Bu, iki nokta arasındaki ortalama yer değiştirme hızıdır; anlık SOG değildir.
    Haversine küresel bir yaklaşımdır; önceki sürüm WGS84 elipsoidini kullanıyordu.
    Dönüşlerde gerçek gidilen yol iki konum arasındaki mesafeden uzun olabilir.
    Zamandaki eksik kayıtlar ve koordinatlar doldurulmaz; yalnız SOG tahmin edilir.
    Sonraki kaydı kullanan tahmin çevrimdışı analize uygundur; canlı tahminde
    gelecek veri sızıntısını önlemek için --fill-direction previous kullanın.

BAŞLANGIÇ AYARLARI (50 dışındaki eşikler evrensel standart DEĞİLDİR)
    --pos-tol-m 100       İki konumun TOPLAM mesafe belirsizliği, metre.
    --min-dt-s 2          Daha kısa aralıklarda SOG ivme testi yapılmaz.
    --max-gap-s 600       Daha uzun boşlukta SOG süreksizliği testi yapılmaz;
                         konumdan hesaplanan üst hız testi yine yapılır.
    --jump-kn 8           Ani değişimde asgari hız farkı, knot.
    --accel-mps2 0.1      Aynı anda aşılması gereken değişim hızı, m/s².
    --return-tol-kn 3     Tekil sıçramada A ve C arasındaki azami hız farkı.
    --max-fill-uncertainty-kn 5  Eksik hız tahmininde azami konum kaynaklı
                                hız belirsizliği: pos_tol_m / dt / KNOT_MPS.
    --compare-alpha 0.05  Hız farklarının merkez %95 aralığını kullan.
    --compare-lower-kn L --compare-upper-kn U
                         Daha önce kalibre edilmiş sabit alt/üst sınırları kullan.
    --compare-max-gap-s 120  SOG karşılaştırmasında azami zaman aralığı.
    --compare-stable-delta-kn 3  İki bildirilen hız arasındaki azami fark;
                                daha hızlı değişimde ortalama testi atlanır.
    --fill-direction previous_or_next  Önce önceki, gerekirse sonraki aralık.
    --fill-direction previous          Yalnız önceki aralık; çevrimiçi kullanım.
HIZ FARKI EŞİĞİNİN BİLİMSEL DAYANAĞI
    Paulig ve Okhrin (2024), Ocean Engineering 312, 119092,
    DOI: 10.1016/j.oceaneng.2024.119092, "Reported against positional velocity".
    e = (SOG_A+SOG_B)/2 - v_calc    (İŞARETLİ fark, knot)
    L = quantile(e, alpha/2); U = quantile(e, 1-alpha/2)
    e < L veya e > U => bağlantının iki ucu şüpheli.
    alpha=0.05 => merkez %95, iki kuyrukta %2.5. Bu %5 kesin hata demek değildir.
    Önceki 5 knot + konum payı formülü hız karşılaştırmasından kaldırılmıştır.
    Konum toleransı konum denetiminde ve eksik hız tahmininde kullanılmaya devam eder.
    Varsayılan olarak uygun aralıklar aynı girdi dosyasından kalibre edilir.
    Her kuyrukta en az bir gözleme karşılık gelen sayıda uygun aralık gerekir:
    ceil(2/alpha), varsayılan alpha=0.05 için 40. Bu yalnız işlemsel bir alt
    kontroldür, makaleden alınmış bir yeterlilik garantisi değildir. Daha azında
    eşik öğrenilmez ve karşılaştırma yapılmamış olarak raporlanır.
    Az sayıda kayıttan güvenilir eşik beklemeyin.
    Büyük bir referans döneminden öğrenilen L/U'yu sonraki analizlerde --compare-
    lower-kn/upper-kn ile sabitlemek mümkündür. ML test verisinden eşik öğrenmeyin.
    Bu, makalenin hız-farkı ölçütünün BASİTLEŞTİRİLMİŞ uyarlamasıdır: makale
    gemi boyu sınıfları ve diğer metriklerle rotayı böler; bu betik ortak bir
    dağılımdan sınır bulup kayıtları incelemeye ayırır. Tam algoritma tekrarı değildir.
    Verinin çoğunluğunun makul olduğu varsayılır. Her kayıtta aynı sistematik
    hata varsa bu yöntem onu yakalamayabilir; sıra dışılık kesin hata değildir.
    Merkez %95, bir ölçümün %95 güvenle doğru olduğu anlamına gelmez.
Bu sayıları verinin örnekleme sıklığına ve gemi türüne göre kalibre edin.
Örneğin 10 dakika boyunca kademeli hızlanma, tekil hatalı sinyal değildir.

ÇIKTILAR (girdi dosyası değiştirilmez)
    temiz_ais.csv       Kurallarla elenmeyen ve şüpheli işaretlenmeyen kayıtlar.
    elenen_ais.csv      Bölge dışı kayıtlar HARİÇ elenenler ve birincil nedenleri.
    supheli_ais.csv     Süreksizlik/çelişki adayları; kesin hata iddiası yoktur.
                       Uygun aralık bulunamadığı için hız tamamlanamayanlar da
                       bu dosyaya alınır; eksiklik kesin ölçüm hatası sayılmaz.
    tum_kayitlar.csv    Bölge dışı kayıtlar HARİÇ tüm kararlar ve özgün alanlar.
    kalite_ozeti.json   Sayılar, kullanılan ayarlar, kaynaklar.
Şüpheliler temiz çıktıya alınmaz, ayrı dosyada korunur. Ham girdi korunur.
Marmara dışındaki kayıtlar döndürülen DataFrame'den de çıkarılır; toplam
çıktı kayıt sayısı + marmara_disi_silinen = girdi kayıt sayısıdır.
qc_row_id: başlık hariç 1 tabanlı girdi kayıt numarası, fiziksel satır değildir.
qc_prev_row_id: ölçümlerde kullanılan önceki kaydın kimliği. Önceki kayıt
şüpheli olabilir; metrikler denetim öncesi komşulara aittir. Sonraki analizde
yalnız aynı qc_segment_id içindeki temiz kayıtları birbirine bağlayın.
YENİ SÜTUNLAR
    qc_inside_marmara   True: dikdörtgen içinde veya sınırda;
                        boş: koordinat geçersiz/eksik olduğundan belirlenemedi.
                        False olan kayıtlar çıktılara yazılmadan silinir.
    qc_area_pass_id     Aynı MMSI'de bölge dışı kayıtlar geçildikçe değişen bölüm
                        kimliği. Farklı kimlikteki noktalar arasında hız türetilmez.
    qc_sog_reported_kn  Bildirilen hız (knot); boş/NaN/bilgi yok => NaN.
    qc_sog_kn           Kullanılacak hız: bildirilen değer veya eksik hız tahmini.
    qc_speed_source     reported / calculated_previous / calculated_next /
                        unavailable / invalid.
    qc_speed_is_imputed Hesaplanarak tamamlandı mı?
    qc_position_speed_kn  Önceki nokta -> bu nokta aralığının ham hesaplanan hızı.
    qc_calc_next_kn       Bu nokta -> sonraki nokta aralığının hesaplanan hızı.
    qc_fill_start_row_id, qc_fill_end_row_id, qc_fill_dt_s:
                        Tahminin hangi aralığa ait olduğunu gösterir.
    qc_fill_block_reason: Tamamlanamayan eksik hız için önceki/sonraki aralığın
                         neden kullanılamadığını gösterir.
    qc_pair_sog_mean_kn, qc_pair_speed_error_kn, qc_pair_signed_error_kn:
                        Önceki aralığa ait bildirilen ortalama, mutlak fark,
                        işaretli fark. İşaretli fark = bildirilen ortalama - hesaplanan.
    qc_pair_compare_lower_kn, qc_pair_compare_upper_kn:
                        Kalibre edilen işaretli fark alt/üst sınırları.
    qc_pair_compare_tested  Bu aralık SOG karşılaştırmasına girdi mi?
    qc_continuity_checked=False: bildirilen SOG için kullanılabilir komşuyla
                                ani değişim kontrolü yapılamamış.
    qc_speed_compare_checked=False: bildirilen SOG konum hızıyla karşılaştırılamamış.
Tahmin edilmiş hızın kesin anlık ölçüm olduğunu varsaymayın; qc_speed_source'u
analiz ve raporlarda koruyun. Bildirilen hızlar tahminlerle değiştirilmez.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import sys
import unicodedata

import numpy as np
import pandas as pd


KNOT_MPS = 1852 / 3600
EARTH_RADIUS_M = 6_371_000.0
# Kullanıcı tarafından verilen DMS sınırları. Tüm yönler N/E, yani pozitiftir.
# Ondalık dereceye tek dönüşüm; filtre için yuvarlama veya ek tolerans uygulanmaz.
MARMARA_BOUNDS = {
    "lat_min": (39 * 3600 + 59 * 60 + 56.1) / 3600,
    "lat_max": (41 * 3600 + 13 * 60 + 58.6) / 3600,
    "lon_min": (26 * 3600 + 10 * 60 + 27.2) / 3600,
    "lon_max": (29 * 3600 + 56 * 60 + 31.9) / 3600,
}
SOURCES = {
    "ais_ozel_kodlari": "https://www.itu.int/rec/R-REC-M.1371",
    "50_knot_literatur_ornegi": "https://doi.org/10.5194/essd-17-277-2025",
    "haversine_formulu": "https://scikit-learn.org/stable/modules/generated/sklearn.metrics.pairwise.haversine_distances.html",
    "deniz_mili_knot": "https://oceanservice.noaa.gov/facts/nautical-mile-knot.html",
    "hiz_farki_alpha_yontemi": "https://doi.org/10.1016/j.oceaneng.2024.119092",
    "hiz_farki_acik_metin": "https://arxiv.org/html/2407.04402v3#S6.SS2.SSS4",
}


@dataclass(frozen=True)
class Config:
    sog_unit: str = "knot"
    time_unit: str = "iso"
    time_format: str | None = None
    decimal: str = "."
    max_speed_kn: float = 50.0
    pos_tol_m: float = 100.0
    min_dt_s: float = 2.0
    max_gap_s: float = 600.0
    jump_kn: float = 8.0
    accel_mps2: float = 0.1
    return_tol_kn: float = 3.0
    max_fill_uncertainty_kn: float = 5.0
    compare_alpha: float = 0.05
    compare_lower_kn: float | None = None
    compare_upper_kn: float | None = None
    compare_max_gap_s: float = 120.0
    compare_stable_delta_kn: float = 3.0
    fill_direction: str = "previous_or_next"


ALIASES = {
    "mmsi": ("mmsi", "ssvid"),
    "time": ("timestamp", "basedatetime", "datetime", "time", "date_time", "utc_time"),
    "lat": ("latitude", "lat", "enlem"),
    "lon": ("longitude", "lon", "lng", "boylam"),
    "sog": ("sog", "speed", "velocity", "speed_over_ground", "speed_knots", "hiz"),
}


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text).strip().lower().replace("ı", "i"))
    return "".join(c for c in text if not unicodedata.combining(c) and c.isalnum())


def resolve_columns(frame: pd.DataFrame, explicit: dict[str, str | None]) -> dict[str, str | None]:
    result = {}
    for field, aliases in ALIASES.items():
        if explicit.get(field):
            matches = [explicit[field]] if explicit[field] in frame.columns else []
        else:
            wanted = {norm(x) for x in aliases}
            matches = [c for c in frame.columns if norm(c) in wanted]
        if field == "sog" and not matches and not explicit.get(field):
            result[field] = None
            continue
        if len(matches) != 1:
            raise ValueError(
                f"{field} sütunu kesin seçilemedi. --{field} SUTUN_ADI belirtin. "
                f"Bulunan adaylar: {matches}; mevcut sütunlar: {list(frame.columns)}"
            )
        result[field] = matches[0]
    selected = [v for v in result.values() if v is not None]
    if len(set(selected)) != len(selected):
        raise ValueError("MMSI, zaman, enlem, boylam ve SOG farklı sütunlar olmalı.")
    return result


def numeric(series: pd.Series, decimal: str) -> pd.Series:
    text = series.astype("string").str.strip().str.lower()
    text = text.replace({"∞": "inf", "+∞": "inf", "-∞": "-inf", "−∞": "-inf"})
    if decimal == ",":
        text = text.str.replace(",", ".", regex=False)
    return pd.to_numeric(text, errors="coerce").astype("float64")


def haversine_m(lat1, lon1, lat2, lon2):
    """Derece cinsinden koordinatlardan küresel mesafe, metre. R=6371 km."""
    lat1, lon1, lat2, lon2 = [np.radians(np.asarray(v, dtype=float)) for v in (lat1, lon1, lat2, lon2)]
    a = np.sin((lat2-lat1)/2)**2 + np.cos(lat1)*np.cos(lat2)*np.sin((lon2-lon1)/2)**2
    return 2 * EARTH_RADIUS_M * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def distances(lat1, lon1, lat2, lon2, mask) -> np.ndarray:
    result = np.full(len(mask), np.nan)
    if np.any(mask):
        result[mask] = haversine_m(lat1[mask], lon1[mask], lat2[mask], lon2[mask])
    return result


def speed_difference_bounds(errors, cfg: Config):
    """İşaretli SOG farkları için iki taraflı ampirik alpha-quantile sınırları."""
    errors = np.asarray(errors, dtype=float)
    finite_errors = errors[np.isfinite(errors)]
    fixed = cfg.compare_lower_kn is not None
    required_count = int(np.ceil(2/cfg.compare_alpha))
    info = {
        "yontem": "sabit_referans_araligi" if fixed else "alpha_empirik_ortak_dagilim",
        "alpha": cfg.compare_alpha,
        "alt_kantil": cfg.compare_alpha / 2,
        "ust_kantil": 1 - cfg.compare_alpha / 2,
        "uygun_aralik_sayisi": int(len(finite_errors)),
        "islemsel_asgari_kalibrasyon_araligi": required_count,
        "alt_sinir_kn": None,
        "ust_sinir_kn": None,
        "sifiri_kapsiyor_mu": None,
        "uyari": [],
    }
    if fixed:
        lower, upper = float(cfg.compare_lower_kn), float(cfg.compare_upper_kn)
    elif len(finite_errors) >= required_count:
        lower, upper = np.quantile(finite_errors, [cfg.compare_alpha/2, 1-cfg.compare_alpha/2])
    else:
        info["durum"] = "esik_yok"
        info["uyari"].append(f"En az {required_count} uygun aralık veya önceden kalibre edilmiş alt/üst sınırlar gerekli; hız-farkı testi yapılmadı.")
        return None, None, info
    info["durum"] = "esik_hazir"
    info["alt_sinir_kn"], info["ust_sinir_kn"] = float(lower), float(upper)
    info["sifiri_kapsiyor_mu"] = bool(lower <= 1e-9 and upper >= -1e-9)
    if not info["sifiri_kapsiyor_mu"]:
        info["uyari"].append("Referans aralığı sıfır hız farkını kapsamıyor. Sistematik sapma, dönüşler ve zaman eşleşmesini inceleyin; eşik kendi başına doğruluk kanıtı değildir.")
    if not fixed:
        info["uyari"].append("Eşik aynı girdi dosyasının ortak dağılımından öğrenildi; küçük/kirli veya tek gemi türüne ait örneklerde genelleme yapmayın.")
    return float(lower), float(upper), info


def clean_ais(raw: pd.DataFrame, columns: dict[str, str | None], cfg: Config = Config()):
    """DataFrame alır; (tüm kayıtlar, JSON uyumlu özet) döndürür.

    Bölge dışındaki satırlar çıktıdan silinir; kalanların girdi alanları korunur.
    Girdi MMSI'lerini metin olarak okumak önerilir.
    Tüm veri RAM'e yüklenir; çok büyük dosyalar için MMSI bazında bölünmelidir.
    """
    if cfg.sog_unit not in {"knot", "kmh", "raw10"} or cfg.time_unit not in {"iso", "s", "ms"}:
        raise ValueError("Bilinmeyen hız/zaman birimi.")
    values = (cfg.max_speed_kn, cfg.pos_tol_m, cfg.min_dt_s, cfg.max_gap_s,
              cfg.jump_kn, cfg.accel_mps2, cfg.return_tol_kn, cfg.max_fill_uncertainty_kn,
              cfg.compare_alpha, cfg.compare_max_gap_s, cfg.compare_stable_delta_kn)
    if not all(np.isfinite(v) for v in values):
        raise ValueError("Eşikler sonlu sayılar olmalı.")
    if min(cfg.max_speed_kn, cfg.min_dt_s, cfg.jump_kn, cfg.accel_mps2) <= 0:
        raise ValueError("Hız, zaman, değişim ve ivme eşikleri pozitif olmalı.")
    if (min(cfg.pos_tol_m, cfg.return_tol_kn, cfg.compare_stable_delta_kn) < 0 or
        cfg.max_fill_uncertainty_kn <= 0 or cfg.max_gap_s < cfg.min_dt_s or cfg.compare_max_gap_s < cfg.min_dt_s):
        raise ValueError("Toleranslar negatif olamaz; max-gap >= min-dt olmalı.")
    if not 0 < cfg.compare_alpha < 1:
        raise ValueError("compare-alpha 0 ile 1 arasında olmalı.")
    if (cfg.compare_lower_kn is None) != (cfg.compare_upper_kn is None):
        raise ValueError("compare-lower-kn ve compare-upper-kn birlikte belirtilmeli.")
    if cfg.compare_lower_kn is not None and (
        not np.isfinite(cfg.compare_lower_kn) or not np.isfinite(cfg.compare_upper_kn) or
        cfg.compare_lower_kn > cfg.compare_upper_kn
    ):
        raise ValueError("Sabit hız farkı sınırları sonlu ve alt <= üst olmalı.")
    if cfg.fill_direction not in {"previous", "previous_or_next"}:
        raise ValueError("Bilinmeyen eksik hız tamamlama yönü.")
    if cfg.decimal not in {".", ","}:
        raise ValueError("Ondalık ayracı '.' veya ',' olmalı.")
    if any(str(c).startswith("qc_") for c in raw.columns):
        raise ValueError("Girdi qc_ ile başlayan sütun içeriyor; özgün ham dosyayı kullanın.")
    if set(columns) != set(ALIASES) or any(
        (c is None and key != "sog") or (c is not None and c not in raw.columns) for key, c in columns.items()
    ):
        raise ValueError("MMSI/zaman/enlem/boylam için geçerli sütun eşlemesi gerekli; SOG isteğe bağlıdır.")

    df = raw.reset_index(drop=True).copy()
    df["qc_row_id"] = np.arange(1, len(df) + 1)
    df["qc_status"] = "aday"
    df["qc_reason"] = ""
    df["qc_note"] = ""
    stages = []

    def reject(mask, reason):
        selected = np.asarray(mask, dtype=bool) & df["qc_status"].eq("aday").to_numpy()
        df.loc[selected, "qc_status"] = "elendi"
        df.loc[selected, "qc_reason"] = reason

    def stage(name):
        stages.append({"asama": name, "kalan_kayit": int(df["qc_status"].eq("aday").sum())})

    sog_input = df[columns["sog"]] if columns["sog"] is not None else pd.Series("", index=df.index, dtype="string")
    text = sog_input.astype("string").str.strip().str.lower().fillna("")
    speed = numeric(sog_input, cfg.decimal)
    missing = text.isin(["", "null", "none", "na", "n/a", "<na>", "nan", "+nan", "-nan"])
    nonfinite_tokens = text.isin(["inf", "+inf", "-inf",
                                 "infinity", "+infinity", "-infinity", "∞", "+∞", "-∞", "−∞"])
    reject(nonfinite_tokens | np.isinf(speed), "sog_sonlu_degil")
    reject(speed.isna() & ~missing, "sog_sayisal_degil")
    reject(speed < 0, "sog_negatif")
    if cfg.sog_unit == "raw10":
        reject((speed > 1023) | (np.isfinite(speed) & (speed != np.floor(speed))), "sog_ham_kod_gecersiz")
        speed = speed / 10
    elif cfg.sog_unit == "kmh":
        speed = speed / 1.852
    # Bunlar çözülmüş 0.1 knot AIS alanı içindir (örn. mesaj 1/2/3/18).
    ais_unavailable = np.isclose(speed, 102.3, rtol=0, atol=1e-8)
    missing = missing | ais_unavailable
    df["qc_sog_input_state"] = np.where(missing, "eksik", "bildirilen")
    df.loc[ais_unavailable, "qc_sog_input_state"] = "ais_bilgi_yok_1023"
    df["qc_sog_reported_kn"] = speed.mask(missing)
    df["qc_sog_kn"] = df["qc_sog_reported_kn"]
    reject(np.isclose(speed, 102.2, rtol=0, atol=1e-8), "sog_ais_ust_kod_1022")
    stage("1_gecersiz_hiz_ele_eksikleri_koru")

    # Önceki kararla uyumlu: TAM 50 KORUNUR; >= 50 kullanılmıyor.
    reject((speed > cfg.max_speed_kn) & ~missing, "sog_ust_esik")
    df["qc_speed_source"] = np.where(missing, "unavailable", "reported")
    df.loc[df["qc_status"].eq("elendi"), "qc_speed_source"] = "invalid"
    df.loc[df["qc_status"].eq("elendi"), "qc_sog_input_state"] = "gecersiz"
    df.loc[df["qc_status"].eq("elendi"), "qc_sog_kn"] = np.nan
    df["qc_speed_is_imputed"] = False
    stage("2_ust_hiz_filtresi")

    df["qc_mmsi"] = df[columns["mmsi"]].astype("string").str.strip().str.replace(r"\.0$", "", regex=True)
    reject(~df["qc_mmsi"].str.fullmatch(r"[0-9]{9}", na=False) | df["qc_mmsi"].eq("000000000"), "mmsi_gecersiz")
    # Burada yalnız sözdizimi doğrulanır; gerçek bir gemiye ait olduğu doğrulanmaz.
    if cfg.time_unit == "iso":
        ts = df[columns["time"]].astype("string").str.strip()
        numeric_time = ts.str.fullmatch(r"[+-]?[0-9]+(?:\.[0-9]+)?", na=False)
        if cfg.time_format is None and (numeric_time & df["qc_status"].eq("aday")).any():
            raise ValueError("Sayısal zaman bulundu. Unix için --time-unit s veya ms belirtin; "
                             "yalnız AIS saniye alanı kullanılamaz.")
        df["qc_time_utc"] = pd.to_datetime(ts, format=cfg.time_format or "mixed", utc=True, errors="coerce")
    else:
        df["qc_time_utc"] = pd.to_datetime(numeric(df[columns["time"]], cfg.decimal), unit=cfg.time_unit,
                                             origin="unix", utc=True, errors="coerce")
    reject(df["qc_time_utc"].isna(), "zaman_gecersiz")
    df["qc_lat"] = numeric(df[columns["lat"]], cfg.decimal)
    df["qc_lon"] = numeric(df[columns["lon"]], cfg.decimal)
    coordinate_valid = (np.isfinite(df["qc_lat"]) & df["qc_lat"].between(-90, 90) &
                        np.isfinite(df["qc_lon"]) & df["qc_lon"].between(-180, 180))
    reject(~coordinate_valid, "konum_gecersiz")
    stage("3_kimlik_zaman_konum")

    inside_marmara = (coordinate_valid &
                      df["qc_lat"].between(MARMARA_BOUNDS["lat_min"], MARMARA_BOUNDS["lat_max"], inclusive="both") &
                      df["qc_lon"].between(MARMARA_BOUNDS["lon_min"], MARMARA_BOUNDS["lon_max"], inclusive="both"))
    df["qc_inside_marmara"] = pd.Series(pd.NA, index=df.index, dtype="boolean")
    df.loc[coordinate_valid, "qc_inside_marmara"] = inside_marmara[coordinate_valid]
    reject(coordinate_valid & ~inside_marmara, "marmara_sinirlari_disinda")
    stage("4_marmara_calisma_alani")

    # Coğrafi kesintileri tüm zamanlanabilir ham kayıtlardan bul. Bir sınır dışı
    # nokta daha önce örn. yüksek SOG nedeniyle elenmiş olsa da kesinti oluşturur.
    # Böylece içeride A -> dışarıda B -> içeride C, A-C diye birleştirilmez.
    trackable = (df["qc_mmsi"].str.fullmatch(r"[0-9]{9}", na=False) &
                 df["qc_mmsi"].ne("000000000") & df["qc_time_utc"].notna())
    area_order = df.loc[trackable].sort_values(["qc_mmsi", "qc_time_utc", "qc_row_id"], kind="stable")
    known_outside = area_order["qc_inside_marmara"].eq(False).fillna(False).astype("int64")
    area_counter = known_outside.groupby(area_order["qc_mmsi"], sort=False).cumsum()
    df["qc_area_pass_id"] = pd.Series(pd.NA, index=df.index, dtype="Int64")
    area_ids = area_order.index[area_order["qc_inside_marmara"].fillna(False)]
    df.loc[area_ids, "qc_area_pass_id"] = area_counter.loc[area_ids]

    keys = ["qc_mmsi", "qc_time_utc", "qc_lat", "qc_lon", "qc_sog_kn"]
    active = df.loc[df["qc_status"].eq("aday")]
    duplicates = active.index[active.duplicated(keys, keep="first")]
    reject(df.index.isin(duplicates), "ayni_olcum_tekrari")
    stage("5_tekrar_kayitlar")

    w = df.loc[df["qc_status"].eq("aday")].sort_values(
        ["qc_mmsi", "qc_time_utc", "qc_row_id"], kind="stable").copy()
    ix = w.index.to_numpy()
    n = len(w)
    flags: dict[str, np.ndarray] = {}
    mmsi = w["qc_mmsi"].to_numpy()
    lat = w["qc_lat"].to_numpy(float)
    lon = w["qc_lon"].to_numpy(float)
    # Bildirilen ve türetilen hızlar ayrı kalır; bağımsız kontroller yalnız
    # gerçek bildirilen SOG değerleriyle yapılır.
    sog = w["qc_sog_reported_kn"].to_numpy(float)
    t = w["qc_time_utc"].astype("int64").to_numpy() / 1e9
    same_ship = np.zeros(n, dtype=bool)
    same_ship[1:] = mmsi[1:] == mmsi[:-1]
    passes = w["qc_area_pass_id"].to_numpy(dtype="int64")
    same = same_ship & (passes == np.roll(passes, 1))
    area_break = same_ship & ~same
    dt = np.full(n, np.nan)
    dt[same] = (t - np.roll(t, 1))[same]
    conflict = w.duplicated(["qc_mmsi", "qc_time_utc"], keep=False).to_numpy()
    flags["ayni_zamanda_celiskili_olcum"] = conflict
    # Bir çelişkili kaydı seçip diğerini gerçek kabul etme.
    geom_test = same & (dt > 0) & ~conflict & ~np.roll(conflict, 1)
    d = distances(np.roll(lat, 1), np.roll(lon, 1), lat, lon, geom_test)
    geom_bad = geom_test & (d > cfg.max_speed_kn * KNOT_MPS * dt + cfg.pos_tol_m)
    v_position = np.full(n, np.nan)
    np.divide(d, dt * KNOT_MPS, out=v_position, where=geom_test)

    # B'yi atlayıp A-C bağlantısını sınama. Kararlar tek geçişte verilir;
    # şüpheli bir noktadan sonraki tüm noktalar zincirleme silinmez.
    candidate = np.zeros(n, dtype=bool)
    if n >= 3:
        candidate[1:-1] = geom_bad[1:-1] & geom_bad[2:]
    bridge_dt = np.roll(t, -1) - np.roll(t, 1)
    candidate &= (bridge_dt > 0) & (bridge_dt <= cfg.max_gap_s)
    bridge_d = distances(np.roll(lat, 1), np.roll(lon, 1), np.roll(lat, -1), np.roll(lon, -1), candidate)
    pos_spike = candidate & (bridge_d <= cfg.max_speed_kn * KNOT_MPS * bridge_dt + cfg.pos_tol_m)
    flags["tekil_konum_sicramasi_adayi"] = pos_spike
    unresolved_geom = geom_bad & ~pos_spike & ~np.roll(pos_spike, 1)
    flags["konum_zaman_baglantisi_supheli"] = unresolved_geom | np.roll(unresolved_geom, -1)

    position_suspicious = conflict | pos_spike | flags["konum_zaman_baglantisi_supheli"]
    local_edge = (geom_test & (dt >= cfg.min_dt_s) & (dt <= cfg.max_gap_s) & ~geom_bad &
                  ~position_suspicious & ~np.roll(position_suspicious, 1))
    pos_uncertainty = np.full(n, np.nan)
    np.divide(cfg.pos_tol_m, dt * KNOT_MPS, out=pos_uncertainty, where=geom_test)
    fill_edge = (local_edge & np.isfinite(v_position) & (v_position <= cfg.max_speed_kn) &
                 (pos_uncertainty <= cfg.max_fill_uncertainty_kn))
    missing_local = missing.to_numpy(dtype=bool)[ix]
    fill_previous = missing_local & fill_edge
    fill_next = np.zeros(n, dtype=bool)
    if cfg.fill_direction == "previous_or_next":
        fill_next = missing_local & ~fill_previous & np.roll(fill_edge, -1)
    imputed = fill_previous | fill_next
    used_sog = sog.copy()
    used_sog[fill_previous] = v_position[fill_previous]
    used_sog[fill_next] = np.roll(v_position, -1)[fill_next]
    df.loc[ix, "qc_sog_kn"] = used_sog
    df.loc[ix[fill_previous], "qc_speed_source"] = "calculated_previous"
    df.loc[ix[fill_next], "qc_speed_source"] = "calculated_next"
    df.loc[ix[imputed], "qc_speed_is_imputed"] = True
    flags["eksik_hiz_tahmin_edilemedi"] = missing_local & ~imputed

    edge_block = np.select(
        [area_break, ~same, conflict | np.roll(conflict, 1), dt <= 0,
         position_suspicious | np.roll(position_suspicious, 1),
         dt < cfg.min_dt_s, dt > cfg.max_gap_s, v_position > cfg.max_speed_kn,
         pos_uncertainty > cfg.max_fill_uncertainty_kn, fill_edge],
        ["marmara_disina_cikis_araligi", "onceki_konum_yok", "ayni_zamanda_celiski", "zaman_farki_pozitif_degil",
         "supheli_konum", "cok_kisa_zaman_araligi", "uzun_zaman_boslugu",
         "hesaplanan_hiz_ust_esik", "konum_belirsizligi_yuksek", ""],
        default="uygun_aralik_yok",
    )
    fill_block = np.full(n, "", dtype=object)
    unfilled = missing_local & ~imputed
    fill_block[unfilled] = np.char.add("previous:", edge_block[unfilled])
    if cfg.fill_direction == "previous_or_next":
        next_block = np.where(np.roll(area_break, -1), "marmara_disina_cikis_araligi",
                              np.where(np.roll(same, -1), np.roll(edge_block, -1), "sonraki_konum_yok"))
        fill_block[unfilled] = [str(a) + ";next:" + str(b) for a, b in zip(fill_block[unfilled], next_block[unfilled])]
    df["qc_fill_block_reason"] = ""
    df.loc[ix, "qc_fill_block_reason"] = fill_block

    # Her tahminin aralık kimliği saklanır. SOG_i için önceki aralığı
    # kullanmak v(t_i)'yi tam ölçmez; yalnız bu aralığın ortalamasını tahmin eder.
    rows = w["qc_row_id"].to_numpy()
    fill_start, fill_end, fill_dt, fill_uncert = [np.full(n, np.nan) for _ in range(4)]
    fill_start[fill_previous] = np.roll(rows, 1)[fill_previous]
    fill_end[fill_previous] = rows[fill_previous]
    fill_dt[fill_previous] = dt[fill_previous]
    fill_uncert[fill_previous] = pos_uncertainty[fill_previous]
    fill_start[fill_next] = rows[fill_next]
    fill_end[fill_next] = np.roll(rows, -1)[fill_next]
    fill_dt[fill_next] = np.roll(dt, -1)[fill_next]
    fill_uncert[fill_next] = np.roll(pos_uncertainty, -1)[fill_next]

    delta = np.full(n, np.nan)
    delta[same] = (sog - np.roll(sog, 1))[same]
    speed_test = local_edge & np.isfinite(sog) & np.isfinite(np.roll(sog, 1))

    # SOG anlıktır; Haversine hızını iki bildirilen SOG'un ortalamasıyla,
    # yalnız kısa ve yaklaşık sabit hızlı aralıklarda karşılaştır.
    # Tahmini SOG'u bu ortalamaya katmak döngüsel bir doğrulama olurdu.
    compare_candidate = (speed_test & (dt <= cfg.compare_max_gap_s) &
                         (np.abs(delta) <= cfg.compare_stable_delta_kn))
    pair_mean, pair_error, pair_signed, pair_lower, pair_upper = [np.full(n, np.nan) for _ in range(5)]
    pair_mean[compare_candidate] = ((sog + np.roll(sog, 1)) / 2)[compare_candidate]
    pair_signed[compare_candidate] = (pair_mean - v_position)[compare_candidate]
    pair_error[compare_candidate] = np.abs(pair_signed[compare_candidate])
    lower, upper, compare_calibration = speed_difference_bounds(pair_signed[compare_candidate], cfg)
    compare_test = compare_candidate.copy()
    if lower is None:
        compare_test[:] = False
    else:
        pair_lower[compare_test], pair_upper[compare_test] = lower, upper
    # 1e-9 knot yalnız kayan nokta hesap yuvarlaması içindir; fiziksel tolerans değildir.
    compare_bad = compare_test & ((pair_signed < pair_lower - 1e-9) | (pair_signed > pair_upper + 1e-9))
    flags["bildirilen_hiz_konumla_tutarsiz"] = compare_bad | np.roll(compare_bad, -1)

    accel = np.full(n, np.nan)
    np.divide(np.abs(delta) * KNOT_MPS, dt, out=accel, where=speed_test)
    abrupt = speed_test & (np.abs(delta) >= cfg.jump_kn) & (accel > cfg.accel_mps2)
    speed_spike = (abrupt & np.roll(abrupt, -1) &
                   (delta * np.roll(delta, -1) < 0) &
                   (np.abs(np.roll(sog, -1) - np.roll(sog, 1)) <= cfg.return_tol_kn))
    if n:
        speed_spike[[0, -1]] = False
    flags["tekil_hiz_sicramasi_adayi"] = speed_spike
    unresolved_speed = abrupt & ~speed_spike & ~np.roll(speed_spike, 1)
    flags["ani_hiz_degisimi_iki_uc_supheli"] = unresolved_speed | np.roll(unresolved_speed, -1)

    for reason, mask in flags.items():
        ids = ix[mask]
        df.loc[ids, "qc_reason"] = df.loc[ids, "qc_reason"] + reason + ";"
    df["qc_reason"] = df["qc_reason"].str.rstrip(";")
    suspicious = df["qc_status"].eq("aday") & df["qc_reason"].ne("")
    df.loc[suspicious, "qc_status"] = "supheli"
    df.loc[df["qc_status"].eq("aday"), "qc_status"] = "temiz"

    metric_values = {
        "qc_prev_row_id": np.where(same, np.roll(w["qc_row_id"].to_numpy(), 1), np.nan),
        "qc_dt_s": dt, "qc_distance_m": d, "qc_position_speed_kn": v_position,
        "qc_calc_next_kn": np.roll(v_position, -1),
        "qc_position_uncertainty_kn": pos_uncertainty,
        "qc_fill_start_row_id": fill_start, "qc_fill_end_row_id": fill_end,
        "qc_fill_dt_s": fill_dt, "qc_fill_uncertainty_kn": fill_uncert,
        "qc_pair_sog_mean_kn": pair_mean, "qc_pair_speed_error_kn": pair_error,
        "qc_pair_signed_error_kn": pair_signed,
        "qc_pair_compare_lower_kn": pair_lower, "qc_pair_compare_upper_kn": pair_upper,
        "qc_delta_sog_kn": delta, "qc_abs_accel_mps2": accel,
        "qc_bridge_distance_m": bridge_d, "qc_bridge_dt_s": np.where(candidate, bridge_dt, np.nan),
    }
    for name, values in metric_values.items():
        df[name] = np.nan
        df.loc[ix, name] = values
    for reason, mask in flags.items():
        df["qc_" + reason] = False
        df.loc[ix, "qc_" + reason] = mask
    df["qc_continuity_checked"] = False
    df.loc[ix, "qc_continuity_checked"] = speed_test | np.roll(speed_test, -1)
    df["qc_pair_compare_tested"] = False
    df.loc[ix, "qc_pair_compare_tested"] = compare_test
    df["qc_speed_compare_checked"] = False
    df.loc[ix, "qc_speed_compare_checked"] = compare_test | np.roll(compare_test, -1)
    for mask, note in [(same & (dt > cfg.max_gap_s), "uzun_veri_boslugu"),
                       (same & (dt > 0) & (dt < cfg.min_dt_s), "ivme_icin_cok_kisa_aralik"),
                       (area_break, "marmara_disina_cikis_sonrasi_yeni_bolum")]:
        df.loc[ix[mask], "qc_note"] = note

    # Şüpheli/elenmiş noktaların ötesine otomatik doğru bağlantı varsayılmaz.
    # Segment kimliği temiz kayıtlara yazılır; MMSI sınırını asla aşmaz.
    accepted = df.loc[ix, "qc_status"].eq("temiz").to_numpy()
    trusted_edge = local_edge & accepted & np.roll(accepted, 1)
    segment_id = np.cumsum(~trusted_edge)
    df["qc_segment_id"] = pd.Series(pd.NA, index=df.index, dtype="Int64")
    df.loc[ix[accepted], "qc_segment_id"] = segment_id[accepted]

    # Coğrafi kesintiler yukarıda belirlenmiştir. Şimdi bölge dışı satırları
    # bütün çıktı tablolarından ve fonksiyonun dönüş değerinden tamamen çıkar.
    # Daha önce başka nedenle elenmiş sınır dışı satırlar da burada silinir.
    outside_mask = coordinate_valid & ~inside_marmara
    outside_removed = int(outside_mask.sum())
    df = df.loc[~outside_mask].copy()
    status_counts = {s: int(df["qc_status"].eq(s).sum()) for s in ["temiz", "elendi", "supheli"]}
    summary = {
        "girdi_kayit": len(raw), "sonuc": status_counts,
        "marmara_disi_silinen": outside_removed,
        "ciktilardaki_toplam_kayit": len(df),
        "asama_sonu_kalan": stages,
        "eleme_nedenleri": {str(k): int(v) for k, v in df.loc[df["qc_status"].eq("elendi"), "qc_reason"].value_counts().items()},
        "suphe_nedenleri_ayni_kayit_birden_fazla_olabilir": {k: int(v.sum()) for k, v in flags.items()},
        "sifir_knot_korunan_temiz": int((df["qc_status"].eq("temiz") & df["qc_sog_kn"].eq(0)).sum()),
        "eksik_hiz_girdi": int(missing.sum()),
        "marmara_sinirlari_disinda_konumu_olan": outside_removed,
        "marmara_filtresiyle_elenen": outside_removed,
        "marmara_calisma_alani": {
            "yontem": "dikdortgen_bounding_box", "sinir_kaynagi": "kullanicinin_kabul_ettigi_koordinatlar",
            "sinirlar_dahil": True, "ondalik_derece": MARMARA_BOUNDS,
            "kiyi_poligonu_veya_kara_maskesi_uygulanir": False,
            "bolge_disi_kayitlar_ciktiya_yazilir": False,
        },
        "konumdan_tamamlanan_hiz": int(df["qc_speed_is_imputed"].sum()),
        "tamamlanan_temiz_kayit": int((df["qc_speed_is_imputed"] & df["qc_status"].eq("temiz")).sum()),
        "hiz_kaynaklari": {str(k): int(v) for k, v in df["qc_speed_source"].value_counts().items()},
        "bildirilen_hiz_karsilastirilan_aralik": int(compare_test.sum()),
        "bildirilen_hiz_karsilastirma_supheli_aralik": int(compare_bad.sum()),
        "hiz_farki_esikleri": compare_calibration,
        "yerel_sureklilik_testi_yapilamayan_temiz": int((df["qc_status"].eq("temiz") & ~df["qc_continuity_checked"]).sum()),
        "ayarlar": asdict(cfg), "sutunlar": columns, "kaynaklar": SOURCES,
        "mesafe_yontemi": "Haversine", "dunya_yaricapi_m": EARTH_RADIUS_M,
        "hiz_formulu": "(mesafe_m/1852) / (zaman_farki_s/3600)",
        "aciklama": [
            "Marmara dışındaki kayıtlar hız türetme ve kalibrasyona alınmaz; çıktı DataFrame'inden ve bütün CSV dosyalarından silinir. Sınırlar dahildir.",
            "Bölge dışına çıkıp dönen MMSI kayıtları arasında bağlantı kurulmaz; yeni bölüm başlar.",
            "Hız üst eşiği '>' ile uygulanır; tam eşik korunur.",
            "Süreksizlikler kesin hata kabul edilmez; supheli_ais.csv'ye ayrılır.",
            "50 knot kullanıcı kararıdır; diğer sayısal toleranslar kalibrasyon gerektiren başlangıç değerleridir.",
            "Makaledeki ilk filtre SOG<50'dir; bu betik tam 50'yi koruyan kullanıcı kararını uygular.",
            "SOG anlık, konumdan hız ortalama yer değiştirmedir; aralarındaki fark şüphe nedenidir, kesin hata kanıtı değildir.",
            "Hız farkı eşiği alpha-yönteminden uyarlanmıştır; varsayılan merkez %95 sınırları aynı dosyanın uygun aralıklarından öğrenilir.",
            "Gemi boyu sınıflaması kullanılmadığından yöntem makalenin basitleştirilmiş uyarlamasıdır, tam tekrarı değildir.",
            "Kuyruklarda kalmak kesin hata demek değildir; genel sistematik hatalar bu yöntemle kaçabilir.",
            "Boş/NaN/1023 hızlar uygun bitişik aralıktan tahmin edilir; koordinatlar ve eksik zaman kayıtları doldurulmaz.",
            "Bildirilmiş hızlar değiştirilmez; bağımsız karşılaştırmada tahmin edilmiş SOG kullanılmaz.",
            "Gelecekteki kaydı kullanan calculated_next tahmini çevrimdışıdır; canlı kullanımda fill_direction=previous seçin.",
            "Uzun boşluklar ve çok kısa aralıklar ivme/eksik hız tamamlama testinde kullanılmaz.",
            "Metrikler şüpheli kayıtları ayırmadan önce hesaplanır; qc_prev_row_id önceki kaydı gösterir.",
        ],
    }
    assert sum(status_counts.values()) == len(df)
    assert len(df) + outside_removed == len(raw)
    return df, summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", type=Path, help="CSV girdi yolu")
    parser.add_argument("--out", type=Path, default=Path("ais_sonuc"))
    for field in ALIASES:
        parser.add_argument("--" + field, help=field + " sütununun tam adı")
    parser.add_argument("--sog-unit", choices=["knot", "kmh", "raw10"], default="knot")
    parser.add_argument("--time-unit", choices=["iso", "s", "ms"], default="iso")
    parser.add_argument("--time-format", default=None)
    parser.add_argument("--fill-direction", choices=["previous", "previous_or_next"], default="previous_or_next")
    parser.add_argument("--sep", default=",", help="CSV ayıracı; varsayılan virgül")
    parser.add_argument("--decimal", choices=[".", ","], default=".")
    parser.add_argument("--encoding", default="utf-8-sig")
    parser.add_argument("--compare-lower-kn", type=float, default=None)
    parser.add_argument("--compare-upper-kn", type=float, default=None)
    for name, default in [("max-speed-kn", 50), ("pos-tol-m", 100), ("min-dt-s", 2),
                          ("max-gap-s", 600), ("jump-kn", 8), ("accel-mps2", 0.1), ("return-tol-kn", 3),
                          ("max-fill-uncertainty-kn", 5), ("compare-alpha", 0.05),
                          ("compare-max-gap-s", 120), ("compare-stable-delta-kn", 3)]:
        parser.add_argument("--" + name, type=float, default=default)
    args = parser.parse_args(argv)
    try:
        # Tüm özgün hücreleri metin okuyarak MMSI ve ham değerleri koru.
        raw = pd.read_csv(args.input, dtype="string", keep_default_na=False, sep=args.sep, encoding=args.encoding)
        columns = resolve_columns(raw, {k: getattr(args, k) for k in ALIASES})
        cfg = Config(**{k: getattr(args, k) for k in Config.__dataclass_fields__})
        audited, summary = clean_ais(raw, columns, cfg)
        args.out.mkdir(parents=True, exist_ok=True)
        names = {"temiz": "temiz_ais.csv", "elendi": "elenen_ais.csv", "supheli": "supheli_ais.csv"}
        targets = [args.out / n for n in [*names.values(), "tum_kayitlar.csv", "kalite_ozeti.json"]]
        if args.input.resolve() in [p.resolve() for p in targets]:
            raise ValueError("Çıktı girdinin üzerine yazacak; farklı --out dizini seçin.")
        # Önceki bir çalışmanın sonuçlarını yanlışlıkla ezme.
        if any(p.exists() for p in targets):
            raise ValueError("Bu çıktı dizininde sonuç dosyaları zaten var; yeni --out dizini seçin.")
        sort_keys = ["qc_mmsi", "qc_time_utc", "qc_row_id"]
        for status, name in names.items():
            result = audited.loc[audited["qc_status"].eq(status)].sort_values(sort_keys, kind="stable")
            result.to_csv(args.out / name, index=False, encoding="utf-8-sig")
        audited.to_csv(args.out / "tum_kayitlar.csv", index=False, encoding="utf-8-sig")
        summary["girdi_dosyasi"] = str(args.input)
        (args.out / "kalite_ozeti.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"girdi": len(raw), **summary["sonuc"],
                          "marmara_disi_silinen": summary["marmara_disi_silinen"],
                          "ciktilardaki_toplam_kayit": summary["ciktilardaki_toplam_kayit"],
                          "hiz_farki_esikleri": summary["hiz_farki_esikleri"],
                          "cikti": str(args.out.resolve())}, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, pd.errors.ParserError) as exc:
        print(f"Hata: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
