# -*- coding: utf-8 -*-
"""
Astrolojik hesaplamalar için Swisseph kütüphanesini kullanan modül.
Tecrübeli bir yazılım mühendisi ve astroloji uzmanı tarafından gözden
geçirilmiş ve güncellenmiştir.
"""

import os
import math
import logging
import json
from datetime import datetime, timedelta, date, time
from decimal import Decimal, ROUND_DOWN
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, Union, TypedDict, BinaryIO

import swisseph as swe
from flask import jsonify, Blueprint, render_template, current_app
from exceptions import (
    AstroError,
    CalculationError,
    ValidationError,
    InvalidDateError,
    InvalidTimeError,
    InvalidCoordinatesError,
    HouseCalculationError,
    EphemerisError,
)


class AstroService:
    @staticmethod
    def calculate(birth_date, birth_time, latitude, longitude, **kwargs):
        """Perform full astrological calculation."""
        return calculate_astro_data(
            birth_date, birth_time, latitude, longitude, **kwargs
        )


class ImportantAngles(TypedDict):
    ascendant: float
    mc: float
    armc: float
    vertex: float


class HouseData(TypedDict):
    house_cusps: Dict[str, float]
    important_angles: ImportantAngles
    house_system: str
    error: Optional[str]


class PlanetPosition(TypedDict):
    degree: float
    sign: str
    retrograde: bool
    house: int
    speed: float
    latitude: float
    distance: float
    degree_in_sign: float
    decan: int
    error: Optional[str]


astro = Blueprint("astro", __name__, template_folder="templates")

RESET = "\033[0m"
BOLD = "\033[1m"

COLOR_LIST = [
    "\033[93m",  # sarı
    "\033[92m",  # yeşil
    "\033[96m",  # cyan
    "\033[95m",  # mor
    "\033[94m",  # mavi
]


def julday_to_datetime(
    jd_ut: float, timezone_offset: float = 3.0
) -> Optional[datetime]:
    """
    Julian günü datetime objesine çevirir.

    Args:
        jd_ut: Julian günü (UT)
        timezone_offset: Yerel saate dönüştürmek için eklenecek saat (default UTC+3)

    Returns:
        Optional[datetime]: Yerel datetime objesi veya hata durumunda None
    """
    try:
        # Julian günü UT'den yerel zamana çevir
        jd_local = jd_ut + timezone_offset / 24.0

        # Decimal kullanarak hassas hesaplama yap
        day_frac = Decimal(str(jd_local % 1))
        hour = int((day_frac * 24).quantize(Decimal("1."), rounding=ROUND_DOWN))
        minute = int(
            ((day_frac * 24 - hour) * 60).quantize(Decimal("1."), rounding=ROUND_DOWN)
        )
        second = int(
            ((day_frac * 24 * 60 - hour * 60 - minute) * 60).quantize(
                Decimal("1."), rounding=ROUND_DOWN
            )
        )

        # swe.revjul fonksiyonu ile tarihi al (yıl, ay, gün)
        year, month, day, _ = swe.revjul(jd_local)

        return datetime(year, month, day, hour, minute, second)
    except Exception as e:
        logger.error(f"julday_to_datetime fonksiyonunda hata: {str(e)}", exc_info=True)
        return None


def get_julian_day(dt: datetime, timezone_offset: float = 3.0) -> float:
    """
    Verilen datetime ve timezone offset için Julian Day (UT) hesaplar.

    Args:
        dt: Datetime objesi
        timezone_offset: UTC'ye ulaşmak için çıkarılacak saat (default 3.0)

    Returns:
        float: Julian Day (UT)
    """
    utc_dt = dt - timedelta(hours=timezone_offset)
    return swe.julday(
        utc_dt.year,
        utc_dt.month,
        utc_dt.day,
        utc_dt.hour + utc_dt.minute / 60.0 + utc_dt.second / 3600.0,
    )


# Logging ayarları
# Daha detaylı log için level=logging.DEBUG yapabilirsiniz.
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

import requests  # Uzak dosyaları indirmek için

# Swiss Ephemeris ayarları — ephe dosyaları image'a bake edildi (services/ephe/)
# Runtime indirme kaldırıldı (erkanerdem.net kapandı, astro.com olmamıştı, vb.)
SWISSEPH_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ephe")

# Klasörü oluştur (mevcutsa atla)
if not os.path.exists(SWISSEPH_DATA_DIR):
    os.makedirs(SWISSEPH_DATA_DIR, exist_ok=True)

# Temel efemeris dosyaları hazır mı kontrol et
core_files = ["sepl_00.se1", "semo_00.se1", "seas_00.se1"]
for cf in core_files:
    if not os.path.exists(os.path.join(SWISSEPH_DATA_DIR, cf)):
        logger.warning(f"Efemeris dosyası eksik: {cf}")

swe.set_ephe_path(SWISSEPH_DATA_DIR)
logger.info(f"Swiss Ephemeris veri yolu ayarlandı: {SWISSEPH_DATA_DIR}")


def convert_house_data_to_strings(data):
    """Ev verilerini, özellikle cusp listesini string anahtarlı dictionary'ye dönüştürür."""
    if isinstance(data, (list, tuple)):
        # Liste formatını {1: degree, 2: degree, ...} formatına çevir
        return {str(i + 1): round(float(v), 2) for i, v in enumerate(data)}
    elif isinstance(data, dict):
        # Dictionary içinde nested liste/tuple/dict varsa onları da çevir
        return {
            str(k): convert_house_data_to_strings(v)
            if isinstance(v, (list, tuple, dict))
            else v
            for k, v in data.items()
        }
    return data


def get_zodiac_sign(degree):
    """Dereceye göre burcu döndürür."""
    zodiac_signs = [
        "Koç",
        "Boğa",
        "İkizler",
        "Yengeç",
        "Aslan",
        "Başak",
        "Terazi",
        "Akrep",
        "Yay",
        "Oğlak",
        "Kova",
        "Balık",
    ]
    normalized_degree = degree % 360
    if normalized_degree < 0:
        normalized_degree += 360
    sign_index = int(normalized_degree // 30)
    # logger.debug(f"{degree:.2f} derece burcu: {zodiac_signs[sign_index]}")
    return zodiac_signs[sign_index]


def get_degree_in_sign(degree):
    """Derecenin burç içindeki derecesini döndürür."""
    normalized_degree = degree % 360
    if normalized_degree < 0:
        normalized_degree += 360
    return normalized_degree % 30


def get_decan(degree_in_sign):
    """Burç içindeki dereceye göre dekanı döndürür."""
    return int(degree_in_sign // 10) + 1


def get_house_number(longitude: float, house_cusps: Dict[str, float]) -> int:
    """
    Bir boylamın (longitude) hangi evde olduğunu belirler.

    Args:
        longitude: Boylam (0-360)
        house_cusps: Ev cusp'ları { '1': degree, ... '12': degree }

    Returns:
        int: Ev numarası (1-12)
    """
    lon = longitude % 360

    try:
        cusps = [float(house_cusps[str(i + 1)]) % 360 for i in range(12)]
    except (KeyError, ValueError, TypeError):
        return 1  # Fallback to 1st house if data is missing

    for i in range(12):
        current_cusp = cusps[i]
        next_cusp = cusps[(i + 1) % 12]

        if current_cusp < next_cusp:
            if current_cusp <= lon < next_cusp:
                return i + 1
        else:  # Wrap-around durumu
            if lon >= current_cusp or lon < next_cusp:
                return i + 1

    return 1


def calculate_houses(
    dt_object: datetime,
    latitude: float,
    longitude: float,
    house_system: Union[bytes, str] = b"P",
    jd_ut: Optional[float] = None,
    timezone_offset: float = 3.0,
) -> HouseData:
    """
    Doğum tarihi, saati ve konuma göre evleri hesaplar.

    Args:
        dt_object: Datetime objesi
        latitude: Enlem
        longitude: Boylam
        house_system: Ev sistemi kodu (örn. b"P" Placidus)
        jd_ut: Önceden hesaplanmış Julian Day (opsiyonel)
        timezone_offset: Zaman dilimi farkı

    Returns:
        HouseData: Ev verilerini içeren TypedDict
    """
    try:
        # Eğer jd_ut verilmemişse hesapla
        if jd_ut is None:
            jd_ut = get_julian_day(dt_object, timezone_offset)

        # Byte formatına çevir
        h_sys = (
            house_system
            if isinstance(house_system, bytes)
            else house_system.encode("utf-8")
        )

        # houses_ex daha detaylı bilgi verir
        cusps, ascmc = swe.houses_ex(jd_ut, float(latitude), float(longitude), h_sys)

        house_cusps_list = [c % 360 for c in list(cusps)[:12]]
        house_cusps = {str(i + 1): round(house_cusps_list[i], 2) for i in range(12)}

        ascmc_list = [a % 360 for a in list(ascmc)[:4]]
        important_angles: ImportantAngles = {
            "ascendant": round(ascmc_list[0], 2),
            "mc": round(ascmc_list[1], 2),
            "armc": round(ascmc_list[2], 2),
            "vertex": round(ascmc_list[3], 2),
        }

        return {
            "house_cusps": house_cusps,
            "important_angles": important_angles,
            "house_system": h_sys.decode("utf-8"),
            "error": None,
        }

    except Exception as e:
        logger.error(f"calculate_houses hatası: {str(e)}")
        return {
            "house_cusps": {str(i + 1): 0.0 for i in range(12)},
            "important_angles": {
                "ascendant": 0.0,
                "mc": 0.0,
                "armc": 0.0,
                "vertex": 0.0,
            },
            "house_system": "P",
            "error": str(e),
        }


def calculate_celestial_positions(
    dt_object: datetime,
    house_cusps: Dict[str, float],
    celestial_bodies_ids: Dict[str, int],
    jd_ut: Optional[float] = None,
    timezone_offset: float = 3.0,
) -> Dict[str, PlanetPosition]:
    """
    Gezegen pozisyonlarını hesaplar.

    Args:
        dt_object: Datetime objesi
        house_cusps: Ev cusp'ları
        celestial_bodies_ids: Gezegen ID'leri
        jd_ut: Önceden hesaplanmış Julian Day (opsiyonel)
        timezone_offset: Zaman dilimi farkı

    Returns:
        Dict[str, PlanetPosition]: Gezegen verileri
    """
    try:
        if jd_ut is None:
            jd_ut = get_julian_day(dt_object, timezone_offset)

        positions = {}
        for name, planet_id in celestial_bodies_ids.items():
            try:
                if planet_id == 17:  # Vulkanus skip
                    continue

                pos_result = swe.calc_ut(
                    jd_ut, planet_id, swe.FLG_SWIEPH | swe.FLG_SPEED
                )

                if not pos_result:
                    positions[name] = {
                        "degree": 0.0,
                        "sign": "Bilinmiyor",
                        "retrograde": False,
                        "house": 0,
                        "speed": 0.0,
                        "latitude": 0.0,
                        "distance": 0.0,
                        "degree_in_sign": 0.0,
                        "decan": 1,
                        "error": "Hesaplama hatası",
                    }
                    continue

                pos = pos_result[0]
                lon = pos[0]
                lat = pos[1]
                dist = pos[2]
                speed = pos[3]

                is_retrograde = speed < 0

                # Ev belirleme
                house_num = get_house_number(lon, house_cusps)

                positions[name] = {
                    "degree": round(lon % 360, 4),
                    "sign": get_zodiac_sign(lon),
                    "retrograde": is_retrograde,
                    "house": house_num,
                    "speed": round(speed, 4),
                    "latitude": round(lat, 4),
                    "distance": round(dist, 4),
                    "degree_in_sign": round(get_degree_in_sign(lon), 2),
                    "decan": get_decan(get_degree_in_sign(lon)),
                    "error": None,
                }

            except Exception as inner_e:
                logger.error(f"{name} hesaplanırken hata: {str(inner_e)}")
                positions[name] = {
                    "degree": 0.0,
                    "sign": "Bilinmiyor",
                    "retrograde": False,
                    "house": 0,
                    "speed": 0.0,
                    "latitude": 0.0,
                    "distance": 0.0,
                    "degree_in_sign": 0.0,
                    "decan": 1,
                    "error": str(inner_e),
                }

        return positions

    except Exception as e:
        logger.error(f"calculate_celestial_positions hatası: {str(e)}")
        return {}


# Natal Gezegen Pozisyonları
def calculate_natal_planet_positions(
    birth_dt: datetime,
    natal_house_cusps: Dict[str, float],
    jd_ut: Optional[float] = None,
    timezone_offset: float = 3.0,
) -> Dict[str, PlanetPosition]:
    """Natal gezegen pozisyonlarını hesaplar."""
    planet_ids = {
        "Sun": swe.SUN,
        "Moon": swe.MOON,
        "Mercury": swe.MERCURY,
        "Venus": swe.VENUS,
        "Mars": swe.MARS,
        "Jupiter": swe.JUPITER,
        "Saturn": swe.SATURN,
        "Uranus": swe.URANUS,
        "Neptune": swe.NEPTUNE,
        "Pluto": swe.PLUTO,
    }
    logger.info("Natal gezegen pozisyonları hesaplanıyor...")
    return calculate_celestial_positions(
        birth_dt, natal_house_cusps, planet_ids, jd_ut, timezone_offset
    )


# Natal Ekstra Noktalar Pozisyonları
def calculate_natal_additional_points(
    birth_dt: datetime,
    natal_house_cusps: Dict[str, float],
    jd_ut: Optional[float] = None,
    timezone_offset: float = 3.0,
) -> Dict[str, PlanetPosition]:
    """Natal ekstra noktaların pozisyonlarını hesaplar."""
    point_ids = {
        "Chiron": swe.CHIRON,
        "Ceres": swe.CERES,
        "Pallas": swe.PALLAS,
        "Juno": swe.JUNO,
        "Vesta": swe.VESTA,
        "Mean_Node": swe.MEAN_NODE,
        "True_Node": swe.TRUE_NODE,
        "Mean_Lilith": swe.MEAN_APOG,
        "True_Lilith": swe.OSCU_APOG,
        "Cupido": swe.CUPIDO,
        "Hades": swe.HADES,
        "Zeus": swe.ZEUS,
        "Kronos": swe.KRONOS,
        "Apollon": swe.APOLLON,
        "Admetos": swe.ADMETOS,
        "Vulkanus": swe.VULKANUS,
        "Poseidon": swe.POSEIDON,
    }
    logger.info("Natal ekstra noktalar pozisyonları hesaplanıyor...")
    return calculate_celestial_positions(
        birth_dt, natal_house_cusps, point_ids, jd_ut, timezone_offset
    )


# Natal veya transit-natal açı hesaplamaları
def calculate_aspects(positions1, positions2=None, orb=None):
    """İki set pozisyon arasındaki (natal-natal veya transit-natal) açıları hesaplar.

    Args:
        positions1 (dict): Gezegen/nokta pozisyonları dict'i (örn. natal pozisyonlar)
        positions2 (dict, optional): İki set pozisyonları (örn. transit pozisyonları).
                                     None ise positions1 kendi içinde kıyaslanır (natal-natal).
        orb (dict, optional): Açı tipleri için özel orb değerleri (örn. {"Conjunction": 8, ...}).
                              Yoksa varsayılanlar kullanılır.

    Returns:
        list: Bulunan açıların listesi [{planet1, planet2, aspect_type, orb}, ...]
    """
    try:
        # Varsayılan orb değerleri (daha esnek olabilir veya yapılandırılabilir)
        default_orbs = {
            "Conjunction": 8.0,
            "Opposition": 8.0,
            "Trine": 8.0,
            "Square": 8.0,
            "Sextile": 6.0,
        }
        orbs_to_use = orb if isinstance(orb, dict) else default_orbs

        aspects_list = []
        # Sadece 'degree' anahtarı olan geçerli pozisyonları al
        valid_positions1 = {
            k: v for k, v in positions1.items() if isinstance(v, dict) and "degree" in v
        }
        valid_positions2 = {
            k: v
            for k, v in (
                positions2.items() if positions2 is not None else positions1.items()
            )
            if isinstance(v, dict) and "degree" in v
        }

        planets1_keys = list(valid_positions1.keys())
        planets2_keys = list(valid_positions2.keys())

        # Açı dereceleri
        aspect_degrees = {
            "Conjunction": 0.0,
            "Sextile": 60.0,
            "Square": 90.0,
            "Trine": 120.0,
            "Opposition": 180.0,
        }

        for p1_key in planets1_keys:
            deg1 = valid_positions1[p1_key]["degree"] % 360  # Normalize

            for p2_key in planets2_keys:
                deg2 = valid_positions2[p2_key]["degree"] % 360  # Normalize

                # Natal-natal kıyaslama yapılıyorsa aynı gezegeni veya çiftleri atla (Sun-Moon vs Moon-Sun)
                if positions2 is None and p1_key >= p2_key:
                    continue

                # Açı farkını hesapla (0-180 derece aralığında)
                diff = abs(deg1 - deg2)
                aspect_diff = min(diff, 360 - diff)  # En kısa yay

                found_aspect = None
                min_orb = float("inf")

                for aspect_name, ideal_degree in aspect_degrees.items():
                    current_orb_limit = orbs_to_use.get(
                        aspect_name, 0.0
                    )  # Orb limitini al
                    if current_orb_limit <= 0:
                        continue  # Orb 0 veya negatifse bu açıyı kontrol etme

                    # Açı farkını ideal dereceye göre orb içinde mi kontrol et
                    # Farklı açı tipleri için farklı kontrol yöntemleri olabilir, özellikle 0/180 çevresi
                    orb_value = abs(aspect_diff - ideal_degree)

                    # Kavuşum (0) ve Karşıt (180) özel kontrolü (0-360 farkı üzerinden)
                    if aspect_name == "Conjunction":
                        orb_value = min(
                            abs(deg1 - deg2), 360 - abs(deg1 - deg2)
                        )  # 0'a yakınlık
                    elif aspect_name == "Opposition":
                        orb_value = min(
                            abs(deg1 - deg2 - 180) % 360, abs(deg1 - deg2 + 180) % 360
                        )  # 180'e yakınlık

                    if orb_value <= current_orb_limit:
                        # Birden fazla orb içinde olabilir, en küçüğünü al (hassas açı)
                        if orb_value < min_orb:
                            min_orb = orb_value
                            found_aspect = {
                                "planet1": p1_key,
                                "planet2": p2_key,
                                "aspect_type": aspect_name,
                                "orb": round(orb_value, 2),
                                "exact_difference_0_180": round(
                                    aspect_diff, 2
                                ),  # 0-180 fark
                            }

                if found_aspect:
                    aspects_list.append(found_aspect)

        # Orb'a göre sırala
        aspects_list = sorted(aspects_list, key=lambda x: x["orb"])

        logger.info(f"Hesaplanan açı sayısı: {len(aspects_list)}")
        # logger.debug(f"Hesaplanan açılar: {aspects_list}")
        return aspects_list

    except Exception as e:
        logger.error(f"calculate_aspects fonksiyonunda hata: {str(e)}", exc_info=True)
        return []  # Hata durumunda boş liste döndür


# Burcun elementini belirleyen fonksiyon
def get_element(sign):
    """Burcun elementini döndürür."""
    elements = {
        "Koç": "Ateş",
        "Aslan": "Ateş",
        "Yay": "Ateş",
        "Boğa": "Toprak",
        "Başak": "Toprak",
        "Oğlak": "Toprak",
        "İkizler": "Hava",
        "Terazi": "Hava",
        "Kova": "Hava",
        "Yengeç": "Su",
        "Akrep": "Su",
        "Balık": "Su",
    }
    return elements.get(sign, "Bilinmiyor")


# Burcun niteliğini belirleyen fonksiyon (Kardinal, Sabit, Değişken)
def get_modality(sign):
    """Burcun niteliğini (Kardinal, Sabit, Değişken) döndürür."""
    modalities = {
        "Koç": "Kardinal",
        "Yengeç": "Kardinal",
        "Terazi": "Kardinal",
        "Oğlak": "Kardinal",
        "Boğa": "Sabit",
        "Aslan": "Sabit",
        "Akrep": "Sabit",
        "Kova": "Sabit",
        "İkizler": "Değişken",
        "Başak": "Değişken",
        "Yay": "Değişken",
        "Balık": "Değişken",
    }
    return modalities.get(sign, "Bilinmiyor")


# Burcun polaritesini belirleyen fonksiyon (Erkek/Pozitif, Dişi/Negatif)
def get_polarity(sign):
    """Burcun polaritesini (Erkek/Dişi) döndürür."""
    polarities = {
        "Koç": "Erkek",
        "İkizler": "Erkek",
        "Aslan": "Erkek",
        "Terazi": "Erkek",
        "Yay": "Erkek",
        "Kova": "Erkek",
        "Boğa": "Dişi",
        "Yengeç": "Dişi",
        "Başak": "Dişi",
        "Akrep": "Dişi",
        "Oğlak": "Dişi",
        "Balık": "Dişi",
    }
    return polarities.get(sign, "Bilinmiyor")


# Natal harita özet yorumunun oluşturulması (Basit versiyon)
def get_natal_summary(natal_planet_positions, natal_houses_data, birth_dt):
    """Natal harita için özet bir yorum metni listesi oluşturur."""
    try:
        interpretations = []

        # Ascendant bilgisi (important_angles içinde olması beklenir)
        # Hata durumunda None gelirse kontrol edelim
        ascendant_deg = natal_houses_data.get("important_angles", {}).get("ascendant")
        if ascendant_deg is not None:
            ascendant_sign = get_zodiac_sign(ascendant_deg)
            ascendant_deg_in_sign = get_degree_in_sign(ascendant_deg)
            ascendant_decan = get_decan(ascendant_deg_in_sign)
            interpretations.append(
                f"Yükselen: {ascendant_sign} {ascendant_deg_in_sign:.2f}° ({ascendant_decan}. dekan)"
            )
        else:
            interpretations.append("Yükselen burç hesaplanamadı.")

        # Güneş ve Ay bilgisi
        sun_pos = natal_planet_positions.get("Sun")
        moon_pos = natal_planet_positions.get("Moon")
        if sun_pos and moon_pos and "sign" in sun_pos and "sign" in moon_pos:
            sun_sign = sun_pos["sign"]
            moon_sign = moon_pos["sign"]
            sun_house = sun_pos.get("house", "Bilinmiyor")
            moon_house = moon_pos.get("house", "Bilinmiyor")
            interpretations.append(
                f"Güneş ({sun_sign} - {sun_house}. ev) ve Ay ({moon_sign} - {moon_house}. ev) pozisyonları temel karakterinizi ve duygusal ihtiyaçlarınızı gösterir."
            )
            interpretations.append(f"Güneş-Ay kombinasyonu: {sun_sign} / {moon_sign}.")
        else:
            interpretations.append("Güneş veya Ay pozisyonu hesaplanamadı.")

        # Element ve Nitelik dağılımı
        elements = {"Ateş": 0, "Toprak": 0, "Hava": 0, "Su": 0}
        modalities = {"Kardinal": 0, "Sabit": 0, "Değişken": 0}
        polarities = {"Erkek": 0, "Dişi": 0}

        # Ana gezegenleri kullanarak dağılımı hesapla (Uranüs, Neptün, Plüton da dahil edilebilir isteğe bağlı)
        planets_for_distribution = [
            "Sun",
            "Moon",
            "Mercury",
            "Venus",
            "Mars",
            "Jupiter",
            "Saturn",
            "Uranus",
            "Neptune",
            "Pluto",
        ]  # Tüm gezegenleri dahil edelim

        for planet in planets_for_distribution:
            if (
                planet in natal_planet_positions
                and "sign" in natal_planet_positions[planet]
            ):
                sign = natal_planet_positions[planet]["sign"]
                elements[get_element(sign)] += 1
                modalities[get_modality(sign)] += 1
                polarities[get_polarity(sign)] += 1

        # Baskın element/nitelik/polarite kontrolü (en az bir gezegen olmalı)
        dominant_element = (
            max(elements.items(), key=lambda x: x[1])
            if any(elements.values())
            else ("Bilinmiyor", 0)
        )
        dominant_modality = (
            max(modalities.items(), key=lambda x: x[1])
            if any(modalities.values())
            else ("Bilinmiyor", 0)
        )
        dominant_polarity = (
            max(polarities.items(), key=lambda x: x[1])
            if any(polarities.values())
            else ("Bilinmiyor", 0)
        )

        if dominant_element[1] > 0:
            interpretations.append(
                f"Baskın Element: {dominant_element[0]} ({dominant_element[1]} gezegen)."
            )
        interpretations.append(
            f"Element Dağılımı: Ateş: {elements['Ateş']}, Toprak: {elements['Toprak']}, Hava: {elements['Hava']}, Su: {elements['Su']}."
        )
        if dominant_modality[1] > 0:
            interpretations.append(
                f"Baskın Nitelik: {dominant_modality[0]} ({dominant_modality[1]} gezegen)."
            )
        interpretations.append(
            f"Nitelik Dağılımı: Kardinal: {modalities['Kardinal']}, Sabit: {modalities['Sabit']}, Değişken: {modalities['Değişken']}."
        )
        if dominant_polarity[1] > 0:
            interpretations.append(
                f"Baskın Polarite: {dominant_polarity[0]} ({dominant_polarity[1]} gezegen)."
            )

        # Retrograd gezegenler
        retrogrades = [
            planet
            for planet, details in natal_planet_positions.items()
            if details.get("retrograde", False)
            is True  # retrograde key'i varsa ve True ise
        ]
        if retrogrades:
            interpretations.append(f"Retrograd gezegenler: {', '.join(retrogrades)}.")
        # else: # Retrograd gezegen olmaması da bir bilgidir, ama yorumu uzatmamak için sadece varsa ekleyelim.
        #    interpretations.append("Natal haritada retrograd gezegen yok.")

        # Evlerdeki gezegen yoğunluğu
        houses_dict = {i: [] for i in range(1, 13)}
        # Hem gezegenleri hem de ek noktaları evlere dağıtalım
        all_natal_celestial_bodies = {}
        all_natal_celestial_bodies.update(natal_planet_positions)
        # Uranian gezegenleri hariç diğer ek noktaları dahil edelim (Çok fazla uranian evi kalabalıklaştırabilir)
        points_to_include_in_houses = [
            "Chiron",
            "Ceres",
            "Pallas",
            "Juno",
            "Vesta",
            "True_Node",
            "Mean_Node",
            "True_Lilith",
            "Mean_Lilith",
        ]

        natal_additional_points = calculate_natal_additional_points(
            birth_dt, natal_houses_data["house_cusps"]
        )
        # Ek noktaları da dahil et
        # Ek noktaları natal_planet_positions ile birleştiriyoruz

        for point_name in points_to_include_in_houses:
            if point_name in natal_additional_points:
                all_natal_celestial_bodies[point_name] = natal_additional_points[
                    point_name
                ]

        for body_name, details in all_natal_celestial_bodies.items():
            if (
                "house" in details
                and isinstance(details["house"], int)
                and 1 <= details["house"] <= 12
            ):
                houses_dict[details["house"]].append(body_name)

        populated_houses = {house: p for house, p in houses_dict.items() if p}
        for house in sorted(populated_houses.keys()):
            interpretations.append(
                f"{house}. Ev: {', '.join(populated_houses[house])}."
            )

        logger.info("Natal özet yorum oluşturuldu.")
        # logger.debug(f"Natal yorum: {interpretations}")
        return interpretations

    except Exception as e:
        logger.error(f"Natal özet yorum oluşturma hatası: {str(e)}", exc_info=True)
        return ["Yorum oluşturulurken bir hata oluştu."]


# ==========================================
# VİMSHOTTARİ DASA SİSTEMİ - TAM İMPLEMENTASYON
# ==========================================
# 120 yıllık Vedik astroloji döngü sistemi
# Maha Dasa -> Antardasa (Bhukti) -> Pratyantardasa (3. seviye)

# Nakshatra Verileri (27 Nakshatra)
NAKSHATRAS = [
    {
        "index": 0,
        "name": "Ashwini",
        "name_tr": "Aşvini",
        "lord": "Ketu",
        "start": 0.0,
        "end": 13.333333,
    },
    {
        "index": 1,
        "name": "Bharani",
        "name_tr": "Bharani",
        "lord": "Venus",
        "start": 13.333333,
        "end": 26.666667,
    },
    {
        "index": 2,
        "name": "Krittika",
        "name_tr": "Krittika",
        "lord": "Sun",
        "start": 26.666667,
        "end": 40.0,
    },
    {
        "index": 3,
        "name": "Rohini",
        "name_tr": "Rohini",
        "lord": "Moon",
        "start": 40.0,
        "end": 53.333333,
    },
    {
        "index": 4,
        "name": "Mrigashira",
        "name_tr": "Mrigaşira",
        "lord": "Mars",
        "start": 53.333333,
        "end": 66.666667,
    },
    {
        "index": 5,
        "name": "Ardra",
        "name_tr": "Ardra",
        "lord": "Rahu",
        "start": 66.666667,
        "end": 80.0,
    },
    {
        "index": 6,
        "name": "Punarvasu",
        "name_tr": "Punarvasu",
        "lord": "Jupiter",
        "start": 80.0,
        "end": 93.333333,
    },
    {
        "index": 7,
        "name": "Pushya",
        "name_tr": "Puşya",
        "lord": "Saturn",
        "start": 93.333333,
        "end": 106.666667,
    },
    {
        "index": 8,
        "name": "Ashlesha",
        "name_tr": "Aşleşa",
        "lord": "Mercury",
        "start": 106.666667,
        "end": 120.0,
    },
    {
        "index": 9,
        "name": "Magha",
        "name_tr": "Magha",
        "lord": "Ketu",
        "start": 120.0,
        "end": 133.333333,
    },
    {
        "index": 10,
        "name": "Purva Phalguni",
        "name_tr": "Purva Phalguni",
        "lord": "Venus",
        "start": 133.333333,
        "end": 146.666667,
    },
    {
        "index": 11,
        "name": "Uttara Phalguni",
        "name_tr": "Uttara Phalguni",
        "lord": "Sun",
        "start": 146.666667,
        "end": 160.0,
    },
    {
        "index": 12,
        "name": "Hasta",
        "name_tr": "Hasta",
        "lord": "Moon",
        "start": 160.0,
        "end": 173.333333,
    },
    {
        "index": 13,
        "name": "Chitra",
        "name_tr": "Çitra",
        "lord": "Mars",
        "start": 173.333333,
        "end": 186.666667,
    },
    {
        "index": 14,
        "name": "Swati",
        "name_tr": "Svati",
        "lord": "Rahu",
        "start": 186.666667,
        "end": 200.0,
    },
    {
        "index": 15,
        "name": "Vishakha",
        "name_tr": "Vişakha",
        "lord": "Jupiter",
        "start": 200.0,
        "end": 213.333333,
    },
    {
        "index": 16,
        "name": "Anuradha",
        "name_tr": "Anuradha",
        "lord": "Saturn",
        "start": 213.333333,
        "end": 226.666667,
    },
    {
        "index": 17,
        "name": "Jyeshtha",
        "name_tr": "Jyeştha",
        "lord": "Mercury",
        "start": 226.666667,
        "end": 240.0,
    },
    {
        "index": 18,
        "name": "Mula",
        "name_tr": "Mula",
        "lord": "Ketu",
        "start": 240.0,
        "end": 253.333333,
    },
    {
        "index": 19,
        "name": "Purva Ashadha",
        "name_tr": "Purva Aşadha",
        "lord": "Venus",
        "start": 253.333333,
        "end": 266.666667,
    },
    {
        "index": 20,
        "name": "Uttara Ashadha",
        "name_tr": "Uttara Aşadha",
        "lord": "Sun",
        "start": 266.666667,
        "end": 280.0,
    },
    {
        "index": 21,
        "name": "Shravana",
        "name_tr": "Şravana",
        "lord": "Moon",
        "start": 280.0,
        "end": 293.333333,
    },
    {
        "index": 22,
        "name": "Dhanishta",
        "name_tr": "Dhanişta",
        "lord": "Mars",
        "start": 293.333333,
        "end": 306.666667,
    },
    {
        "index": 23,
        "name": "Shatabhisha",
        "name_tr": "Şatabhişa",
        "lord": "Rahu",
        "start": 306.666667,
        "end": 320.0,
    },
    {
        "index": 24,
        "name": "Purva Bhadrapada",
        "name_tr": "Purva Bhadrapada",
        "lord": "Jupiter",
        "start": 320.0,
        "end": 333.333333,
    },
    {
        "index": 25,
        "name": "Uttara Bhadrapada",
        "name_tr": "Uttara Bhadrapada",
        "lord": "Saturn",
        "start": 333.333333,
        "end": 346.666667,
    },
    {
        "index": 26,
        "name": "Revati",
        "name_tr": "Revati",
        "lord": "Mercury",
        "start": 346.666667,
        "end": 360.0,
    },
]

# Dasa Periyotları (Yıl cinsinden) - Toplam 120 yıl
DASA_YEARS = {
    "Ketu": 7,
    "Venus": 20,
    "Sun": 6,
    "Moon": 10,
    "Mars": 7,
    "Rahu": 18,
    "Jupiter": 16,
    "Saturn": 19,
    "Mercury": 17,
}

# Dasa Sırası (Ketu'dan başlar)
DASA_ORDER = [
    "Ketu",
    "Venus",
    "Sun",
    "Moon",
    "Mars",
    "Rahu",
    "Jupiter",
    "Saturn",
    "Mercury",
]

# Gezegen Türkçe İsimleri
PLANET_NAMES_TR = {
    "Ketu": "Ketu (Güney Ay Düğümü)",
    "Venus": "Venüs (Şukra)",
    "Sun": "Güneş (Surya)",
    "Moon": "Ay (Chandra)",
    "Mars": "Mars (Mangal)",
    "Rahu": "Rahu (Kuzey Ay Düğümü)",
    "Jupiter": "Jüpiter (Guru)",
    "Saturn": "Satürn (Şani)",
    "Mercury": "Merkür (Budha)",
}

# Toplam Dasa döngüsü (yıl)
TOTAL_DASA_CYCLE = 120.0
NAKSHATRA_SPAN = 360.0 / 27.0  # ~13.333333 derece


def get_nakshatra_info(moon_degree):
    """Ay'ın derecesine göre Nakshatra bilgisini döndürür."""
    degree = moon_degree % 360
    if degree < 0:
        degree += 360

    nakshatra_index = int(degree / NAKSHATRA_SPAN)
    if nakshatra_index > 26:
        nakshatra_index = 26

    nakshatra = NAKSHATRAS[nakshatra_index]
    degree_in_nakshatra = degree - nakshatra["start"]
    pada = int(degree_in_nakshatra / (NAKSHATRA_SPAN / 4)) + 1  # 4 pada per nakshatra
    if pada > 4:
        pada = 4

    return {
        "index": nakshatra_index,
        "name": nakshatra["name"],
        "name_tr": nakshatra["name_tr"],
        "lord": nakshatra["lord"],
        "pada": pada,
        "degree_in_nakshatra": round(degree_in_nakshatra, 4),
        "percentage_traversed": round((degree_in_nakshatra / NAKSHATRA_SPAN) * 100, 2),
    }


def calculate_dasa_balance_at_birth(moon_degree):
    """Doğum anında kalan Dasa süresini hesaplar."""
    nakshatra_info = get_nakshatra_info(moon_degree)
    start_lord = nakshatra_info["lord"]

    # Nakshatra'nın kalan kısmı = Dasa'nın kalan kısmı
    remaining_in_nakshatra = NAKSHATRA_SPAN - nakshatra_info["degree_in_nakshatra"]
    balance_ratio = remaining_in_nakshatra / NAKSHATRA_SPAN

    # Başlangıç Dasa'sının kalan süresi (yıl)
    balance_years = balance_ratio * DASA_YEARS[start_lord]

    return {
        "start_lord": start_lord,
        "balance_years": balance_years,
        "balance_days": balance_years * 365.25,
        "nakshatra_info": nakshatra_info,
    }


def get_dasa_sequence_from_lord(start_lord):
    """Belirli bir lord'dan başlayan Dasa sırasını döndürür."""
    start_idx = DASA_ORDER.index(start_lord)
    return DASA_ORDER[start_idx:] + DASA_ORDER[:start_idx]


def calculate_sub_period_duration(main_years, sub_lord_years):
    """Alt periyot süresini hesaplar (gün cinsinden)."""
    return (main_years * sub_lord_years / TOTAL_DASA_CYCLE) * 365.25


def get_vimshottari_dasa(birth_dt, natal_moon_degree):
    """
    Kapsamlı Vimshottari Dasa hesaplaması.

    Hesaplar:
    - Maha Dasa (Ana Dasa)
    - Antardasa (Bhukti - Alt Dasa)
    - Pratyantardasa (3. seviye)
    - Nakshatra bilgisi
    - Gelecek 5 yıllık Dasa takvimi

    Args:
        birth_dt: Doğum tarihi (datetime)
        natal_moon_degree: Ay'ın ekliptik derecesi (0-360)

    Returns:
        dict: Kapsamlı Dasa bilgileri
    """
    try:
        if natal_moon_degree is None:
            return {
                "error": "Ay pozisyonu bulunamadığı için Vimshottari Dasa hesaplanamadı."
            }

        now = datetime.now()

        # 1. Nakshatra ve başlangıç Dasa bilgisi
        birth_balance = calculate_dasa_balance_at_birth(natal_moon_degree)
        nakshatra_info = birth_balance["nakshatra_info"]
        start_lord = birth_balance["start_lord"]
        balance_days = birth_balance["balance_days"]

        # 2. Tüm Dasa periyotlarını hesapla (doğumdan itibaren)
        dasa_sequence = get_dasa_sequence_from_lord(start_lord)
        all_dasas = []

        # İlk Dasa (kalan süre ile)
        first_dasa_end = birth_dt + timedelta(days=balance_days)
        all_dasas.append(
            {
                "lord": start_lord,
                "lord_tr": PLANET_NAMES_TR[start_lord],
                "start": birth_dt,
                "end": first_dasa_end,
                "duration_years": balance_days / 365.25,
                "is_partial": True,
            }
        )

        # Sonraki Dasa'lar (tam periyotlar)
        current_start = first_dasa_end
        for i in range(1, len(dasa_sequence)):
            lord = dasa_sequence[i]
            duration_days = DASA_YEARS[lord] * 365.25
            dasa_end = current_start + timedelta(days=duration_days)
            all_dasas.append(
                {
                    "lord": lord,
                    "lord_tr": PLANET_NAMES_TR[lord],
                    "start": current_start,
                    "end": dasa_end,
                    "duration_years": DASA_YEARS[lord],
                    "is_partial": False,
                }
            )
            current_start = dasa_end

        # İkinci döngü için devam (120 yıl sonrası)
        for lord in dasa_sequence:
            duration_days = DASA_YEARS[lord] * 365.25
            dasa_end = current_start + timedelta(days=duration_days)
            all_dasas.append(
                {
                    "lord": lord,
                    "lord_tr": PLANET_NAMES_TR[lord],
                    "start": current_start,
                    "end": dasa_end,
                    "duration_years": DASA_YEARS[lord],
                    "is_partial": False,
                }
            )
            current_start = dasa_end

        # 3. Mevcut Maha Dasa'yı bul
        current_maha_dasa = None
        current_maha_dasa_index = 0
        for i, dasa in enumerate(all_dasas):
            if dasa["start"] <= now < dasa["end"]:
                current_maha_dasa = dasa
                current_maha_dasa_index = i
                break

        if not current_maha_dasa:
            return {"error": "Mevcut Dasa periyodu bulunamadı."}

        # 4. Antardasa (Bhukti) hesapla
        maha_lord = current_maha_dasa["lord"]
        maha_start = current_maha_dasa["start"]
        maha_duration_days = (current_maha_dasa["end"] - maha_start).days

        bhukti_sequence = get_dasa_sequence_from_lord(maha_lord)
        all_bhuktis = []
        bhukti_start = maha_start

        for bhukti_lord in bhukti_sequence:
            bhukti_duration_days = calculate_sub_period_duration(
                maha_duration_days / 365.25, DASA_YEARS[bhukti_lord]
            )
            bhukti_end = bhukti_start + timedelta(days=bhukti_duration_days)
            all_bhuktis.append(
                {
                    "lord": bhukti_lord,
                    "lord_tr": PLANET_NAMES_TR[bhukti_lord],
                    "start": bhukti_start,
                    "end": bhukti_end,
                    "duration_days": bhukti_duration_days,
                }
            )
            bhukti_start = bhukti_end

        # Mevcut Bhukti'yi bul
        current_bhukti = None
        current_bhukti_index = 0
        for i, bhukti in enumerate(all_bhuktis):
            if bhukti["start"] <= now < bhukti["end"]:
                current_bhukti = bhukti
                current_bhukti_index = i
                break

        # 5. Pratyantardasa (3. seviye) hesapla
        current_pratyantardasa = None
        all_pratyantardasas = []

        if current_bhukti:
            bhukti_lord = current_bhukti["lord"]
            bhukti_start = current_bhukti["start"]
            bhukti_duration_days = current_bhukti["duration_days"]

            pratyantar_sequence = get_dasa_sequence_from_lord(bhukti_lord)
            pratyantar_start = bhukti_start

            for pratyantar_lord in pratyantar_sequence:
                pratyantar_duration_days = calculate_sub_period_duration(
                    bhukti_duration_days / 365.25, DASA_YEARS[pratyantar_lord]
                )
                pratyantar_end = pratyantar_start + timedelta(
                    days=pratyantar_duration_days
                )
                all_pratyantardasas.append(
                    {
                        "lord": pratyantar_lord,
                        "lord_tr": PLANET_NAMES_TR[pratyantar_lord],
                        "start": pratyantar_start,
                        "end": pratyantar_end,
                        "duration_days": pratyantar_duration_days,
                    }
                )
                pratyantar_start = pratyantar_end

            # Mevcut Pratyantardasa'yı bul
            for pratyantar in all_pratyantardasas:
                if pratyantar["start"] <= now < pratyantar["end"]:
                    current_pratyantardasa = pratyantar
                    break

        # 6. Gelecek 5 yıllık Dasa takvimi
        future_timeline = []
        five_years_later = now + timedelta(days=5 * 365.25)

        for dasa in all_dasas:
            if dasa["end"] > now and dasa["start"] < five_years_later:
                future_timeline.append(
                    {
                        "type": "Maha Dasa",
                        "lord": dasa["lord"],
                        "lord_tr": PLANET_NAMES_TR[dasa["lord"]],
                        "start": dasa["start"].strftime("%Y-%m-%d"),
                        "end": dasa["end"].strftime("%Y-%m-%d"),
                    }
                )

        # Gelecek Bhukti'ler (mevcut Maha Dasa içinde)
        for bhukti in all_bhuktis:
            if bhukti["end"] > now and bhukti["start"] < five_years_later:
                future_timeline.append(
                    {
                        "type": "Antardasa",
                        "lord": f"{maha_lord}-{bhukti['lord']}",
                        "lord_tr": f"{PLANET_NAMES_TR[maha_lord]} / {PLANET_NAMES_TR[bhukti['lord']]}",
                        "start": bhukti["start"].strftime("%Y-%m-%d"),
                        "end": bhukti["end"].strftime("%Y-%m-%d"),
                    }
                )

        # 7. Kalan süreleri hesapla
        remaining_in_maha = (current_maha_dasa["end"] - now).days
        remaining_in_bhukti = (
            (current_bhukti["end"] - now).days if current_bhukti else 0
        )
        remaining_in_pratyantar = (
            (current_pratyantardasa["end"] - now).days if current_pratyantardasa else 0
        )

        # 8. Sonuç
        return {
            # Nakshatra Bilgisi
            "nakshatra": {
                "name": nakshatra_info["name"],
                "name_tr": nakshatra_info["name_tr"],
                "lord": nakshatra_info["lord"],
                "pada": nakshatra_info["pada"],
                "degree": round(nakshatra_info["degree_in_nakshatra"], 2),
                "percentage": nakshatra_info["percentage_traversed"],
            },
            # Mevcut Maha Dasa
            "main_dasa_lord": current_maha_dasa["lord"],
            "main_dasa_lord_tr": PLANET_NAMES_TR[current_maha_dasa["lord"]],
            "main_dasa_start_date": current_maha_dasa["start"].strftime("%Y-%m-%d"),
            "main_dasa_end_date": current_maha_dasa["end"].strftime("%Y-%m-%d"),
            "remaining_days_in_main_dasa": remaining_in_maha,
            "remaining_years_in_main_dasa": round(remaining_in_maha / 365.25, 2),
            # Mevcut Antardasa (Bhukti)
            "sub_dasa_lord": current_bhukti["lord"] if current_bhukti else None,
            "sub_dasa_lord_tr": PLANET_NAMES_TR[current_bhukti["lord"]]
            if current_bhukti
            else None,
            "sub_dasa_start_date": current_bhukti["start"].strftime("%Y-%m-%d")
            if current_bhukti
            else None,
            "sub_dasa_end_date": current_bhukti["end"].strftime("%Y-%m-%d")
            if current_bhukti
            else None,
            "remaining_days_in_sub_dasa": remaining_in_bhukti,
            # Mevcut Pratyantardasa (3. seviye)
            "pratyantar_lord": current_pratyantardasa["lord"]
            if current_pratyantardasa
            else None,
            "pratyantar_lord_tr": PLANET_NAMES_TR[current_pratyantardasa["lord"]]
            if current_pratyantardasa
            else None,
            "pratyantar_start_date": current_pratyantardasa["start"].strftime(
                "%Y-%m-%d"
            )
            if current_pratyantardasa
            else None,
            "pratyantar_end_date": current_pratyantardasa["end"].strftime("%Y-%m-%d")
            if current_pratyantardasa
            else None,
            "remaining_days_in_pratyantar": remaining_in_pratyantar,
            # Mevcut Dasa Dizisi (kısa format)
            "current_period": f"{current_maha_dasa['lord']}-{current_bhukti['lord'] if current_bhukti else '?'}-{current_pratyantardasa['lord'] if current_pratyantardasa else '?'}",
            "current_period_tr": f"{PLANET_NAMES_TR[current_maha_dasa['lord']].split(' ')[0]} / {PLANET_NAMES_TR[current_bhukti['lord']].split(' ')[0] if current_bhukti else '?'} / {PLANET_NAMES_TR[current_pratyantardasa['lord']].split(' ')[0] if current_pratyantardasa else '?'}",
            # Gelecek 5 Yıllık Takvim
            "future_timeline": future_timeline[:15],  # İlk 15 periyot
            # Tüm Bhukti'ler (mevcut Maha Dasa için)
            "all_bhuktis_in_current_dasa": [
                {
                    "lord": b["lord"],
                    "lord_tr": PLANET_NAMES_TR[b["lord"]],
                    "start": b["start"].strftime("%Y-%m-%d"),
                    "end": b["end"].strftime("%Y-%m-%d"),
                    "is_current": b["lord"]
                    == (current_bhukti["lord"] if current_bhukti else None),
                }
                for b in all_bhuktis
            ],
        }

    except Exception as e:
        logger.error(f"Vimshottari Dasa hesaplama hatası: {str(e)}", exc_info=True)
        return {"error": f"Vimshottari Dasa hesaplama hatası: {str(e)}"}


# Firdaria periyotları hesaplaması
def get_firdaria_period(birth_dt, natal_sun_pos, natal_houses_data):
    """Doğum tarihine ve Güneş'in evine göre Firdaria periyotlarını hesaplar."""
    try:
        # Gündüz veya Gece doğumu kontrolü
        # Güneş 1. evden 6. eve kadar ise gündüz, 7. evden 12. eve kadar ise gece kabul edilir.
        sun_house = natal_sun_pos.get("house") if natal_sun_pos else None

        if sun_house is None or sun_house == 0:
            # Eğer güneşin evi hesaplanamadıysa veya geçersizse, saati kullanarak kaba bir tahmin yapalım.
            # Ancak ev daha doğrudur. Loglama ile uyarı verelim.
            logger.warning(
                f"Güneş evi belirlenemedi ({sun_house}), Firdaria için kaba saat tahmini kullanılıyor."
            )
            is_daytime_birth = 6 <= birth_dt.hour < 18
        else:
            is_daytime_birth = 1 <= sun_house <= 6

        # Firdaria Süreleri (Yıl olarak)
        period_years = {
            "Sun": 10,
            "Venus": 8,
            "Mercury": 13,
            "Moon": 9,
            "Saturn": 11,
            "Jupiter": 12,
            "Mars": 7,
            # Kuzey ve Güney Düğümleri de dahil edilebilir (standart 7 gezegen sisteminde yok)
            # "North Node": 3, "South Node": 2, # Toplam 75 yıl olur
        }
        total_cycle_years = sum(period_years.values())  # 72 yıl (7 gezegen için)

        # Firdaria Sırası (Gündüz ve Gece doğumuna göre)
        # 7 gezegenli sistem
        firdaria_sequence_day = [
            "Sun",
            "Venus",
            "Mercury",
            "Moon",
            "Saturn",
            "Jupiter",
            "Mars",
        ]
        firdaria_sequence_night = [
            "Moon",
            "Saturn",
            "Jupiter",
            "Mars",
            "Sun",
            "Venus",
            "Mercury",
        ]  # Bu sıra doğrudur

        # Doğum tarihinden bugüne kadar geçen gün sayısı
        age_in_days = (datetime.now() - birth_dt).days
        age_in_years = age_in_days / 365.25  # Geçen yaklaşık yıl

        # Hangi ana periyotta olduğunu bul (72 yıllık döngüler halinde)
        current_sequence = (
            firdaria_sequence_day if is_daytime_birth else firdaria_sequence_night
        )
        years_passed_in_total_cycles = (
            int(age_in_years / total_cycle_years) * total_cycle_years
        )  # Tam döngülerde geçen yıl
        years_passed_in_current_cycle = (
            age_in_years - years_passed_in_total_cycles
        )  # Mevcut döngüde geçen yıl

        accumulated_years_in_cycle = 0  # Mevcut döngü içinde biriken yıl
        main_ruler = None
        main_period_start_date = None
        main_period_end_date = None

        for i, planet in enumerate(current_sequence):
            duration = period_years[planet]

            if years_passed_in_current_cycle < accumulated_years_in_cycle + duration:
                main_ruler = planet
                # Ana periyot başlangıç tarihi = Doğum tarihi + (Tam döngüler * 72 yıl + Mevcut döngüde bu periyottan önceki süre) gün
                total_days_before_main_period = (
                    years_passed_in_total_cycles + accumulated_years_in_cycle
                ) * 365.25
                main_period_start_date = birth_dt + timedelta(
                    days=total_days_before_main_period
                )
                main_period_end_date = main_period_start_date + timedelta(
                    days=duration * 365.25
                )  # Ana periyot bitiş tarihi

                # Alt periyodu (Sub-ruler) hesapla
                # Alt periyot döngüsü Ana Periyot yöneticisi ile başlar
                sub_sequence_start_index = current_sequence.index(main_ruler)
                sub_sequence = (
                    current_sequence[sub_sequence_start_index:]
                    + current_sequence[:sub_sequence_start_index]
                )

                # Ana periyot içinde geçen gün sayısı
                days_passed_in_main_period = (
                    datetime.now() - main_period_start_date
                ).days

                accumulated_sub_days = (
                    0  # Ana periyot içinde biriken alt periyot günleri
                )
                sub_ruler = None
                sub_period_start_date = (
                    main_period_start_date  # İlk alt periyot ana periyotla başlar
                )
                sub_period_end_date = None

                for sub_planet in sub_sequence:
                    # Alt periyot süresi (gün olarak) = (Ana Dasa Süresi (gün) * Alt Periyot Lordunun Süresi (yıl)) / Toplam Döngü Süresi (72 yıl)
                    sub_duration_days = (
                        (main_period_end_date - main_period_start_date).days
                        * period_years[sub_planet]
                    ) / total_cycle_years

                    sub_period_end_date = sub_period_start_date + timedelta(
                        days=sub_duration_days
                    )

                    if datetime.now() < sub_period_end_date:
                        sub_ruler = sub_planet
                        break  # Alt periyot bulundu

                    sub_period_start_date = sub_period_end_date  # Sonraki alt periyot şimdikinin bittiği yerden başlar

                break  # Ana periyot bulundu

            accumulated_years_in_cycle += duration

        if (
            main_ruler
            and sub_ruler
            and main_period_start_date
            and main_period_end_date
            and sub_period_start_date
            and sub_period_end_date
        ):
            remaining_in_main_period_days = (main_period_end_date - datetime.now()).days
            remaining_in_sub_period_days = (sub_period_end_date - datetime.now()).days

            logger.info(f"Firdaria hesaplandı: Ana: {main_ruler}, Alt: {sub_ruler}")
            return {
                "main_ruler": main_ruler,
                "sub_ruler": sub_ruler,
                "main_period_start_date": main_period_start_date.strftime("%Y-%m-%d"),
                "main_period_end_date": main_period_end_date.strftime("%Y-%m-%d"),
                "sub_period_start_date": sub_period_start_date.strftime("%Y-%m-%d")
                if sub_period_start_date
                else "N/A",
                "sub_period_end_date": sub_period_end_date.strftime("%Y-%m-%d")
                if sub_period_end_date
                else "N/A",
                "remaining_days_in_main_period": remaining_in_main_period_days,
                "remaining_days_in_sub_period": remaining_in_sub_period_days,
                "note": "Bu Firdaria hesaplaması 7 gezegenli 72 yıllık döngüyü varsayar. Diğer sistemler (örn. düğümler dahil) farklı olabilir.",
            }
        else:
            logger.warning(
                "Firdaria periyodu bulunamadı. Hesaplamada bir hata olabilir."
            )
            return {"error": "Firdaria periyodu hesaplanamadı."}

    except Exception as e:
        logger.error(f"Firdaria hesaplama hatası: {str(e)}", exc_info=True)
        return {"error": f"Firdaria hesaplama hatası: {str(e)}"}


# Harmonik harita hesaplaması (Herhangi bir harmonik sayı için)
def get_harmonic_chart(dt_object, harmonic_number, celestial_bodies_positions):
    """Belirli bir datetime objesi ve N. harmonik sayı için gezegen pozisyonlarını hesaplar.
    celestial_bodies_positions: { "İsim": {"degree": X, ...} } formatında dict.
    """
    try:
        if not isinstance(harmonic_number, int) or harmonic_number <= 0:
            raise ValueError("Harmonik sayı pozitif bir tam sayı olmalıdır.")

        harmonic_positions = {}
        for name, data in celestial_bodies_positions.items():
            if "degree" not in data:
                logger.warning(
                    f"Harmonik {harmonic_number} için {name} pozisyonu (degree) eksik, atlandı."
                )
                continue
            lon = data["degree"]

            # Harmonik derece = (Natal Derece * Harmonik Sayı) % 360
            harmonic_degree = (lon * harmonic_number) % 360
            if harmonic_degree < 0:
                harmonic_degree += 360

            harmonic_positions[name] = {
                "degree": round(harmonic_degree, 2),
                "sign": get_zodiac_sign(harmonic_degree),
                "degree_in_sign": round(get_degree_in_sign(harmonic_degree), 2),
            }
            # logger.debug(f"H{harmonic_number} {name}: {harmonic_positions[name]['degree']:.2f}° {harmonic_positions[name]['sign']}")

        logger.info(
            f"Harmonik H{harmonic_number} haritası hesaplandı ({len(harmonic_positions)} adet)."
        )
        return harmonic_positions

    except Exception as e:
        logger.error(
            f"get_harmonic_chart ({harmonic_number}) fonksiyonunda hata: {str(e)}",
            exc_info=True,
        )
        return {}


# Derin harmonik analiz (Birden çok harmonik)
def calculate_deep_harmonic_analysis(birth_dt, natal_celestial_positions):
    """Doğum tarihine göre çeşitli N. harmonik haritaların gezegen pozisyonlarını hesaplar.
    natal_celestial_positions: { "İsim": {"degree": X, ...} } formatında dict. (Tüm natal noktalar)
    """
    try:
        logger.info("Derin harmonik analiz hesaplanıyor...")

        # Harmonik sayıları ve anlamları
        harmonics_to_calculate = {
            1: {"name": "Rāśi (D1)", "details": "Ana harita, hayatın tamamı"},
            2: {"name": "Hora (D2)", "details": "Para kazanma şekli, finans akışı"},
            3: {
                "name": "Drekkana (D3)",
                "details": "Cesaret, kardeşler, mücadele gücü",
            },
            4: {"name": "Chaturthamsa (D4)", "details": "Mülk, ev, yerleşim, taşınma"},
            7: {"name": "Saptamsa (D7)", "details": "Çocuklar, yaratıcılık, torunlar"},
            9: {
                "name": "Navamsa (D9)",
                "details": "Evlilik, partner, dharma, ruhsal yolculuk, En kritik varga",
            },
            10: {
                "name": "Dasamsa (D10)",
                "details": "Kariyer, meslek, toplumsal statü",
            },
            12: {"name": "Dvadasamsa (D12)", "details": "Ebeveynler, geçmiş yaşamlar"},
            13: {
                "name": "Trayodashamsa (D13)",
                "details": "arzuların, tutkuların, bastırılmış dürtülerin ve irade gücünün analiz edildiği bölünmüş haritadır",
            },
            16: {
                "name": "Shodasamsa (D16)",
                "details": "Taşıtlar, gayrimenkul, genel mutluluk/üzüntü, konfor",
            },
            17: {
                "name": "Saptadashamsa (D17)",
                "details": "güç, statü, onur, toplumsal saygınlık ve “yüksek konumda durabilme” sorusuna cevap verir.",
            },
            19: {
                "name": "Navatara (D19)",
                "details": "Ruhsal bilinç + ilahi planla senkronizasyon tanrısal düzen bu kişiyi ne kadar kolluyor?” sorusuna cevap verir.",
            },
            20: {"name": "Vimsamsa (D20)", "details": "Ruhsal gelişim, ibadet, inanç"},
            23: {
                "name": "Vimsamsa / Trimsamsa-23 (D23)",
                "details": "Bilgiyi alma, işleme ve aktarma haritası",
            },
            24: {"name": "Chaturvimsamsa (D24)", "details": "Eğitim, bilgi, öğrenme"},
            27: {
                "name": "Nakshatramsa (D27) / Bhamsa",
                "details": "Güç, zayıflık, fiziksel dayanıklılık",
            },
            30: {
                "name": "Trimsamsa (D30)",
                "details": "Zorluklar, talihsizlikler, hastalıklar, Kişinin başına “neden kötü şeyler geliyor?” sorusunun cevabı",
            },
            40: {"name": "Khavedamsa (D40)", "details": "Anne soyundan karma"},
            45: {"name": "Akshavedamsa (D45)", "details": "Baba soyundan karma"},
            60: {"name": "Shashtiamsa (D60)", "details": "Saf karma, önceki yaşam"},
            # Diğer Batı harmonikleri eklenebilir (örn. 4, 5, 8, 11, 13, 14, 15)
        }

        deep_harmonic_analysis = {}

        for harmonic_number, info in harmonics_to_calculate.items():
            # calculate_celestial_positions'ı her harmonik için tekrar çağırmak yerine,
            # natal pozisyonları alıp harmonik dönüşümü yapmak daha verimli.
            harmonic_positions = get_harmonic_chart(
                birth_dt, harmonic_number, natal_celestial_positions
            )  # Burada natal_celestial_positions kullanılır

            deep_harmonic_analysis[f"H{harmonic_number}"] = {
                "name": info["name"],
                "details": info["details"],
                "planet_positions": harmonic_positions,
            }

        logger.info(
            f"Derin harmonik analiz tamamlandı ({len(deep_harmonic_analysis)} harmonik hesaplandı)."
        )
        return deep_harmonic_analysis

    except Exception as e:
        logger.error(
            f"calculate_deep_harmonic_analysis fonksiyonunda hata: {str(e)}",
            exc_info=True,
        )
        return {}


# Transit gezegen pozisyonlarının hesaplanması (Belirli bir tarih/saat için)
# calculate_celestial_positions kullanılır
def get_transit_positions(transit_dt, latitude, longitude):
    """Belirli bir transit tarihi, saati ve konuma göre gezegen pozisyonlarını hesaplar."""
    try:
        logger.info(
            f"Transit gezegen pozisyonları hesaplanıyor: {transit_dt.strftime('%Y-%m-%d %H:%M:%S')}"
        )
        # Transit anı için evleri hesapla (transit evler için konuma ihtiyaç duyarız)
        transit_houses_data = calculate_houses(transit_dt, latitude, longitude, b"P")
        transit_house_cusps = transit_houses_data.get("house_cusps", {})

        if not transit_house_cusps or any(
            v is None for v in transit_house_cusps.values()
        ):  # Geçersiz cusp kontrolü
            logger.warning("Transit ev pozisyonları hesaplanamadı veya eksik.")
            # Devam etmek için boş cusp dict kullan, bu durumda ev bilgisi doğru olmaz
            transit_house_cusps = {str(i + 1): 0.0 for i in range(12)}

        planet_ids = {
            "Sun": swe.SUN,
            "Moon": swe.MOON,
            "Mercury": swe.MERCURY,
            "Venus": swe.VENUS,
            "Mars": swe.MARS,
            "Jupiter": swe.JUPITER,
            "Saturn": swe.SATURN,
            "Uranus": swe.URANUS,
            "Neptune": swe.NEPTUNE,
            "Pluto": swe.PLUTO,
            "True_Node": swe.TRUE_NODE,  # Transit Düğümler
        }

        # calculate_celestial_positions'ı kullanarak transit pozisyonlarını hesapla
        transit_positions = calculate_celestial_positions(
            transit_dt, transit_house_cusps, planet_ids
        )

        logger.info(
            f"Transit gezegen pozisyonları hesaplandı ({len(transit_positions)} adet)."
        )
        return (
            transit_positions,
            transit_houses_data,
        )  # Transit pozisyonları ve Transit ev verisini döndür

    except Exception as e:
        logger.error(
            f"get_transit_positions fonksiyonunda hata: {str(e)}", exc_info=True
        )
        return {}, {}  # Hata durumunda boş sözlükler döndür


# İkincil (sekonder) progresyonların hesaplanması
# calculate_celestial_positions kullanılır
def calculate_secondary_progressions(birth_dt, current_dt, latitude, longitude):
    """Doğum ve güncel tarihe göre ikincil progresyon pozisyonlarını hesaplar."""
    try:
        logger.info(
            f"Sekonder Progresyon pozisyonları hesaplanıyor ({current_dt.strftime('%Y-%m-%d %H:%M:%S')})."
        )
        # İkincil Progresyon: Doğumdan sonraki her 1 gün, yaşamdaki 1 yıla eşittir.
        # Progresif Julian Günü (UT) = Natal Julian Günü (UT) + Yaş (gün olarak)

        dt_utc_birth = birth_dt - timedelta(hours=3)  # Varsayım: UTC+3 Local -> UTC
        jd_ut_birth = swe.julday(
            dt_utc_birth.year,
            dt_utc_birth.month,
            dt_utc_birth.day,
            dt_utc_birth.hour
            + dt_utc_birth.minute / 60.0
            + dt_utc_birth.second / 3600.0,
        )

        # Yaş (gün olarak). datetime.date() kullanarak sadece gün farkını alalım.
        age_in_days = (current_dt.date() - birth_dt.date()).days

        # Progresif Julian Günü (UT)
        jd_progression_ut = jd_ut_birth + age_in_days  # Bu UT progresyon JD'sidir.

        # Progresif evleri hesapla (latitude ve longitude'a ihtiyaç duyar)
        # Progresif evler genellikle doğum yerel saati ve progresif tarih/saat JD'si ile hesaplanır.
        # Progresif Tarih/Saat: birth_dt + age_in_days
        prog_dt = datetime(
            birth_dt.year, birth_dt.month, birth_dt.day, birth_dt.hour, birth_dt.minute
        ) + timedelta(days=age_in_days)

        # calculate_houses fonksiyonunu kullanarak progresif evleri hesapla
        # Bu fonksiyon zaten UTC+3 düzeltmesini içeriyor varsayımıyla kullanalım:
        prog_houses_data = calculate_houses(prog_dt, latitude, longitude, b"P")
        prog_house_cusps = prog_houses_data.get("house_cusps", {})
        if not prog_house_cusps or any(
            v is None for v in prog_house_cusps.values()
        ):  # Geçersiz cusp kontrolü
            logger.warning("Progresif ev pozisyonları hesaplanamadı veya eksik.")
            prog_house_cusps = {str(i + 1): 0.0 for i in range(12)}  # Fallback

        celestial_bodies_ids = {
            "Sun": swe.SUN,
            "Moon": swe.MOON,
            "Mercury": swe.MERCURY,
            "Venus": swe.VENUS,
            "Mars": swe.MARS,
            "Jupiter": swe.JUPITER,
            "Saturn": swe.SATURN,
            "Uranus": swe.URANUS,
            "Neptune": swe.NEPTUNE,
            "Pluto": swe.PLUTO,
            "True_Node": swe.TRUE_NODE,  # Progresif Düğümler de hesaplanabilir
        }

        progressed_positions = {}
        for planet_name, planet_id in celestial_bodies_ids.items():
            try:
                # swe.calc_ut progresif JD'yi kullanır
                pos_result = swe.calc_ut(
                    jd_progression_ut, planet_id, swe.FLG_SWIEPH | swe.FLG_SPEED
                )

                # Hata kontrolü
                if not pos_result or not pos_result[0]:
                    logger.warning(
                        f"Sekonder Progresyon {planet_name} pozisyonu hesaplanamadı veya hata oluştu: {pos_result[1] if pos_result else 'Unknown error'}"
                    )
                    progressed_positions[planet_name] = {
                        "degree": 0.0,
                        "sign": "Bilinmiyor",
                        "retrograde": False,
                        "house": 0,
                        "speed": 0.0,
                        "latitude": 0.0,
                        "distance": 0.0,
                        "error": pos_result[1] if pos_result else "Unknown error",
                    }
                    continue

                pos = pos_result[0]
                lon = pos[0]
                lat = pos[1]
                dist = pos[2]
                speed = pos[3]

                is_retrograde = speed < 0

                # Progresif ev belirleme (prog_house_cusps kullanılır)
                house_num = (
                    get_house_number(lon, prog_house_cusps) if prog_house_cusps else 0
                )  # Ev cuspları yoksa ev 0

                progressed_positions[planet_name] = {
                    "degree": round(
                        lon % 360, 2
                    ),  # Dereceyi 0-360 arasına normalize et
                    "sign": get_zodiac_sign(lon),
                    "retrograde": is_retrograde,
                    "house": house_num,  # Progresif ev bilgisi
                    "speed": round(speed, 4),
                    "latitude": round(lat, 4),
                    "distance": round(dist, 4),
                    "degree_in_sign": round(get_degree_in_sign(lon), 2),
                    "decan": get_decan(get_degree_in_sign(lon)),
                }
                # logger.debug(f"Sekonder Progresyon {planet_name}: {progressed_positions[planet_name]}")

            except Exception as e:
                logger.error(
                    f"Sekonder Progresyon {planet_name} hesaplanırken hata: {str(e)}",
                    exc_info=True,
                )
                progressed_positions[planet_name] = {
                    "degree": 0.0,
                    "sign": "Bilinmiyor",
                    "retrograde": False,
                    "house": 0,
                    "speed": 0.0,
                    "latitude": 0.0,
                    "distance": 0.0,
                    "error": str(e),
                }
                continue

        logger.info(
            f"Sekonder Progresyon pozisyonları hesaplandı ({len(progressed_positions)} adet)."
        )
        return (
            progressed_positions,
            prog_houses_data,
        )  # Progresif pozisyonları ve ev verisini döndür

    except Exception as e:
        logger.error(
            f"calculate_secondary_progressions fonksiyonunda hata: {str(e)}",
            exc_info=True,
        )
        return {}, {}  # Hata durumunda boş sözlükler döndür


# Solar Arc progresyon hesaplaması
def get_solar_arc_progressions(birth_dt, current_dt, natal_planet_positions):
    """Doğum ve güncel tarihe göre Solar Arc progresyon pozisyonlarını hesaplar.
    Natal gezegen pozisyonlarına solar arc derecesini ekler."""
    try:
        logger.info("Solar Arc Progresyon pozisyonları hesaplanıyor...")
        dt_utc_birth = birth_dt - timedelta(hours=3)  # Varsayım: UTC+3 Local -> UTC
        jd_ut_birth = swe.julday(
            dt_utc_birth.year,
            dt_utc_birth.month,
            dt_utc_birth.day,
            dt_utc_birth.hour
            + dt_utc_birth.minute / 60.0
            + dt_utc_birth.second / 3600.0,
        )

        # Solar Arc derecesi = Doğum anı UT Güneş boylamı ile Şu anki tarih UT Güneş boylamı arasındaki fark
        # Progresif Güneş konumu için secondary progression'daki progressed_positions'dan Sun'ı alabiliriz.
        # Natal Güneş pozisyonunu al
        natal_sun_pos = natal_planet_positions.get("Sun")
        if not natal_sun_pos or "degree" not in natal_sun_pos:
            logger.error("Natal Güneş pozisyonu bulunamadı, Solar Arc hesaplanamıyor.")
            return {"error": "Natal Güneş pozisyonu eksik."}
        natal_sun_degree = natal_sun_pos["degree"]

        # İkincil Progresif Güneş pozisyonunu hesapla (Progresif JD'yi kullanarak)
        # Yaş (gün olarak)
        age_in_days = (
            current_dt.date() - birth_dt.date()
        ).days  # Sadece gün farkı alalım
        jd_progression_ut = jd_ut_birth + age_in_days  # Bu UT progresyon JD'sidir.

        prog_sun_pos_result = swe.calc_ut(jd_progression_ut, swe.SUN, swe.FLG_SWIEPH | swe.FLG_SPEED)
        if not prog_sun_pos_result or not prog_sun_pos_result[0]:
            logger.error(
                "Progresif Güneş pozisyonu hesaplanamadı, Solar Arc hesaplanamıyor."
            )
            return {"error": "Progresif Güneş pozisyonu eksik."}

        prog_sun_degree = prog_sun_pos_result[0][0] % 360

        # Solar Arc = Progresif Güneş Derecesi - Natal Güneş Derecesi
        solar_arc_degree = prog_sun_degree - natal_sun_degree
        # Ark derecesini -180 ile +180 arasına normalize et (bu, arc'ın yönünü gösterir)
        if solar_arc_degree > 180:
            solar_arc_degree -= 360
        if solar_arc_degree < -180:
            solar_arc_degree += 360

        logger.info(f"Hesaplanan Solar Arc derecesi: {solar_arc_degree:.2f}°")

        solar_arc_positions = {}
        # Natal pozisyonlara solar arc derecesini ekle
        for planet_name, natal_data in natal_planet_positions.items():
            if "degree" not in natal_data:
                continue
            natal_deg = natal_data["degree"] % 360
            sa_deg = (natal_deg + solar_arc_degree) % 360
            if sa_deg < 0:
                sa_deg += 360

            solar_arc_positions[planet_name] = {
                "degree": round(sa_deg, 2),
                "sign": get_zodiac_sign(sa_deg),
                "degree_in_sign": round(get_degree_in_sign(sa_deg), 2),
                "solar_arc_applied": round(
                    solar_arc_degree, 2
                ),  # Uygulanan arc derecesi
            }
            # logger.debug(f"SA {planet_name}: {solar_arc_positions[planet_name]}")

        logger.info("Solar Arc Progresyon pozisyonları hesaplandı.")
        return solar_arc_positions

    except Exception as e:
        logger.error(
            f"get_solar_arc_progressions fonksiyonunda hata: {str(e)}", exc_info=True
        )
        return {}


# Solar Return haritası hesaplaması
def calculate_solar_return_chart(birth_dt, current_dt, latitude, longitude):
    """Doğum tarihi ve güncel tarihe göre en yakın Solar Return (Güneş Dönüşü) tarihini bulur
    ve o tarihteki gezegen pozisyonlarını hesaplar."""
    try:
        logger.info("Solar Return hesaplaması başlıyor...")
        dt_utc_birth = birth_dt - timedelta(hours=3)  # Varsayım: UTC+3 Local -> UTC
        jd_ut_birth = swe.julday(
            dt_utc_birth.year,
            dt_utc_birth.month,
            dt_utc_birth.day,
            dt_utc_birth.hour
            + dt_utc_birth.minute / 60.0
            + dt_utc_birth.second / 3600.0,
        )

        # Natal Güneş boylamını al
        natal_sun_long = swe.calc_ut(jd_ut_birth, swe.SUN, swe.FLG_SWIEPH)[0][0]

        # Solar Return, Güneş'in tam natal pozisyonuna döndüğü andır.
        # Güncel tarihten sonraki ilk Güneş dönüşünü bulalım.
        # Arama başlangıç tarihi: Mevcut yılın doğum günü civarı, geçmişteyse gelecek yılın aynı tarihi
        test_dt_start = datetime(
            current_dt.year,
            birth_dt.month,
            birth_dt.day,
            birth_dt.hour,
            birth_dt.minute,
        )
        if test_dt_start < current_dt:
            test_dt_start = test_dt_start.replace(year=current_dt.year + 1)

        jd_test_start = swe.julday(
            test_dt_start.year,
            test_dt_start.month,
            test_dt_start.day,
            test_dt_start.hour
            + test_dt_start.minute / 60.0
            + test_dt_start.second / 3600.0,
        )

        # swe.solve_event ile hedef boylama ulaşma eventini bulalım (SWE_EVENT_BEGTRANSIT gibi eventler gezegenler arası ilişki için)
        # Belirli bir boylama ulaşma event'i için swe.soltime veya iterative arama daha uygun.
        # swe.soltime(tjd_ut, geopos, direction, rsmi, semc, serr)
        # rsmi: SWE_SMI_SUN, direction: 0 (any)
        # swe.soltime ile Güneş'in transitini bulabiliriz (doğuş, batış gibi), ama belirli bir boylama ulaşmayı bulmaz.

        # Hassas arama (iteratif) ile Güneş'in natal boylamına ulaştığı zamanı bulalım.
        solar_return_dt = None
        jd_current_test = jd_test_start
        tolerance = 0.0001  # Derece cinsinden tolerans (çok küçük olmalı)
        max_iterations = 50  # Güvenlik sınırı

        for i in range(max_iterations):
            # Güneş'in pozisyonunu ve hızını al
            pos_result = swe.calc_ut(
                jd_current_test, swe.SUN, swe.FLG_SWIEPH | swe.FLG_SPEED
            )  # Hızı da al

            if not pos_result or not pos_result[0]:
                logger.warning(
                    f"Solar Return aramasında {i}. iterasyonda Güneş pozisyonu hesaplanamadı."
                )
                break  # Hata olursa döngüden çık

            current_sun_long = pos_result[0][0]
            current_sun_speed = pos_result[0][3]  # Derece/gün cinsinden hız

            if (
                abs(current_sun_speed) < 0.01
            ):  # Hız çok düşükse veya 0'a yakınsa (retrograde vs.)
                logger.warning(
                    "Solar Return aramasında Güneş hızı sıfıra yakın, hesaplama durduruldu."
                )
                break

            # Natal boylam ile mevcut boylam arasındaki farkı hesapla
            diff = (natal_sun_long - current_sun_long) % 360
            # En kısa farkı al (-180 ile +180 aralığında)
            if diff > 180:
                diff -= 360
            if diff < -180:
                diff += 360

            # Eğer fark tolerans içindeyse, zamanı bulduk
            if abs(diff) < tolerance:
                solar_return_dt = julday_to_datetime(jd_current_test)
                break

            # Farkı kapatmak için gereken zamanı hesapla (gün olarak)
            # Zaman değişimi = Fark / Hız
            time_change_days = diff / current_sun_speed

            # Yeni test Julian günü
            jd_current_test += time_change_days

            # Arama aralığı dışına çıkmamaya dikkat edilebilir, ancak iterasyon sayısı genelde yeterlidir.
            # if jd_current_test > swe.julday(test_dt_start.year + 2, 1, 1, 0): # Örneğin 2 yıl sonrasından fazla gitmesin
            #      logger.warning("Solar Return aramasında aralık dışına çıkıldı, hassas zaman bulunamadı.")
            #      break

        if solar_return_dt is None:
            logger.warning(
                "Solar Return tarihi hassas olarak bulunamadı, en yakın değer kullanılıyor."
            )
            # Son bulunan jd_current_test en yakın değer olmalı
            solar_return_dt = swe.julday_to_datetime(jd_current_test)

        logger.info(
            f"Solar Return tarihi bulundu: {solar_return_dt.strftime('%Y-%m-%d %H:%M:%S')}"
        )

        # Solar Return anındaki evleri hesapla (lokasyon natal lokasyon)
        solar_return_houses_data = calculate_houses(
            solar_return_dt, latitude, longitude, b"P"
        )
        solar_return_house_cusps = solar_return_houses_data.get("house_cusps", {})

        if not solar_return_house_cusps:
            logger.warning("Solar Return ev pozisyonları hesaplanamadı.")
            solar_return_house_cusps = {str(i + 1): 0.0 for i in range(12)}  # Fallback

        # Gezegen ve Ek nokta pozisyonlarını hesapla (Solar Return anı ve lokasyonu için)
        planet_ids = {
            "Sun": swe.SUN,
            "Moon": swe.MOON,
            "Mercury": swe.MERCURY,
            "Venus": swe.VENUS,
            "Mars": swe.MARS,
            "Jupiter": swe.JUPITER,
            "Saturn": swe.SATURN,
            "Uranus": swe.URANUS,
            "Neptune": swe.NEPTUNE,
            "Pluto": swe.PLUTO,
            "True_Node": swe.TRUE_NODE,
        }
        additional_point_ids = {
            "Chiron": swe.CHIRON,
            "Ceres": swe.CERES,
            "Pallas": swe.PALLAS,
            "Juno": swe.JUNO,
            "Vesta": swe.VESTA,
            "Mean_Node": swe.MEAN_NODE,  # True_Node zaten planet_ids'de var
            "Mean_Lilith": swe.MEAN_APOG,
            "True_Lilith": swe.OSCU_APOG,
            # Uranianları dahil etmeyelim SR haritasında
        }

        solar_return_planet_positions = calculate_celestial_positions(
            solar_return_dt, solar_return_house_cusps, planet_ids
        )
        solar_return_additional_points = calculate_celestial_positions(
            solar_return_dt, solar_return_house_cusps, additional_point_ids
        )

        # Sonuç sözlüğünü oluştur
        # Yükselen burç ve derecesini al
        solar_return_asc_degree = solar_return_houses_data.get(
            "important_angles", {}
        ).get("ascendant")
        solar_return_asc_sign = (
            get_zodiac_sign(solar_return_asc_degree)
            if solar_return_asc_degree is not None
            else "Bilinmiyor"
        )
        solar_return_asc_deg_in_sign = (
            round(get_degree_in_sign(solar_return_asc_degree), 2)
            if solar_return_asc_degree is not None
            else 0.0
        )

        solar_return_chart_data = {
            "return_date": solar_return_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "ascendant_sign": solar_return_asc_sign,
            "ascendant_degree": solar_return_asc_deg_in_sign,
            "datetime": solar_return_dt.strftime(
                "%Y-%m-%d %H:%M:%S"
            ),  # Geriye dönük uyumluluk için
            "location": {"latitude": latitude, "longitude": longitude},
            "planet_positions": solar_return_planet_positions,
            "additional_points": solar_return_additional_points,
            "houses": solar_return_houses_data,
        }

        logger.info("Solar Return haritası hesaplaması tamamlandı.")
        return solar_return_chart_data

    except Exception as e:
        logger.error(
            f"calculate_solar_return_chart fonksiyonunda hata: {str(e)}", exc_info=True
        )
        return {}  # Hata durumunda boş sözlük döndür


# Lunar Return haritası hesaplaması
def calculate_lunar_return_chart(birth_dt, current_dt, latitude, longitude):
    """Doğum tarihi ve güncel tarihe göre en yakın Lunar Return (Ay Dönüşü) tarihini bulur
    ve o tarihteki gezegen pozisyonlarını hesaplar."""
    try:
        logger.info("Lunar Return hesaplaması başlıyor...")
        dt_utc_birth = birth_dt - timedelta(hours=3)  # Varsayım: UTC+3 Local -> UTC
        jd_ut_birth = swe.julday(
            dt_utc_birth.year,
            dt_utc_birth.month,
            dt_utc_birth.day,
            dt_utc_birth.hour
            + dt_utc_birth.minute / 60.0
            + dt_utc_birth.second / 3600.0,
        )

        # Natal Ay boylamını al
        natal_moon_long = swe.calc_ut(jd_ut_birth, swe.MOON, swe.FLG_SWIEPH)[0][0]

        # Lunar Return, Ay'ın tam natal pozisyonuna döndüğü andır. Yaklaşık her 27.3 günde bir.
        # Güncel tarihten sonraki ilk Ay dönüşünü bulalım.
        # Arama başlangıç tarihi: Güncel tarihten birkaç gün öncesi (örneğin 30 gün)
        test_dt_start = current_dt - timedelta(days=30)

        jd_test_start = swe.julday(
            test_dt_start.year,
            test_dt_start.month,
            test_dt_start.day,
            test_dt_start.hour
            + test_dt_start.minute / 60.0
            + test_dt_start.second / 3600.0,
        )

        # Hassas arama (iteratif) ile Ay'ın natal boylamına ulaştığı zamanı bulalım.
        lunar_return_dt = None
        jd_current_test = jd_test_start
        tolerance = 0.0001  # Derece cinsinden tolerans (çok küçük olmalı)
        max_iterations = (
            100  # Ay daha hızlı hareket eder, daha fazla iterasyon gerekebilir
        )

        for i in range(max_iterations):
            # Ay'ın pozisyonunu ve hızını al
            pos_result = swe.calc_ut(
                jd_current_test, swe.MOON, swe.FLG_SWIEPH | swe.FLG_SPEED
            )  # Hızı da al

            if not pos_result or not pos_result[0]:
                logger.warning(
                    f"Lunar Return aramasında {i}. iterasyonda Ay pozisyonu hesaplanamadı."
                )
                break  # Hata olursa döngüden çık

            current_moon_long = pos_result[0][0]
            current_moon_speed = pos_result[0][3]  # Derece/gün cinsinden hız

            if (
                abs(current_moon_speed) < 0.1
            ):  # Hız çok düşükse veya 0'a yakınsa (retrograde nadir ama olabilir)
                logger.warning(
                    "Lunar Return aramasında Ay hızı sıfıra yakın, hesaplama durduruldu."
                )
                break

            # Natal boylam ile mevcut boylam arasındaki farkı hesapla
            diff = (natal_moon_long - current_moon_long) % 360
            # En kısa farkı al (-180 ile +180 aralığında)
            if diff > 180:
                diff -= 360
            if diff < -180:
                diff += 360

            # Eğer fark tolerans içindeyse, zamanı bulduk
            if abs(diff) < tolerance:
                lunar_return_dt = julday_to_datetime(jd_current_test)
                break

            # Farkı kapatmak için gereken zamanı hesapla (gün olarak)
            # Zaman değişimi = Fark / Hız
            time_change_days = diff / current_moon_speed

            # Yeni test Julian günü
            jd_current_test += time_change_days

            # Arama aralığı dışına çıkmamaya dikkat edilebilir. Genellikle 30 gün yeterli arama aralığı sağlar.
            # Eğer test_dt_start'tan 30 günden fazla ileri gittiyse
            # if jd_current_test > swe.julday(test_dt_start.year, test_dt_start.month, test_dt_start.day + 30, 0):
            #     logger.warning("Lunar Return aramasında aralık dışına çıkıldı, hassas zaman bulunamadı.")
            #     break

        if lunar_return_dt is None:
            logger.warning(
                "Lunar Return tarihi hassas olarak bulunamadı, en yakın değer kullanılıyor."
            )
            # Son bulunan jd_current_test en yakın değer olmalı
            lunar_return_dt = swe.julday_to_datetime(jd_current_test)

        # Bulunan Lunar Return tarihi current_dt'den önceyse, bir sonraki dönüşü bulalım.
        # Bu basit bir kontrol, daha sofistike arama algoritmaları daha verimli olabilir.
        # Ancak iteratif yöntem genellikle en yakın çözümü bulur.
        # Eğer bulunan tarih bugünden eskiyse, test_dt_start'ı bulunan tarihten sonraya ayarlayıp tekrar arama yapılabilir.
        # Veya basitçe, eğer LR tarihi current_dt'den eskiyse, 27.3 gün (yaklaşık Ay döngüsü) ekleyerek bir sonraki LR'yi tahmin edip o civarda hassas arama yapılabilir.
        # Şimdilik bulunan tarihi kullanıyoruz, eğer logic güncel sonrası ilk LR'yi bulmaksa, başlangıç aralığı güncel tarihten başlamalıdır.
        # Önceki kod test_dt_start = current_dt - timedelta(days=15) kullanıyordu, bu bugünden önceki LR'yi bulabilir.
        # test_dt_start = current_dt # Eğer her zaman "şu anki tarihten sonraki ilk" LR isteniyorsa

        # Basitlik adına, bulunan tarihi kullanıyoruz. Eğer birden fazla LR periyodu gerekirse bu kısım güncellenmeli.

        logger.info(
            f"Lunar Return tarihi bulundu: {lunar_return_dt.strftime('%Y-%m-%d %H:%M:%S')}"
        )

        # Lunar Return anındaki evleri hesapla (lokasyon natal lokasyon)
        lunar_return_houses_data = calculate_houses(
            lunar_return_dt, latitude, longitude, b"P"
        )
        lunar_return_house_cusps = lunar_return_houses_data.get("house_cusps", {})

        if not lunar_return_house_cusps:
            logger.warning("Lunar Return ev pozisyonları hesaplanamadı.")
            lunar_return_house_cusps = {str(i + 1): 0.0 for i in range(12)}  # Fallback

        # Gezegen ve Ek nokta pozisyonlarını hesapla (Lunar Return anı ve lokasyonu için)
        planet_ids = {
            "Sun": swe.SUN,
            "Moon": swe.MOON,
            "Mercury": swe.MERCURY,
            "Venus": swe.VENUS,
            "Mars": swe.MARS,
            "Jupiter": swe.JUPITER,
            "Saturn": swe.SATURN,
            "Uranus": swe.URANUS,
            "Neptune": swe.NEPTUNE,
            "Pluto": swe.PLUTO,
            "True_Node": swe.TRUE_NODE,
        }
        additional_point_ids = {
            "Chiron": swe.CHIRON,
            "Ceres": swe.CERES,
            "Pallas": swe.PALLAS,
            "Juno": swe.JUNO,
            "Vesta": swe.VESTA,
            "Mean_Node": swe.MEAN_NODE,
            "Mean_Lilith": swe.MEAN_APOG,
            "True_Lilith": swe.OSCU_APOG,
            # Uranianları dahil etmeyelim LR haritasında
        }

        lunar_return_planet_positions = calculate_celestial_positions(
            lunar_return_dt, lunar_return_house_cusps, planet_ids
        )
        lunar_return_additional_points = calculate_celestial_positions(
            lunar_return_dt, lunar_return_house_cusps, additional_point_ids
        )

        # Sonuç sözlüğünü oluştur
        # Yükselen burç ve derecesini al
        lunar_return_asc_degree = lunar_return_houses_data.get(
            "important_angles", {}
        ).get("ascendant")
        lunar_return_asc_sign = (
            get_zodiac_sign(lunar_return_asc_degree)
            if lunar_return_asc_degree is not None
            else "Bilinmiyor"
        )
        lunar_return_asc_deg_in_sign = (
            round(get_degree_in_sign(lunar_return_asc_degree), 2)
            if lunar_return_asc_degree is not None
            else 0.0
        )

        lunar_return_chart_data = {
            "return_date": lunar_return_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "ascendant_sign": lunar_return_asc_sign,
            "ascendant_degree": lunar_return_asc_deg_in_sign,
            "datetime": lunar_return_dt.strftime(
                "%Y-%m-%d %H:%M:%S"
            ),  # Geriye dönük uyumluluk için
            "location": {"latitude": latitude, "longitude": longitude},
            "planet_positions": lunar_return_planet_positions,
            "additional_points": lunar_return_additional_points,
            "houses": lunar_return_houses_data,
        }

        logger.info("Lunar Return haritası hesaplaması tamamlandı.")
        return lunar_return_chart_data

    except Exception as e:
        logger.error(
            f"calculate_lunar_return_chart fonksiyonunda hata: {str(e)}", exc_info=True
        )
        return {}  # Hata durumunda boş sözlük döndür


# Sabit yıldızların hesaplanması
def calculate_fixed_stars(birth_dt):
    """Doğum tarihine göre sabit yıldızların pozisyonlarını hesaplar"""
    try:
        logger.info("Sabit yıldız pozisyonları hesaplanıyor...")
        dt_utc = birth_dt - timedelta(hours=3)  # Varsayım: UTC+3 Local -> UTC
        jd_ut = swe.julday(
            dt_utc.year,
            dt_utc.month,
            dt_utc.day,
            dt_utc.hour + dt_utc.minute / 60.0 + dt_utc.second / 3600.0,
        )

        # Swisseph'in desteklediği yaygın sabit yıldızların listesi
        # İsimlerin swe.fixstar veya swe.fixstar2_ut tarafından tanınması gerekir.
        # Tam liste için swisseph belgelerine ve fixstars.cat dosyasına bakılmalıdır.
        # Bazı isimler birden fazla kelime içerir ve boşluklar alt çizgi (_) ile değiştirilmelidir
        # veya swe'nin beklediği tam format kullanılmalıdır.
        # Önceki listedeki bazı isimler (Draco, Hyades, Pleiades, Praesepe, Sirius B, Procyon B, Deneb Okab, Formalhaut)
        # doğrudan tanınmıyor olabilir veya farklı bir yazılıma sahiptir.
        # Daha güvenli olması için yaygın ve bilinen isimleri kullanalım ve hata yakalamayı sürdürelim.
        fixed_stars_list_safe = [
            "Aldebaran",
            "Antares",
            "Regulus",
            "Spica",
            "Sirius",
            "Vega",
            "Fomalhaut",
            "Pollux",
            "Castor",
            "Procyon",
            "Algol",
            "Deneb_Algedi",  # Boşlukları alt çizgi yapalım
            "Scheat",
            "Markab",
            "Capella",
            "Rigel",
            "Betelgeuse",
            "Bellatrix",
            "Alnilam",
            "Alnitak",
            "Saiph",
            "Polaris",
            "Kochab",
            "Alcyone",
            "Asellus_Borealis",
            "Asellus_Australis",
            "Acubens",
            "Canopus",
            "Miaplacidus",
            "Suhail",
            "Avior",
            "Wezen",
            "Aludra",
            "Alphard",
            "Alphecca",
            "Unukalhai",
            "Rasalhague",
            "Shaula",
            "Lesath",
            "Kaus_Australis",
            "Nunki",
            "Ascella",
            "Deneb_Adige",
            "Sador",
            "Albireo",
            "Altair",
            "Algedi",
            "Nashira",
            "Sadalmelek",
            "Sadal_Suud",
            "Formalhaut",  # Formalhaut'u tekrar ekleyelim, belki farklı yazılımı denerken çalışır
        ]

        results = {}
        for star_name_raw in fixed_stars_list_safe:
            # swe fonksiyonları genellikle küçük harf ve alt çizgi ile çalışır
            star_name = star_name_raw.lower().replace(
                " ", "_"
            )  # Boşlukları alt çizgiye çevir

            try:
                # swe.fixstar(starname, tjd_ut, iflags)
                # returns ((lon, lat, dist), mag, serr) - Bu format magnitude'u veriyor
                pos_result_mag = swe.fixstar(star_name, jd_ut, swe.FLG_SWIEPH)

                # Hata kontrolü: pos_result_mag None değilse ve ilk elemanı (konum tuple) None değilse
                if not pos_result_mag or not pos_result_mag[0]:
                    # logger.debug(f"Sabit yıldız '{star_name_raw}' pozisyonu hesaplanamadı veya bulunamadı (pos_result_mag[0] None).")
                    continue  # Bulunamazsa atla

                pos_tuple = pos_result_mag[0]  # (lon, lat, dist)
                degree = pos_tuple[0] % 360  # Tam boylam, 0-360 normalize
                if degree < 0:
                    degree += 360
                latitude = pos_tuple[1]  # Ekliptik enlem

                # Magnitude kontrolü: pos_result_mag en az 2 elemanlı mı ve 2. eleman sayısal mı?
                magnitude = None
                if len(pos_result_mag) > 1:
                    if isinstance(pos_result_mag[1], (int, float)):
                        magnitude = float(pos_result_mag[1])
                    # else: # Eğer sayısal değilse, muhtemelen serr stringidir. Hata yakalandığında loglanır.
                    # logger.warning(f"Sabit yıldız '{star_name_raw}' için magnitude sayısal değil: {pos_result_mag[1]}.")

                sign = get_zodiac_sign(degree)

                results[star_name_raw] = {  # Orijinal ismi kaydet
                    "degree": round(degree, 2),  # Tam boylam
                    "sign": sign,
                    "degree_in_sign": round(
                        get_degree_in_sign(degree), 2
                    ),  # Burç içindeki derece
                    "latitude": round(latitude, 4),  # Ekliptik enlem
                    "magnitude": round(magnitude, 2) if magnitude is not None else None,
                }
                # logger.debug(f"{star_name_raw} pozisyonu hesaplandı: {results[star_name_raw]}")

            except swe.Error as e:
                # Swisseph'in kendi hatasını yakala (örn. yıldız bulunamadı)
                logger.debug(
                    f"Sabit yıldız {star_name_raw} hesaplanırken Swisseph hatası: {str(e)}"
                )
                continue  # Hata olursa atla

            except Exception as e:
                # Diğer olası hataları yakala (örn. TypeError)
                logger.error(
                    f"Sabit yıldız {star_name_raw} hesaplanırken beklenmedik hata: {str(e)}",
                    exc_info=True,
                )
                continue  # Hata olursa atla

        logger.info(f"Sabit yıldızların hesaplanması tamamlandı ({len(results)} adet).")
        return results

    except Exception as e:
        logger.error(
            f"calculate_fixed_stars fonksiyonunda genel hata: {str(e)}", exc_info=True
        )
        return {}


# Eclipse (Tutulma) hesaplaması - Doğum tarihi civarında veya güncel tarih civarında
def find_eclipses_in_range(start_dt, end_dt):
    """Verilen tarih aralığında Güneş ve Ay tutulmalarını bulur."""
    try:
        logger.info(
            f"Tutulmalar aranıyor: {start_dt.strftime('%Y-%m-%d')} - {end_dt.strftime('%Y-%m-%d')}"
        )

        # Aranan aralığı sınırla - çok büyük aralıklar sorun oluşturabilir
        # Başlangıç tarihi 100 yıldan fazla geriye gidiyorsa sınırla
        min_valid_year = max(start_dt.year, 100)  # Minimum 100 yıl olarak sınırla
        actual_start_dt = (
            datetime(min_valid_year, 1, 1)
            if start_dt.year < min_valid_year
            else start_dt
        )

        # Bitiş tarihi çok uzak gelecekteyse sınırla
        max_valid_year = min(end_dt.year, 3000)  # Maksimum 3000 yıl olarak sınırla
        actual_end_dt = (
            datetime(max_valid_year, 12, 31) if end_dt.year > max_valid_year else end_dt
        )

        # Tahmini tutulma tarihleri - Ay tutulması yaklaşık her 5.5 ay, Güneş tutulması yılda 2-5 kez
        # Güneş veya Ay tutulması için en yüksek sıklık genelde yılda 7'dir
        # Ocak 2020 - Aralık 2030 arası için tetik zamanları:
        solar_eclipse_dates = [
            datetime(2020, 6, 21),
            datetime(2020, 12, 14),
            datetime(2021, 6, 10),
            datetime(2021, 12, 4),
            datetime(2022, 4, 30),
            datetime(2022, 10, 25),
            datetime(2023, 4, 20),
            datetime(2023, 10, 14),
            datetime(2024, 4, 8),
            datetime(2024, 10, 2),
            datetime(2025, 3, 29),
            datetime(2025, 9, 21),
            datetime(2026, 2, 17),
            datetime(2026, 8, 12),
            datetime(2027, 2, 6),
            datetime(2027, 8, 2),
            datetime(2028, 1, 26),
            datetime(2028, 7, 22),
            datetime(2029, 1, 14),
            datetime(2029, 7, 11),
            datetime(2029, 12, 5),
            datetime(2030, 6, 1),
            datetime(2030, 11, 25),
        ]

        lunar_eclipse_dates = [
            datetime(2020, 1, 10),
            datetime(2020, 6, 5),
            datetime(2020, 7, 5),
            datetime(2020, 11, 30),
            datetime(2021, 5, 26),
            datetime(2021, 11, 19),
            datetime(2022, 5, 16),
            datetime(2022, 11, 8),
            datetime(2023, 5, 5),
            datetime(2023, 10, 28),
            datetime(2024, 3, 25),
            datetime(2024, 9, 18),
            datetime(2025, 3, 14),
            datetime(2025, 9, 7),
            datetime(2026, 3, 3),
            datetime(2026, 8, 28),
            datetime(2027, 2, 20),
            datetime(2027, 8, 17),
            datetime(2028, 2, 10),
            datetime(2028, 8, 6),
            datetime(2029, 1, 30),
            datetime(2029, 7, 26),
            datetime(2030, 1, 20),
            datetime(2030, 7, 15),
        ]

        # Tüm bu tarihleri ±30 gün arasında arayalım
        all_eclipse_triggers = []

        for solar_date in solar_eclipse_dates:
            if (
                actual_start_dt <= solar_date + timedelta(days=40)
                and solar_date - timedelta(days=40) <= actual_end_dt
            ):
                all_eclipse_triggers.append((solar_date, "Solar"))

        for lunar_date in lunar_eclipse_dates:
            if (
                actual_start_dt <= lunar_date + timedelta(days=40)
                and lunar_date - timedelta(days=40) <= actual_end_dt
            ):
                all_eclipse_triggers.append((lunar_date, "Lunar"))

        # Sonuç listesi
        eclipses_list = []

        # Her potansiyel tutulma tarihinde detaylı arama yap
        for trigger_date, eclipse_type in all_eclipse_triggers:
            # Her tetik noktasının etrafında ±30 günlük bir arama yapalım
            search_start = max(actual_start_dt, trigger_date - timedelta(days=30))
            search_end = min(actual_end_dt, trigger_date + timedelta(days=30))

            # Julian günlerine çevir
            jd_start = swe.julday(
                search_start.year, search_start.month, search_start.day, 0
            )
            jd_end = swe.julday(
                search_end.year, search_end.month, search_end.day, 23.99
            )

            try:
                # Ay tutulması araması
                if eclipse_type == "Lunar":
                    res = swe.lun_eclipse_when(jd_start, swe.FLG_SWIEPH, 0)
                    if res and res[0] < jd_end:
                        jd_eclipse = res[0]
                        ecl_type = res[4] if len(res) > 4 else 0
                        ecl_mag = res[5] if len(res) > 5 else 0
                        saros = res[6] if len(res) > 6 else None

                        # Tarih ve saat bilgisini al
                        dt_parts = swe.revjul(jd_eclipse, swe.GREG_CAL)
                        if dt_parts and dt_parts[0] > 0 and dt_parts[0] < 9999:
                            year, month, day, hour_float = dt_parts
                            hour = int(hour_float)
                            minute = int((hour_float - hour) * 60)
                            second = int(((hour_float - hour) * 60 - minute) * 60)
                            eclipse_dt = datetime(
                                year, month, day, hour, minute, second
                            )

                            # Tutulma tipini belirle
                            type_name = (
                                "Total"
                                if ecl_type & swe.ECL_TOTAL
                                else "Partial"
                                if ecl_type & swe.ECL_PARTIAL
                                else "Penumbral"
                                if ecl_type & swe.ECL_PENUMBRAL
                                else "Unknown"
                            )

                            eclipses_list.append(
                                {
                                    "datetime": eclipse_dt.strftime(
                                        "%Y-%m-%d %H:%M:%S"
                                    ),
                                    "eclipse_type": "Lunar " + type_name,
                                    "details": {
                                        "type": "Lunar",
                                        "event_type_flag": ecl_type,
                                        "magnitude": ecl_mag,
                                        "saros": saros,
                                    },
                                }
                            )

                # Güneş tutulması araması
                if eclipse_type == "Solar":
                    res = swe.sol_eclipse_when_glob(jd_start, swe.FLG_SWIEPH, 0)
                    if res and res[0] < jd_end:
                        jd_eclipse = res[0]
                        ecl_type = res[1] if len(res) > 1 else 0
                        ecl_mag = res[2] if len(res) > 2 else 0
                        saros = res[3] if len(res) > 3 else None

                        # Tarih ve saat bilgisini al
                        dt_parts = swe.revjul(jd_eclipse, swe.GREG_CAL)
                        if dt_parts and dt_parts[0] > 0 and dt_parts[0] < 9999:
                            year, month, day, hour_float = dt_parts
                            hour = int(hour_float)
                            minute = int((hour_float - hour) * 60)
                            second = int(((hour_float - hour) * 60 - minute) * 60)
                            eclipse_dt = datetime(
                                year, month, day, hour, minute, second
                            )

                            # Tutulma tipini belirle
                            type_name = (
                                "Total"
                                if ecl_type & swe.ECL_TOTAL
                                else "Annular"
                                if ecl_type & swe.ECL_ANNULAR
                                else "Partial"
                                if ecl_type & swe.ECL_PARTIAL
                                else "Annular-Total"
                                if ecl_type & swe.ECL_ANNULAR_TOTAL
                                else "Unknown"
                            )

                            eclipses_list.append(
                                {
                                    "datetime": eclipse_dt.strftime(
                                        "%Y-%m-%d %H:%M:%S"
                                    ),
                                    "eclipse_type": "Solar " + type_name,
                                    "details": {
                                        "type": "Solar",
                                        "type_name": type_name,
                                        "event_type_flag": ecl_type,
                                        "magnitude": ecl_mag,
                                        "saros": saros,
                                    },
                                }
                            )
            except Exception as e:
                # Eğer bu aralıkta hata oluşursa, logla ve devam et
                logger.warning(
                    f"Tutulma arama hatası (tarih: {trigger_date}): {str(e)}"
                )
                continue

        # Tarihe göre sırala
        eclipses_list.sort(key=lambda x: x["datetime"])

        # Tekrarlanan tutulmaları kaldır
        unique_eclipses = []
        seen_dates = set()

        for eclipse in eclipses_list:
            date_part = eclipse["datetime"].split(" ")[0]  # Sadece tarih kısmını al
            if date_part not in seen_dates:
                seen_dates.add(date_part)
                unique_eclipses.append(eclipse)

        logger.info(
            f"Tutulma arama tamamlandı. Bulunan tutulma sayısı: {len(unique_eclipses)}"
        )
        return unique_eclipses

    except Exception as e:
        logger.error(
            f"find_eclipses_in_range fonksiyonunda hata: {str(e)}", exc_info=True
        )
        return []


# Antiscia ve Contra-antiscia hesaplaması (Doğum anı için)
def calculate_antiscia(natal_celestial_positions, orb=1.0):
    """Gezegenlerin antiscia (karşıt dekan) ve contra-antiscia (karşıt burçta aynı dekan) noktalarını ve bağlantılarını hesaplar.

    Args:
        natal_celestial_positions (dict): Natal gezegen/nokta konumları
        orb (float): Maksimum tolerans derecesi (default 1°)

    Returns:
        dict: Her gezegen/nokta için antiscia/contra-antiscia bilgileri ve bağlantılar
    """
    try:
        # Sadece 'degree' anahtarı olan geçerli pozisyonları al
        valid_positions = {
            k: v
            for k, v in natal_celestial_positions.items()
            if isinstance(v, dict) and "degree" in v
        }

        results = {}

        # Pozisyonları normalize et (0-360)
        normalized_positions = {
            p: data["degree"] % 360 for p, data in valid_positions.items()
        }

        for planet1, deg1 in normalized_positions.items():
            # Antiscia noktası hesapla: (180 - deg1) % 360
            antiscia_deg = (180 - deg1) % 360
            if antiscia_deg < 0:
                antiscia_deg += 360

            # Contra-antiscia noktası hesapla: (360 - deg1) % 360
            contra_antiscia_deg = (360 - deg1) % 360
            if contra_antiscia_deg < 0:
                contra_antiscia_deg += 360

            antiscia_connections = []
            contra_antiscia_connections = []

            # Diğer gezegen/noktalarla bağlantıları kontrol et
            for planet2, deg2 in normalized_positions.items():
                if planet1 == planet2:
                    continue  # Kendisiyle kıyaslama yapma

                # Antiscia bağlantısı kontrolü: deg2, antiscia_deg'e orb kadar yakın mı?
                diff_antiscia = abs(deg2 - antiscia_deg)
                orb_antiscia_value = min(
                    diff_antiscia, 360 - diff_antiscia
                )  # En kısa yay

                if orb_antiscia_value <= orb:
                    antiscia_connections.append(
                        {
                            "planet": planet2,
                            "degree": round(deg2, 2),
                            "sign": get_zodiac_sign(deg2),
                            "orb": round(orb_antiscia_value, 2),
                        }
                    )

                # Contra-antiscia bağlantısı kontrolü: deg2, contra_antiscia_deg'e orb kadar yakın mı?
                diff_contra_antiscia = abs(deg2 - contra_antiscia_deg)
                orb_contra_antiscia_value = min(
                    diff_contra_antiscia, 360 - diff_contra_antiscia
                )  # En kısa yay

                if orb_contra_antiscia_value <= orb:
                    contra_antiscia_connections.append(
                        {
                            "planet": planet2,
                            "degree": round(deg2, 2),
                            "sign": get_zodiac_sign(deg2),
                            "orb": round(orb_contra_antiscia_value, 2),
                        }
                    )

            results[planet1] = {
                "original_degree": round(deg1, 2),
                "original_sign": get_zodiac_sign(deg1),
                "antiscia": {
                    "degree": round(antiscia_deg, 2),
                    "sign": get_zodiac_sign(antiscia_deg),
                    "connections": sorted(
                        antiscia_connections, key=lambda x: x["orb"]
                    ),  # Orba göre sırala
                },
                "contra_antiscia": {
                    "degree": round(contra_antiscia_deg, 2),
                    "sign": get_zodiac_sign(contra_antiscia_deg),
                    "connections": sorted(
                        contra_antiscia_connections, key=lambda x: x["orb"]
                    ),  # Orba göre sırala
                },
            }

            # logger.debug(f"{planet1} antiscia/contra-antiscia hesaplandı.")

        logger.info(
            f"Antiscia/Contra-antiscia hesaplaması tamamlandı ({len(results)} gezegen/nokta için)."
        )
        return results

    except Exception as e:
        logger.error(
            f"Antiscia/Contra-antiscia hesaplama hatası: {str(e)}", exc_info=True
        )
        return {}


# Dignity ve Debility skorlarının hesaplanması (Geleneksel yöneticilik, yücelim vb.)
def calculate_dignity_scores(natal_planet_positions):
    """Gezegenlerin basit dignity (yönetim, yücelim) skorlarını hesaplar.
    Ana gezegenler için hesaplama yapar."""
    try:
        # Yöneticilik (Rulership)
        rulerships = {
            "Sun": ["Aslan"],
            "Moon": ["Yengeç"],
            "Mercury": ["İkizler", "Başak"],
            "Venus": ["Boğa", "Terazi"],
            "Mars": ["Koç", "Akrep"],
            "Jupiter": ["Yay", "Balık"],
            "Saturn": ["Oğlak", "Kova"],
        }
        # Yücelim (Exaltation)
        exaltations = {
            "Sun": "Koç",
            "Moon": "Boğa",
            "Mercury": "Kova",  # Farklı kaynaklarda Merkür Başak veya Kova olabilir
            "Venus": "Balık",
            "Mars": "Oğlak",
            "Jupiter": "Yengeç",
            "Saturn": "Terazi",
        }

        # Helper to get sign degree
        def get_zodiac_sign_degree_value(sign_name):
            zodiac_signs = [
                "Koç",
                "Boğa",
                "İkizler",
                "Yengeç",
                "Aslan",
                "Başak",
                "Terazi",
                "Akrep",
                "Yay",
                "Oğlak",
                "Kova",
                "Balık",
            ]
            try:
                return zodiac_signs.index(sign_name) * 30
            except ValueError:
                return None

        # Zarar (Detriment)
        detriment_signs = (
            calculate_detriment_signs()
        )  # Zararı hesaplamak için yardımcı fonksiyon
        # Düşüş (Fall)
        fall_signs = {
            planet: get_zodiac_sign((degree + 180) % 360)
            if (degree := get_zodiac_sign_degree_value(exaltations[planet])) is not None
            else None
            for planet in [
                "Sun",
                "Moon",
                "Mercury",
                "Venus",
                "Mars",
                "Jupiter",
                "Saturn",
            ]  # Yücelimin 180 derece karşısı (Ana gezegenler için)
        }

        dignity_scores = {}
        # Ana gezegenleri kontrol et
        planets_to_check = [
            "Sun",
            "Moon",
            "Mercury",
            "Venus",
            "Mars",
            "Jupiter",
            "Saturn",
        ]

        for planet in planets_to_check:
            if (
                planet not in natal_planet_positions
                or "degree" not in natal_planet_positions[planet]
                or "sign" not in natal_planet_positions[planet]
            ):
                logger.warning(
                    f"{planet} pozisyonu dignity için bulunamadı veya eksik."
                )
                continue

            pos = natal_planet_positions[planet]["degree"]
            sign = natal_planet_positions[planet]["sign"]
            score = 0
            status = "Peregrine"  # Başka bir dignity durumu yoksa

            # Yönetici (+5)
            if sign in rulerships.get(planet, []):
                score += 5
                status = "Yönetici"

            # Yücelimde (+4)
            if exaltations.get(planet) == sign:
                # Yücelim derecesi de kontrol edilebilir hassasiyet için (örn. Güneş 19 Koç)
                # Şimdilik sadece burç kontrolü yapalım
                score += 4
                if (
                    status != "Yönetici"
                ):  # Yönetici aynı zamanda yücelimde olamaz (Nadiren istisnai durumlar olabilir)
                    status = "Yücelimde"

            # Zararda (-5)
            if sign in detriment_signs.get(planet, []):
                score -= 5
                status = "Zararda"

            # Düşüşte (-4)
            if fall_signs.get(planet) == sign:
                score -= 4

            # Triplicity, Term, Face gibi diğer dignity'ler eklenebilir
            # ... (Daha gelişmiş bir dignity tablosu ve hesaplama gerekir)

            dignity_scores[planet] = {
                "degree": round(pos, 2),
                "sign": sign,
                "score_basic": score,  # Sadece yöneticilik/yücelim/zarar/düşüş skorunu tutalım
                "status_basic": status,  # En yüksek dignity/debility durumu
            }
            # logger.debug(f"{planet} dignity: {dignity_scores[planet]}")

        logger.info(
            f"Basit Dignity skorları hesaplandı ({len(dignity_scores)} gezegen için)."
        )
        return dignity_scores

    except Exception as e:
        logger.error(f"Dignity skorları hesaplama hatası: {str(e)}", exc_info=True)
        return {}


def calculate_zodiac_sign_degree():
    """Burç derecelerini hesaplar ve döndürür."""
    try:
        zodiac_signs = [
            "Koç",
            "Boğa",
            "İkizler",
            "Yengeç",
            "Aslan",
            "Başak",
            "Terazi",
            "Akrep",
            "Yay",
            "Oğlak",
            "Kova",
            "Balık",
        ]
        zodiac_sign_degrees = {sign: i * 30 for i, sign in enumerate(zodiac_signs)}
        return zodiac_sign_degrees
    except Exception as e:
        logger.error(f"Burç dereceleri hesaplama hatası: {str(e)}")
        return {}


def calculate_detriment_signs():
    """Zarar (Detriment) burçlarını hesaplar ve döndürür."""
    try:
        detriment_signs = {
            "Sun": ["Kova", "Terazi"],
            "Moon": ["Oğlak", "Akrep"],
            "Mercury": ["Yay", "Balık"],
            "Venus": ["Koç", "Başak"],
            "Mars": ["Boğa", "Terazi"],
            "Jupiter": ["İkizler", "Başak"],
            "Saturn": ["Aslan", "Yengeç"],
        }
        return detriment_signs
    except Exception as e:
        logger.error(f"Zarar burçları hesaplama hatası: {str(e)}")
        return {}


# Midpoint tekniklerinin hesaplanması
def get_midpoint_aspects(natal_celestial_positions, orb=2.0):
    """Natal haritadaki göksel cisim çiftlerinin midpointlerini ve bu midpointlerin
    diğer göksel cisimlere olan açılarını hesaplar."""
    try:
        ASPECT_WEIGHTS = {
            "Conjunction/Opposition": 5,
            "Square": 4,
            "Sesquiquadrate": 3,
            "Semisquare": 2,
        }

        # Sadece 'degree' anahtarı olan geçerli pozisyonları al
        valid_positions = {
            k: v
            for k, v in natal_celestial_positions.items()
            if isinstance(v, dict) and "degree" in v
        }

        midpoint_results = {}  # Değişiklik: Liste yerine Dict kullanıyoruz

        points_keys = list(valid_positions.keys())

        for i in range(len(points_keys)):
            for j in range(i + 1, len(points_keys)):  # Çiftleri tekrar etmeden al
                p1_key = points_keys[i]
                p2_key = points_keys[j]
                deg1 = valid_positions[p1_key]["degree"] % 360
                deg2 = valid_positions[p2_key]["degree"] % 360

                # Midpoint hesaplama (kısa yay)
                diff = abs(deg1 - deg2)
                if diff > 180:
                    midpoint_deg = (deg1 + deg2 + 360) / 2.0
                else:
                    midpoint_deg = (deg1 + deg2) / 2.0

                midpoint_deg = midpoint_deg % 360
                if midpoint_deg < 0:
                    midpoint_deg += 360

                midpoint_sign = get_zodiac_sign(midpoint_deg)
                midpoint_deg_in_sign = get_degree_in_sign(midpoint_deg)

                normalized_positions = calculate_normalized_positions(valid_positions)

                # Bu midpointe diğer gezegen/noktaların açılarını kontrol et
                aspects = []
                for p3_key, deg3 in normalized_positions.items():
                    if p3_key == p1_key or p3_key == p2_key:
                        continue

                    aspect_deg_diff = abs(midpoint_deg - deg3) % 180

                    min_orb_found = float("inf")
                    best_aspect_type = None

                    # Basit kontrol
                    if (
                        abs(aspect_deg_diff - 0) <= orb
                        or abs(aspect_deg_diff - 180) <= orb
                    ):
                        best_aspect_type = "Conjunction/Opposition"
                        min_orb_found = (
                            min(abs(aspect_deg_diff - 0), abs(aspect_deg_diff - 180))
                            % 180
                        )
                    elif abs(aspect_deg_diff - 90) <= orb:
                        best_aspect_type = "Square"
                        min_orb_found = abs(aspect_deg_diff - 90)
                    elif abs(aspect_deg_diff - 45) <= orb:
                        best_aspect_type = "Semisquare"
                        min_orb_found = abs(aspect_deg_diff - 45)
                    elif abs(aspect_deg_diff - 135) <= orb:
                        best_aspect_type = "Sesquiquadrate"
                        min_orb_found = abs(aspect_deg_diff - 135)

                    if best_aspect_type:
                        aspects.append(
                            {
                                "celestial_body": p3_key,
                                "aspect_type": best_aspect_type,
                                "weight": ASPECT_WEIGHTS.get(best_aspect_type, 1),
                                "orb": round(min_orb_found, 2),
                            }
                        )

                # Sadece anlamlı açıları tut
                filtered_aspects = [
                    a
                    for a in aspects
                    if (a["weight"] >= 4 or (a["weight"] == 3 and a["orb"] <= 0.7))
                ]

                if filtered_aspects:
                    combined_key = f"{p1_key}/{p2_key}"
                    midpoint_results[combined_key] = {
                        "degree": round(midpoint_deg, 2),
                        "sign": midpoint_sign,
                        "degree_in_sign": round(midpoint_deg_in_sign, 2),
                        "aspects": sorted(filtered_aspects, key=lambda x: x["orb"]),
                    }

        logger.info(
            f"Midpoint hesaplamaları tamamlandı ({len(midpoint_results)} adet)."
        )
        return midpoint_results

    except Exception as e:
        logger.error(f"get_midpoint_aspects hatası: {str(e)}", exc_info=True)
        return {}


def calculate_normalized_positions(natal_celestial_positions):
    """Natal haritadaki göksel cisimlerin pozisyonlarını normalize eder (0-360 aralığına çeker)."""
    try:
        # Sadece 'degree' anahtarı olan geçerli pozisyonları al
        valid_positions = {
            k: v
            for k, v in natal_celestial_positions.items()
            if isinstance(v, dict) and "degree" in v
        }

        normalized_positions = {
            p: data["degree"] % 360 for p, data in valid_positions.items()
        }

        logger.info(
            f"Pozisyonlar normalize edildi ({len(normalized_positions)} gezegen/nokta için)."
        )
        return normalized_positions

    except Exception as e:
        logger.error(f"Pozisyonları normalize etme hatası: {str(e)}", exc_info=True)
        return {}


# Progressed Moon Phase hesaplaması
def calculate_progressed_moon_phase(progressed_positions):
    """Progressed Sun ve Moon pozisyonlarına göre progressed Ay fazını hesaplar."""
    try:
        prog_sun_pos = progressed_positions.get("Sun")
        prog_moon_pos = progressed_positions.get("Moon")

        if (
            not prog_sun_pos
            or not prog_moon_pos
            or "degree" not in prog_sun_pos
            or "degree" not in prog_moon_pos
        ):
            logger.error(
                "Progressed Moon Phase hesaplama için progressed Güneş veya Ay pozisyonu eksik."
            )
            return {"error": "Progressed Güneş veya Ay pozisyonu eksik."}

        prog_sun_deg = prog_sun_pos["degree"]
        prog_moon_deg = prog_moon_pos["degree"]

        # Ay ile Güneş arasındaki açı farkını bul (0-360 arası normalize edilir)
        phase_angle = (prog_moon_deg - prog_sun_deg) % 360
        if phase_angle < 0:
            phase_angle += 360

        # Faz gününü hesapla (yaklaşık 29.53 günlük sinodik dönem üzerinden)
        phase_day = round((phase_angle / 360) * 29.53059, 1)

        # Ay fazını açıya göre belirle (Natal Lunation Cycle ile aynı fazlar)
        if 0 <= phase_angle < 45:
            phase = "Yeni Ay (New Moon)"
        elif 45 <= phase_angle < 90:
            phase = "Hilal (Crescent Moon)"
        elif 90 <= phase_angle < 135:
            phase = "İlk Dördün (First Quarter)"
        elif 135 <= phase_angle < 180:
            phase = "Şişen Ay (Gibbous Moon)"
        elif 180 <= phase_angle < 225:
            phase = "Dolunay (Full Moon)"
        elif 225 <= phase_angle < 270:
            phase = "Dağılma (Disseminating Moon)"
        elif 270 <= phase_angle < 315:
            phase = "Son Dördün (Last Quarter)"
        elif 315 <= phase_angle < 360:
            phase = "Balsamik Ay (Balsamic Moon)"
        else:
            phase = "Bilinmeyen Faz"

        result = {
            "phase_name": phase,
            "phase_angle": round(phase_angle, 2),
            "phase_day_approx": phase_day,  # Bu progressed günler değil, sinodik gün sayısıdır
        }

        logger.info(f"Progressed Moon Phase hesaplandı: {result}")
        return result

    except Exception as e:
        logger.error(f"Progressed Moon Phase hesaplama hatası: {str(e)}", exc_info=True)
        return {"error": str(e)}


# Azimuth ve Altitude hesaplaması (Belirli bir andaki göksel cisimlerin horizon üzerindeki pozisyonları)
def calculate_azimuth_altitude_for_bodies(
    dt_object, latitude, longitude, elevation_m, celestial_positions
):
    """Belirli bir datetime, konum ve yükseklik için göksel cisimlerin Azimuth ve Altitude (Ufuk) koordinatlarını hesaplar.
    celestial_positions: { "İsim": {"degree": X, "latitude": Y, "distance": Z} } formatında dict.
    """
    try:
        logger.info("Göksel cisimlerin Azimuth ve Altitude hesaplanıyor...")
        dt_utc = dt_object - timedelta(hours=3)  # Varsayım: UTC+3 Local -> UTC
        jd_ut = swe.julday(
            dt_utc.year,
            dt_utc.month,
            dt_utc.day,
            dt_utc.hour + dt_utc.minute / 60.0 + dt_utc.second / 3600.0,
        )

        geopos = [longitude, latitude, elevation_m]  # [boylam, enlem, yükseklik metre]

        azalt_positions = {}

        # Sadece 'degree', 'latitude', 'distance' anahtarları olan geçerli pozisyonları al
        valid_positions = {
            k: v
            for k, v in celestial_positions.items()
            if isinstance(v, dict)
            and "degree" in v
            and "latitude" in v
            and "distance" in v
        }

        for body_name, data in valid_positions.items():
            try:
                # Gezegenin ekliptik pozisyonunu kullan (lon, lat, dist)
                # calculate_celestial_positions'tan gelen veriyi kullanabiliriz.
                ecl_lon = data["degree"]
                ecl_lat = data["latitude"]
                ecl_dist = data["distance"]
                ecl_coords = [ecl_lon, ecl_lat, ecl_dist]

                # Ecliptic koordinatlardan Horizon koordinatlarına dönüştür (azimuth, altitude)
                # swe.azalt(tjd_ut, SWE_ECL2HOR, geopos, atpress, attemp, xin)
                # xin: [lon, lat, dist] from swe.calc_ut
                # atpress, attemp: Atmosfer basıncı ve sıcaklığı, kırılma (refraction) için kullanılır. Varsayılan 0 kırılma yok.
                # Kırılma dahil: atpress=1013.25 (deniz seviyesi), attemp=15 (Celsius)
                atpress = 1013.25
                attemp = 15.0
                azalt_result = swe.azalt(
                    jd_ut, swe.ECL2HOR, geopos, atpress, attemp, ecl_coords
                )

                # result: (azimuth, true_altitude, apparent_altitude)
                if azalt_result and len(azalt_result) >= 3:
                    azimuth = azalt_result[0]
                    true_altitude = azalt_result[1]
                    apparent_altitude = azalt_result[2]

                    azalt_positions[body_name] = {
                        "azimuth": round(
                            azimuth, 2
                        ),  # Kuzey 0, Doğu 90, Güney 180, Batı 270
                        "true_altitude": round(
                            true_altitude, 2
                        ),  # Kırılma düzeltilmemiş
                        "apparent_altitude": round(
                            apparent_altitude, 2
                        ),  # Kırılma düzeltilmiş
                        "is_above_horizon": apparent_altitude
                        > 0,  # Ufuk üzerinde mi? (Kırılma dahil)
                    }
                    # logger.debug(f"{body_name} Az/Alt: {azalt_positions[body_name]}")

                else:
                    logger.warning(f"{body_name} Azimuth/Altitude hesaplanamadı.")
                    azalt_positions[body_name] = {
                        "azimuth": None,
                        "true_altitude": None,
                        "apparent_altitude": None,
                        "is_above_horizon": False,
                        "error": "Calculation failed",
                    }

            except Exception as e:
                logger.error(
                    f"{body_name} Azimuth/Altitude hesaplanırken hata: {str(e)}",
                    exc_info=True,
                )
                azalt_positions[body_name] = {
                    "azimuth": None,
                    "true_altitude": None,
                    "apparent_altitude": None,
                    "is_above_horizon": False,
                    "error": str(e),
                }
                continue

        logger.info(
            f"Azimuth ve Altitude hesaplamaları tamamlandı ({len(azalt_positions)} cisim için)."
        )
        return azalt_positions

    except Exception as e:
        logger.error(
            f"calculate_azimuth_altitude_for_bodies fonksiyonunda hata: {str(e)}",
            exc_info=True,
        )
        return {}


# Refraction hesaplaması (Yardımcı fonksiyon, doğrudan kullanılmayabilir)
def calculate_refraction(altitude, atpress=1013.25, attemp=15.0, flag=True):
    """Calculate refraction correction.

    Args:
        altitude (float): True or apparent altitude in degrees
        atpress (float): Atmospheric pressure in mbar/hPa
        attemp (float): Atmospheric temperature in Celsius
        flag (bool): True for true->apparent, False for apparent->true

    Returns:
        float: Converted altitude in degrees
    """
    try:
        # altitude float olmalı
        if not isinstance(altitude, (int, float)):
            return None

        return swe.refrac(
            float(altitude),
            float(atpress),
            float(attemp),
            swe.TRUE_TO_APP if flag else swe.APP_TO_TRUE,
        )
    except Exception as e:
        logger.error(f"Refraction calculation error: {str(e)}")
        return None


# JSON uyumluluğu için yardımcı fonksiyon
def ensure_json_serializable(obj):
    """Recursively converts objects to JSON serializable types."""
    if isinstance(obj, dict):
        return {str(k): ensure_json_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [ensure_json_serializable(elem) for elem in obj]
    elif isinstance(obj, tuple):
        return tuple(
            ensure_json_serializable(elem) for elem in obj
        )  # Tuple'lar genellikle JSON'da liste olur ama burada tuple olarak bırakalım
    elif isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    elif isinstance(obj, (datetime, date, time)):
        return obj.isoformat()  # Tarih/saat objelerini ISO formatında stringe çevir
    # Diğer olası Swisseph çıktı tipleri (örn. swe.error) veya hata objeleri stringe çevrilsin
    else:
        return str(obj)


# ------------------------------------------------------------------------------
# Ana Hesaplama Fonksiyonu
# ------------------------------------------------------------------------------


def calculate_astro_data(
    birth_date,
    birth_time,
    latitude,
    longitude,
    elevation_m=0,
    house_system=b"P",
    transit_info=None,
):
    """
    Verilen doğum tarihi, saati, konumu ve ev sistemine göre kapsamlı astrolojik veriyi hesaplar.

    Args:
        birth_date (str or date): Doğum tarihi (YYYY-MM-DD formatı veya date objesi)
        birth_time (str or time): Doğum saati (HH:MM formatı veya time objesi)
        latitude (float): Doğum yeri enlemi
        longitude (float): Doğum yeri boylamı
        elevation_m (float, optional): Doğum yeri yüksekliği metre cinsinden. Varsayılan 0.
        house_system (bytes or str, optional): Ev sistemi (örn. b"P" Porphyry, "R" Regiomontanus). Varsayılan Porphyry.
        transit_info (dict, optional): Transit hesaplamaları için özel bilgiler.
                                     {'date': 'YYYY-MM-DD', 'time': 'HH:MM:SS', 'latitude': float, 'longitude': float}
                                     formatında olabilir.

    Returns:
        dict: Kapsamlı astrolojik hesaplama sonuçlarını içeren sözlük.
    """
    # Giriş verilerini detaylı olarak logla
    logger.info("==== ASTROLOJIK HESAPLAMA BAŞLATILIYOR ====")
    logger.info(f"Doğum tarihi input: {repr(birth_date)} - Tip: {type(birth_date)}")
    logger.info(f"Doğum saati input: {repr(birth_time)} - Tip: {type(birth_time)}")
    logger.info(f"Enlem: {repr(latitude)} - Tip: {type(latitude)}")
    logger.info(f"Boylam: {repr(longitude)} - Tip: {type(longitude)}")
    logger.info(f"Yükseklik: {repr(elevation_m)} - Tip: {type(elevation_m)}")
    logger.info(f"Ev sistemi: {repr(house_system)} - Tip: {type(house_system)}")
    logger.info(f"Transit bilgisi: {repr(transit_info)}")

    logger.info(
        f"Astrolojik hesaplamalar başlatılıyor: {birth_date} {birth_time} @ Lat {latitude}, Lon {longitude}, Elev {elevation_m}m, System {house_system}"
    )
    if transit_info:
        logger.info(f"Sağlanan transit bilgisi: {transit_info}")

    try:
        # Giriş verilerini standart formatlara dönüştür
        if isinstance(birth_date, str):
            date_obj = datetime.strptime(birth_date, "%Y-%m-%d").date()
        elif isinstance(birth_date, date):
            date_obj = birth_date
        else:
            raise TypeError(
                "birth_date string (YYYY-MM-DD) veya date objesi olmalıdır."
            )

        if isinstance(birth_time, str):
            try:
                # Önce hatalı saat formatlarını düzelt
                time_str = birth_time.strip()
                # Eğer saat çift nokta ile bitiyorsa (HH: gibi), temizle
                if time_str.endswith(":00"):
                    time_str = time_str[:-3]
                elif time_str.endswith(":"):
                    time_str = time_str[:-1]

                # Farklı saat formatlarını dene
                try:
                    # HH:MM:SS formatı
                    time_obj = datetime.strptime(time_str, "%H:%M:%S").time()
                except ValueError:
                    try:
                        # HH:MM formatı
                        time_obj = datetime.strptime(time_str, "%H:%M").time()
                    except ValueError:
                        try:
                            # Sadece HH formatı
                            time_obj = datetime.strptime(time_str, "%H").time()
                        except ValueError:
                            # Saati parse edemezse varsayılan bir saat kullan (örn. 12:00)
                            logger.warning(
                                f"Doğum saati '{birth_time}' parse edilemedi, varsayılan 12:00:00 kullanılıyor."
                            )
                            time_obj = time(12, 0, 0)
            except Exception as e:
                logger.warning(
                    f"Doğum saati '{birth_time}' işlenirken hata: {str(e)}. Varsayılan 12:00:00 kullanılıyor."
                )
                time_obj = time(12, 0, 0)
        elif isinstance(birth_time, time):
            time_obj = birth_time
        else:
            # Saat bilgisi yoksa veya geçersizse 12:00 kullan
            logger.warning(
                f"Doğum saati geçersiz veya belirtilmedi, varsayılan 12:00:00 kullanılıyor."
            )
            time_obj = time(12, 0, 0)

        # house_system string ise bytes'a çevir
        if isinstance(house_system, str):
            house_system_bytes = house_system.encode("utf-8")
        elif isinstance(house_system, bytes):
            house_system_bytes = house_system
        else:
            logger.warning(
                f"Ev sistemi '{house_system}' geçersiz, varsayılan 'P' kullanılıyor."
            )
            house_system_bytes = b"P"

        # Doğum tarihi ve saatini birleştir (datetime objesi)
        birth_dt = datetime.combine(date_obj, time_obj)

        # Julian günü hesapla fonksiyonu - convert_to_jd
        def convert_to_jd(dt_obj):
            # GMT+3'ten UTC'ye çevir
            dt_utc = dt_obj - timedelta(hours=3)  # UTC+3 Local -> UTC

            # datetime'ı bileşenlere ayır ve saat/dakika/saniyeyi ondalık saate çevir
            hour_decimal = (
                dt_utc.hour + (dt_utc.minute / 60.0) + (dt_utc.second / 3600.0)
            )

            # Julian günü hesapla
            jd_ut = swe.julday(dt_utc.year, dt_utc.month, dt_utc.day, hour_decimal)
            return jd_ut

        # Güvenli Julian günü hesaplaması
        try:
            birth_jd = convert_to_jd(birth_dt)
            logger.info(f"Doğum tarihi/saati için Julian günü: {birth_jd}")
        except Exception as e:
            logger.error(f"Julian günü hesaplanırken hata: {str(e)}", exc_info=True)
            return {"error": f"Julian günü hesaplama hatası: {str(e)}"}

        # Transit hesaplamaları için kullanılacak tarih, saat ve konumu belirle
        current_dt = datetime.now()  # Varsayılan olarak şu anki tarih/saat
        transit_dt = current_dt  # Transit tarih/saat varsayılan olarak şu an
        transit_lat = float(latitude)  # Transit enlemi varsayılan olarak doğum yeri
        transit_lon = float(longitude)  # Transit boylamı varsayılan olarak doğum yeri

        # Transit bilgisi verilmişse güncelle
        if transit_info and isinstance(transit_info, dict):
            transit_date_str = transit_info.get("date")
            transit_time_str = transit_info.get(
                "time", "12:00:00"
            )  # Saat yoksa öğlen 12 varsay
            transit_lat_str = transit_info.get("latitude")
            transit_lon_str = transit_info.get("longitude")

            # Transit tarih/saat bilgisi
            if transit_date_str:
                try:
                    transit_dt_date_part = datetime.strptime(
                        transit_date_str, "%Y-%m-%d"
                    ).date()
                    try:
                        # Transit saati işlerken de aynı düzeltmeyi uygulayalım
                        transit_time_str = transit_time_str.strip()
                        # Çift nokta ile bitiyorsa temizle
                        if transit_time_str.endswith(":"):
                            transit_time_str = transit_time_str[:-1]

                        try:
                            # HH:MM:SS formatı
                            transit_dt_time_part = datetime.strptime(
                                transit_time_str, "%H:%M:%S"
                            ).time()
                        except ValueError:
                            try:
                                # HH:MM formatı
                                transit_dt_time_part = datetime.strptime(
                                    transit_time_str, "%H:%M"
                                ).time()
                            except ValueError:
                                try:
                                    # Sadece HH formatı
                                    transit_dt_time_part = datetime.strptime(
                                        transit_time_str, "%H"
                                    ).time()
                                except ValueError:
                                    logger.warning(
                                        f"Transit saati '{transit_time_str}' parse edilemedi, varsayılan 12:00:00 kullanılıyor."
                                    )
                                    transit_dt_time_part = time(12, 0, 0)
                    except Exception as e:
                        logger.warning(
                            f"Transit saati '{transit_time_str}' işlenirken hata: {str(e)}. Varsayılan 12:00:00 kullanılıyor."
                        )
                        transit_dt_time_part = time(12, 0, 0)
                    transit_dt = datetime.combine(
                        transit_dt_date_part, transit_dt_time_part
                    )
                    logger.info(f"Transit hesaplamaları için tarih/saat: {transit_dt}")
                except ValueError:
                    logger.warning(
                        f"Sağlanan transit tarihi '{transit_date_str}' geçersiz. Varsayılan (mevcut zaman) kullanılacak."
                    )

            # Transit konum bilgisi
            if transit_lat_str is not None:
                try:
                    transit_lat = float(transit_lat_str)
                    logger.info(f"Transit hesaplamaları için enlem: {transit_lat}")
                except ValueError:
                    logger.warning(
                        f"Sağlanan transit enlemi '{transit_lat_str}' geçersiz. Varsayılan (natal enlem) kullanılacak."
                    )

            if transit_lon_str is not None:
                try:
                    transit_lon = float(transit_lon_str)
                    logger.info(f"Transit hesaplamaları için boylam: {transit_lon}")
                except ValueError:
                    logger.warning(
                        f"Sağlanan transit boylamı '{transit_lon_str}' geçersiz. Varsayılan (natal boylam) kullanılacak."
                    )

        # Sonuç sözlüğünü oluştur
        result = {
            "birth_info": {
                "datetime": birth_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "location": {
                    "latitude": float(latitude),
                    "longitude": float(longitude),
                    "elevation_m": float(elevation_m)
                    if elevation_m is not None
                    else 0.0,
                },
                "house_system": house_system_bytes.decode("utf-8"),
                "assumed_utc_offset_for_jd_calc": "+3 hours",  # Eğer GMT+3 Local -> UT dönüşümü yapılıyorsa
            },
            "transit_info": {
                "datetime": transit_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "location": {"latitude": transit_lat, "longitude": transit_lon},
            },
        }

        #####################################################
        # 1. NATAL HARITA HESAPLAMALARI
        #####################################################
        logger.info("1. NATAL HARITA HESAPLAMALARI BAŞLIYOR")

        # 1.1 Natal Evler ve Açılar
        natal_houses_data = calculate_houses(
            birth_dt, latitude, longitude, house_system_bytes
        )
        if natal_houses_data.get("error"):
            logger.error(
                f"Natal evler hesaplanırken hata: {natal_houses_data['error']}"
            )
            return {"error": f"Natal evler hesaplanamadı: {natal_houses_data['error']}"}
        result["natal_houses"] = natal_houses_data

        # Ev cusplarının string key'lere sahip olduğundan emin olalım
        if "house_cusps" in result["natal_houses"]:
            result["natal_houses"]["house_cusps"] = convert_house_data_to_strings(
                result["natal_houses"]["house_cusps"]
            )

        # Yükselen derecesini al
        natal_asc_degree = natal_houses_data.get("important_angles", {}).get(
            "ascendant"
        )
        if natal_asc_degree is not None:
            result["natal_ascendant"] = {
                "degree": natal_asc_degree,
                "sign": get_zodiac_sign(natal_asc_degree),
                "degree_in_sign": round(get_degree_in_sign(natal_asc_degree), 2),
                "decan": get_decan(get_degree_in_sign(natal_asc_degree)),
            }
        else:
            result["natal_ascendant"] = {"error": "Ascendant hesaplanamadı."}

        # 1.2 Natal Gezegen Pozisyonları
        natal_planet_positions = calculate_natal_planet_positions(
            birth_dt, natal_houses_data.get("house_cusps", {})
        )
        if not natal_planet_positions:
            logger.error("Natal gezegen pozisyonları boş döndü.")
            return {"error": "Natal gezegen pozisyonları hesaplanamadı."}
        result["natal_planet_positions"] = natal_planet_positions

        # 1.3 Natal Ek Noktalar (Asteroidler, Düğümler, Lilith vb.)
        natal_additional_points = calculate_natal_additional_points(
            birth_dt, natal_houses_data.get("house_cusps", {})
        )
        result["natal_additional_points"] = natal_additional_points

        # 1.4 Tüm Natal Göksel Cisimleri Birleştir (açılar, antiscia, midpoint vb. için)
        all_natal_celestial_positions = {}
        all_natal_celestial_positions.update(natal_planet_positions)
        all_natal_celestial_positions.update(natal_additional_points)

        # Önemli açıları (Asc, MC vb.) da ekle
        if natal_houses_data.get("important_angles"):
            for angle_name, angle_deg in natal_houses_data["important_angles"].items():
                if angle_deg is not None:
                    name = "MC" if angle_name == "mc" else angle_name.capitalize()
                    angle_data = {
                        "degree": angle_deg,
                        "sign": get_zodiac_sign(angle_deg),
                        "degree_in_sign": round(get_degree_in_sign(angle_deg), 2),
                        "is_angle": True,
                    }
                    all_natal_celestial_positions[name] = angle_data
                    # Template'in görebilmesi için ana sözlüğe ekle
                    result["natal_planet_positions"][name] = angle_data

        # 1.5 Natal Açılar (Natal-Natal arası)
        natal_aspects = calculate_aspects(all_natal_celestial_positions)
        result["natal_aspects"] = natal_aspects

        # 1.6 Natal Azimuth/Altitude
        natal_azimuth_altitude = calculate_azimuth_altitude_for_bodies(
            birth_dt, latitude, longitude, elevation_m, natal_planet_positions
        )
        result["natal_azimuth_altitude"] = natal_azimuth_altitude

        # 1.7 Natal Sabit Yıldızlar
        natal_fixed_stars = calculate_fixed_stars(birth_dt)
        result["natal_fixed_stars"] = natal_fixed_stars

        # 1.8 Natal Antiscia ve Contra-antiscia
        natal_antiscia = calculate_antiscia(all_natal_celestial_positions)
        result["natal_antiscia"] = natal_antiscia

        # 1.9 Natal Dignity/Debility Skorları
        natal_dignity_scores = calculate_dignity_scores(natal_planet_positions)
        result["natal_dignity_scores"] = natal_dignity_scores

        # 1.10 Natal Part of Fortune
        if (
            natal_asc_degree is not None
            and natal_planet_positions.get("Sun")
            and natal_planet_positions.get("Moon")
        ):
            natal_part_of_fortune = calculate_part_of_fortune(
                birth_dt, latitude, longitude, natal_planet_positions, natal_asc_degree
            )
            result["natal_part_of_fortune"] = natal_part_of_fortune
        else:
            result["natal_part_of_fortune"] = {
                "error": "Part of Fortune hesaplama için gerekli veriler eksik (Asc, Güneş veya Ay)."
            }

        # 1.11 Natal Arap Noktaları
        if natal_asc_degree is not None:
            natal_arabic_parts = calculate_arabic_parts(
                birth_dt, natal_planet_positions, natal_asc_degree
            )
            result["natal_arabic_parts"] = natal_arabic_parts
        else:
            result["natal_arabic_parts"] = {
                "error": "Ascendant hesaplanamadığı için Arap Noktaları hesaplanamadı."
            }

        # 1.12 Natal Lunation Cycle
        if natal_planet_positions.get("Sun") and natal_planet_positions.get("Moon"):
            natal_lunation_cycle = calculate_lunation_cycle(
                birth_dt, natal_planet_positions
            )
            result["natal_lunation_cycle"] = natal_lunation_cycle
        else:
            result["natal_lunation_cycle"] = {
                "error": "Lunation Cycle hesaplama için Güneş veya Ay pozisyonu eksik."
            }

        # 1.13 Natal Deklinasyonlar
        natal_declinations = calculate_declinations(birth_dt, natal_planet_positions)
        result["natal_declinations"] = natal_declinations

        # 1.14 Natal Midpoint Analizi
        natal_midpoint_analysis = get_midpoint_aspects(all_natal_celestial_positions)
        result["natal_midpoint_analysis"] = natal_midpoint_analysis

        # 1.15 Natal Harmonik Analiz
        deep_harmonic_analysis = calculate_deep_harmonic_analysis(
            birth_dt, all_natal_celestial_positions
        )
        result["deep_harmonic_analysis"] = deep_harmonic_analysis
        result["navamsa_chart"] = deep_harmonic_analysis.get("H9", {})

        # 1.16 Natal Vimshottari Dasa
        if natal_planet_positions.get("Moon"):
            natal_moon_degree = natal_planet_positions["Moon"].get("degree")
            vimshottari_dasa = get_vimshottari_dasa(birth_dt, natal_moon_degree)
            result["vimshottari_dasa"] = vimshottari_dasa
        else:
            result["vimshottari_dasa"] = {
                "error": "Ay pozisyonu eksik, Vimshottari Dasa hesaplanamadı."
            }

        # 1.17 Natal Firdaria Periyotları
        if natal_planet_positions.get("Sun"):
            natal_sun_pos = natal_planet_positions["Sun"]
            firdaria_periods = get_firdaria_period(
                birth_dt, natal_sun_pos, natal_houses_data
            )
            result["firdaria_periods"] = firdaria_periods
        else:
            result["firdaria_periods"] = {
                "error": "Güneş pozisyonu eksik, Firdaria periyotları hesaplanamadı."
            }

        # 1.18 Natal Özet Yorumu
        natal_summary_interpretation = get_natal_summary(
            natal_planet_positions, natal_houses_data, birth_dt
        )
        result["natal_summary_interpretation"] = natal_summary_interpretation

        # 1.19 Natal Tutulmalar (Doğum civarı)
        eclipse_search_start_birth = birth_dt - timedelta(days=365)
        eclipse_search_end_birth = birth_dt + timedelta(days=365)
        eclipses_nearby_birth = find_eclipses_in_range(
            eclipse_search_start_birth, eclipse_search_end_birth
        )
        result["eclipses_nearby_birth"] = eclipses_nearby_birth

        logger.info("1. NATAL HARITA HESAPLAMALARI TAMAMLANDI")

        #####################################################
        # 2. TRANSIT HARITA HESAPLAMALARI
        #####################################################
        logger.info("2. TRANSIT HARITA HESAPLAMALARI BAŞLIYOR")

        # YENİ: Tüm transit analizini tek fonksiyonla al
        transit_data = calculate_transit_data(
            transit_dt, transit_lat, transit_lon, elevation_m
        )
        result.update(transit_data)

        logger.info("2. TRANSIT HARITA HESAPLAMALARI TAMAMLANDI")

        # --- TRANSIT TO NATAL ASPECTS ---
        if "transit_positions" in result and "natal_planet_positions" in result:
            transit_to_natal_aspects = calculate_aspects(
                result["transit_positions"], result["natal_planet_positions"]
            )
            result["transit_to_natal_aspects"] = transit_to_natal_aspects
        else:
            result["transit_to_natal_aspects"] = []

        #####################################################
        # 3. PROGRESYON HESAPLAMALARI
        #####################################################
        logger.info("3. PROGRESYON HESAPLAMALARI BAŞLIYOR")

        # YENİ: Tüm progresyon analizini tek fonksiyonla al
        progression_data = calculate_progression_data(
            birth_dt, transit_dt, latitude, longitude, natal_planet_positions
        )
        result.update(progression_data)

        logger.info("3. PROGRESYON HESAPLAMALARI TAMAMLANDI")

        #####################################################
        # 4. RETURN HARITA HESAPLAMALARI
        #####################################################
        logger.info("4. RETURN HARITA HESAPLAMALARI BAŞLIYOR")

        # 4.1 Solar Return Haritası
        solar_return_chart_data = calculate_solar_return_chart(
            birth_dt, transit_dt, latitude, longitude
        )
        result["solar_return_chart"] = solar_return_chart_data

        # 4.2 Lunar Return Haritası
        lunar_return_chart_data = calculate_lunar_return_chart(
            birth_dt, transit_dt, latitude, longitude
        )
        result["lunar_return_chart"] = lunar_return_chart_data

        logger.info("4. RETURN HARITA HESAPLAMALARI TAMAMLANDI")

        #####################################################
        # 5. HARMONİK ANALİZLER
        #####################################################
        logger.info("5. HARMONİK ANALİZLER BAŞLIYOR")

        harmonic_data = calculate_harmonic_data(birth_dt, all_natal_celestial_positions)
        result.update(harmonic_data)

        logger.info("5. HARMONİK ANALİZLER TAMAMLANDI")

        #####################################################
        # 6. EK HESAPLAMALAR
        #####################################################
        logger.info("6. EK HESAPLAMALAR BAŞLIYOR")

        # 6.1 Transit Civarı Tutulmalar
        eclipse_search_start_current = transit_dt - timedelta(days=180)
        eclipse_search_end_current = transit_dt + timedelta(days=180)
        eclipses_nearby_current = find_eclipses_in_range(
            eclipse_search_start_current, eclipse_search_end_current
        )
        result["eclipses_nearby_current"] = eclipses_nearby_current

        logger.info("6. EK HESAPLAMALAR TAMAMLANDI")

        logger.info("Tüm astrolojik hesaplamalar tamamlandı.")

        # Sonucu JSON uyumlu hale getir
        final_result = ensure_json_serializable(result)
        for i, (category, data) in enumerate(result.items()):
            color = COLOR_LIST[i % len(COLOR_LIST)]

            json_line = json.dumps(data, ensure_ascii=False, separators=(", ", ": "))

            print(f"{BOLD}{color}[{category.upper()}]{RESET} {json_line}")

        return final_result

    except Exception as e:
        logger.error(
            f"Genel hesaplama fonksiyonunda kritik hata: {str(e)}", exc_info=True
        )
        # Ana fonksiyonda hata olursa bir hata nesnesi döndür
        return {"error": f"Hesaplamalar sırasında kritik bir hata oluştu: {str(e)}"}


def calculate_house_for_degree(
    degree, birth_dt, latitude, longitude, house_system=b"P"
):
    """
    Verilen derecenin hangi evde olduğunu hesaplar.

    Args:
        degree (float): Hesaplanacak derece (0-360)
        birth_dt (datetime): Doğum tarihi
        latitude (float): Enlem
        longitude (float): Boylam
        house_system (bytes): Ev sistemi (default: b"P" Porphyry)

    Returns:
        int: Ev numarası (1-12)
    """
    try:
        # Datetime'ı Julian güne çevir
        dt_utc = birth_dt - timedelta(hours=3)  # UTC+3 Local -> UTC
        jd_ut = swe.julday(
            dt_utc.year,
            dt_utc.month,
            dt_utc.day,
            dt_utc.hour + dt_utc.minute / 60.0 + dt_utc.second / 3600.0,
        )

        # Ev cusplarını hesapla
        houses = swe.houses(jd_ut, float(latitude), float(longitude), house_system)
        cusps = houses[0]  # Ev başlangıç dereceleri

        # Derecenin hangi evde olduğunu bul
        for i in range(12):
            start = cusps[i]
            end = cusps[i + 1] if i < 11 else cusps[0]

            if start <= degree < end or (i == 11 and degree >= start):
                return i + 1
            elif start > end and (degree >= start or degree < end):
                return i + 1

        return 1  # Varsayılan olarak 1. ev

    except Exception as e:
        logger.error(f"Ev hesaplama hatası: {str(e)}")
        return 1  # Hata durumunda varsayılan 1. ev


def calculate_lunation_cycle(birth_dt, natal_planet_positions):
    """
    Doğum anındaki Ay fazını hesaplar.

    Args:
        birth_dt (datetime): Doğum tarihi ve saati
        natal_planet_positions (dict): Natal gezegen pozisyonları

    Returns:
        dict: Ay fazı bilgileri
    """
    try:
        # Güneş ve Ay pozisyonlarını al
        sun_pos = natal_planet_positions.get("Sun", {})
        moon_pos = natal_planet_positions.get("Moon", {})

        if not sun_pos or not moon_pos:
            return {"error": "Güneş veya Ay pozisyonu eksik"}

        sun_degree = sun_pos.get("degree", 0)
        moon_degree = moon_pos.get("degree", 0)

        # Faz açısını hesapla
        prog_sun_deg = (sun_degree + 360) % 360
        prog_moon_deg = (moon_degree + 360) % 360

        phase_angle = (prog_moon_deg - prog_sun_deg) % 360
        phase_angle_in_sign = get_degree_in_sign(phase_angle)
        phase_sign = get_zodiac_sign(phase_angle)
        phase_degree_in_sign = round(phase_angle % 30, 2)
        phase_name = get_phase_name(phase_angle)
        return {
            "phase_angle": phase_angle,
            "phase_sign": phase_sign,
            "phase_degree_in_sign": phase_degree_in_sign,
            "phase_name": phase_name,
        }
    except Exception as e:
        logger.error(f"Ay fazı hesaplama hatası: {str(e)}")
        return {"error": f"Ay fazı hesaplanamadı: {str(e)}"}


def calculate_declinations(birth_dt, natal_planet_positions):
    """
    Verilen doğum tarihi ve gezegen pozisyonlarına göre deklinasyonları hesaplar.

    Args:
        birth_dt (datetime): Doğum tarihi ve saati
        natal_planet_positions (dict): Natal gezegen pozisyonları
    Returns:
        dict: Deklinasyon bilgileri
    """
    try:
        declinations = {}
        for planet, pos in natal_planet_positions.items():
            if "degree" in pos:
                degree = pos["degree"]
                # Deklinasyon hesaplama formülü (basit bir örnek)
                declination = round(
                    math.sin(math.radians(degree)) * 90, 2
                )  # Basit bir formül
                declinations[planet] = {
                    "declination": declination,
                    "sign": get_zodiac_sign(declination),
                    "degree_in_sign": round(get_degree_in_sign(declination), 2),
                }
        return declinations
    except Exception as e:
        logger.error(f"Deklinasyon hesaplama hatası: {str(e)}")
        return {"error": f"Deklinasyon hesaplanamadı: {str(e)}"}


def get_phase_name(phase_angle):
    """
    Faz açısına göre Ay fazını isimlendirir.

    Args:
        phase_angle (float): Faz açısı (0-360)

    Returns:
        str: Ay fazı ismi
    """
    if phase_angle < 0 or phase_angle >= 360:
        raise ValueError("Faz açısı 0 ile 360 arasında olmalıdır.")

    if phase_angle < 45:
        return "Yeni Ay"
    elif phase_angle < 135:
        return "İlk Dördün"
    elif phase_angle < 225:
        return "Dolunay"
    elif phase_angle < 315:
        return "Son Dördün"
    else:
        return "Yeni Ay"


def calculate_part_of_fortune(
    birth_dt, latitude, longitude, natal_planet_positions, asc_degree
):
    """
    Part of Fortune pozisyonunu hesaplar.

    Args:
        birth_dt (datetime): Doğum tarihi ve saati
        latitude (float): Doğum yeri enlemi
        longitude (float): Doğum yeri boylamı
        natal_planet_positions (dict): Natal gezegen pozisyonları
        asc_degree (float): Yükselen burç derecesi

    Returns:
        dict: Part of Fortune pozisyon bilgileri
    """
    try:
        # Güneş ve Ay pozisyonlarını al
        sun_pos = natal_planet_positions.get("Sun", {})
        moon_pos = natal_planet_positions.get("Moon", {})

        if not sun_pos or not moon_pos:
            return {"error": "Güneş veya Ay pozisyonu eksik"}

        sun_degree = sun_pos.get("degree", 0)
        moon_degree = moon_pos.get("degree", 0)

        # Part of Fortune formülü: ASC + Moon - Sun (Gündüz doğumlar için)
        # Gece doğumlar için: ASC + Sun - Moon
        is_daytime = birth_dt.hour >= 6 and birth_dt.hour < 18
        if is_daytime:
            pof_degree = (asc_degree + moon_degree - sun_degree) % 360
        else:
            pof_degree = (asc_degree + sun_degree - moon_degree) % 360

        return {
            "degree": pof_degree,
            "sign": get_zodiac_sign(pof_degree),
            "degree_in_sign": round(get_degree_in_sign(pof_degree), 2),
            "house": calculate_house_for_degree(
                pof_degree, birth_dt, latitude, longitude
            ),
        }

    except Exception as e:
        logger.error(f"Part of Fortune hesaplama hatası: {str(e)}", exc_info=True)
        return {"error": f"Part of Fortune hesaplanamadı: {str(e)}"}


def calculate_arabic_parts(birth_dt, natal_planet_positions, asc_degree):
    """
    Arap Noktalarını hesaplar.

    Args:
        birth_dt (datetime): Doğum tarihi ve saati
        natal_planet_positions (dict): Natal gezegen pozisyonları
        asc_degree (float): Yükselen burç derecesi

    Returns:
        dict: Arap Noktası pozisyon bilgileri
    """
    try:
        arabic_parts = {}

        # Güneş ve Ay pozisyonlarını al
        sun_pos = natal_planet_positions.get("Sun", {})
        moon_pos = natal_planet_positions.get("Moon", {})

        if not sun_pos or not moon_pos:
            return {"error": "Güneş veya Ay pozisyonu eksik"}

        sun_degree = sun_pos.get("degree", 0)
        moon_degree = moon_pos.get("degree", 0)

        # Arap Noktası formülü: ASC + Moon - Sun (Gündüz doğumlar için)
        # Gece doğumlar için: ASC + Sun - Moon
        is_daytime = birth_dt.hour >= 6 and birth_dt.hour < 18
        if is_daytime:
            part_of_fortune_degree = (asc_degree + moon_degree - sun_degree) % 360
        else:
            part_of_fortune_degree = (asc_degree + sun_degree - moon_degree) % 360

        latitude = birth_dt.latitude if hasattr(birth_dt, "latitude") else 0
        longitude = birth_dt.longitude if hasattr(birth_dt, "longitude") else 0
        # Part of Fortune hesapla
        # Part of Fortune formülü: ASC + Moon - Sun (Gündüz doğumlar için)
        # Gece doğumlar için: ASC + Sun - Moon
        # Güneş ve Ay pozisyonlarını al
        # Güneş ve Ay pozisyonlarını al
        # Güneş ve Ay pozisyonlarını al
        arabic_parts["Part of Fortune"] = {
            "degree": part_of_fortune_degree,
            "sign": get_zodiac_sign(part_of_fortune_degree),
            "degree_in_sign": round(get_degree_in_sign(part_of_fortune_degree), 2),
            "house": calculate_house_for_degree(
                part_of_fortune_degree, birth_dt, latitude, longitude
            ),
        }

        # Diğer Arap Noktaları hesaplamaları burada yapılabilir

        return arabic_parts

    except Exception as e:
        logger.error(f"Arap Noktası hesaplama hatası: {str(e)}", exc_info=True)
        return {"error": f"Arap Noktası hesaplanamadı: {str(e)}"}


# Dosya sonu işareti (isteğe bağlı)
# ------------------------------------------------------------------------------


def calculate_transit_data(transit_dt, latitude, longitude, elevation_m=0):
    """Transit gezegen pozisyonları, evler ve açılar dahil eksiksiz transit analizini döndürür."""
    try:
        # Gezegen pozisyonları ve evler
        transit_positions, transit_houses_data = get_transit_positions(
            transit_dt, latitude, longitude
        )
        # Transit açılar (transit-transit)
        transit_aspects = calculate_aspects(transit_positions)
        # Transit azimuth/altitude
        transit_azimuth_altitude = calculate_azimuth_altitude_for_bodies(
            transit_dt, latitude, longitude, elevation_m, transit_positions
        )
        return {
            "transit_positions": transit_positions,
            "transit_houses": transit_houses_data,
            "transit_aspects": transit_aspects,
            "transit_azimuth_altitude": transit_azimuth_altitude,
        }
    except Exception as e:
        logger.error(f"Transit analiz hesaplama hatası: {str(e)}", exc_info=True)
        return {
            "transit_positions": {},
            "transit_houses": {},
            "transit_aspects": [],
            "transit_azimuth_altitude": {},
        }


def calculate_progression_data(
    birth_dt, transit_dt, latitude, longitude, natal_planet_positions
):
    """Progresyon (sekonder ve solar arc) pozisyonları, evler ve açılar dahil eksiksiz progresyon analizini döndürür."""
    try:
        # Sekonder progresyonlar ve evler
        secondary_progressions, progressed_houses_data = (
            calculate_secondary_progressions(birth_dt, transit_dt, latitude, longitude)
        )
        # Progresif açılar (progresyon-progresyon)
        progressed_aspects = calculate_aspects(secondary_progressions)
        # Progresif Ay fazı
        progressed_moon_phase = calculate_progressed_moon_phase(secondary_progressions)
        # Solar Arc progresyonları
        solar_arc_progressions = get_solar_arc_progressions(
            birth_dt, transit_dt, natal_planet_positions
        )
        return {
            "secondary_progressions": secondary_progressions,
            "progressed_houses": progressed_houses_data,
            "progressed_aspects": progressed_aspects,
            "progressed_moon_phase": progressed_moon_phase,
            "solar_arc_progressions": solar_arc_progressions,
        }
    except Exception as e:
        logger.error(f"Progresyon analiz hesaplama hatası: {str(e)}", exc_info=True)
        return {
            "secondary_progressions": {},
            "progressed_houses": {},
            "progressed_aspects": [],
            "progressed_moon_phase": {},
            "solar_arc_progressions": {},
        }


def calculate_harmonic_data(birth_dt, natal_celestial_positions):
    """Harmonik analizler (çoklu harmonik haritalar ve navamsa) eksiksiz döndürülür."""
    try:
        deep_harmonic_analysis = calculate_deep_harmonic_analysis(
            birth_dt, natal_celestial_positions
        )
        navamsa_chart = deep_harmonic_analysis.get("H9", {})
        return {
            "deep_harmonic_analysis": deep_harmonic_analysis,
            "navamsa_chart": navamsa_chart,
        }
    except Exception as e:
        logger.error(f"Harmonik analiz hesaplama hatası: {str(e)}", exc_info=True)
        return {"deep_harmonic_analysis": {}, "navamsa_chart": {}}
