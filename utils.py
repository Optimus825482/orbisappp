"""
Utility Functions Module
========================

Bu modül, tekrarlanan kodları ve helper fonksiyonları içerir.
Tüm modüller tarafından kullanılabilir.

İçerik:
- Time parsing fonksiyonları
- Date/datetime conversion utilities
- Constants ve magic numbers
- Common helpers
"""

from datetime import datetime, time, date
from typing import Union, Optional, Any
from functools import singledispatch
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS - Magic Number'ları ortak bir yerde topluyoruz
# =============================================================================
class Constants:
    """Uygulama genelindeki sabit değerler."""
    
    # Time Constants
    DEFAULT_TIME = time(12, 0)  # Varsayılan saat: 12:00
    TIME_FORMATS = ["%H:%M:%S", "%H:%M", "%H"]  # Desteklenen zaman formatları
    
    # Session Constants
    SESSION_LIFETIME_HOURS = 1  # Session lifetime (hours)
    SESSION_TIMEOUT_SECONDS = 3600  # Session timeout (seconds)
    
    # Cache TTL Constants
    CACHE_TTL_AI_INTERPRETATION = 3600  # 1 hour
    CACHE_TTL_LOCATION_SEARCH = 86400  # 24 hours
    CACHE_TTL_ASTRO_CALCULATION = 1800  # 30 minutes
    
    # API Constants
    API_TIMEOUT_SHORT = 5  # 5 seconds
    API_TIMEOUT_MEDIUM = 10  # 10 seconds
    API_TIMEOUT_LONG = 30  # 30 seconds
    
    # Pagination Constants
    MAX_SESSION_FILES = 100
    DEFAULT_RESULTS_LIMIT = 10
    
    # File Mode Constants
    SESSION_FILE_MODE = 0o600  # Session dosyası izinleri
    
    # Astrology Constants
    DEFAULT_HOUSE_SYSTEM = b"P"  # Porphyry (default)
    ZODIAC_SIGNS = [
        "Koç", "Boğa", "İkizler", "Yengeç", "Aslan", "Başak",
        "Terazi", "Akrep", "Yay", "Oğlak", "Kova", "Balık"
    ]
    
    # Planet Symbols
    PLANET_SYMBOLS = {
        "Sun": "☉", "Moon": "☽", "Mercury": "☿", "Venus": "♀",
        "Mars": "♂", "Jupiter": "♃", "Saturn": "♄", "Uranus": "♅",
        "Neptune": "♆", "Pluto": "♇"
    }
    
    # Element Classes
    ELEMENT_FIRE = ["Koç", "Aslan", "Yay", "Aries", "Leo", "Sagittarius"]
    ELEMENT_EARTH = ["Boğa", "Başak", "Oğlak", "Taurus", "Virgo", "Capricorn"]
    ELEMENT_AIR = ["İkizler", "Terazi", "Kova", "Gemini", "Libra", "Aquarius"]
    ELEMENT_WATER = ["Yengeç", "Akrep", "Balık", "Cancer", "Scorpio", "Pisces"]


# =============================================================================
# TIME PARSING UTILITIES
# =============================================================================
def parse_time_flexible(time_str: str) -> time:
    """
    Esnek zaman parsing fonksiyonu.
    Farklı formatları destekler: "HH:MM:SS", "HH:MM", "HH"
    
    Args:
        time_str: Zaman string'i
        
    Returns:
        datetime.time objesi
        
    Examples:
        >>> parse_time_flexible("14:30:45")
        datetime.time(14, 30, 45)
        >>> parse_time_flexible("14:30")
        datetime.time(14, 30)
        >>> parse_time_flexible("14")
        datetime.time(14, 0)
    """
    if not time_str:
        return Constants.DEFAULT_TIME
    
    # String'i temizle
    time_str = time_str.strip()
    
    # Gereksiz :00 ve : suffix'lerini kaldır
    if time_str.endswith(":00"):
        time_str = time_str[:-3]
    elif time_str.endswith(":"):
        time_str = time_str[:-1]
    
    # Farklı formatları dene
    for fmt in Constants.TIME_FORMATS:
        try:
            return datetime.strptime(time_str, fmt).time()
        except ValueError:
            continue
    
    # Hiçbiri uyşmadı - log yap ve varsayılan döndür
    logger.warning(f"Geçersiz saat formatı: '{time_str}', varsayılan {Constants.DEFAULT_TIME.strftime('%H:%M')} kullanılıyor")
    return Constants.DEFAULT_TIME


def parse_date_flexible(date_str: str) -> Optional[date]:
    """
    Esnek tarih parsing fonksiyonu.
    
    Args:
        date_str: Tarih string'i
        
    Returns:
        datetime.date objesi veya None
    """
    if not date_str:
        return None
    
    # Desteklenen formatlar
    formats = [
        "%Y-%m-%d",  # ISO format
        "%d/%m/%Y",  # Turkish format
        "%d.%m.%Y",  # German format
        "%m/%d/%Y",  # US format
    ]
    
    date_str = date_str.strip()
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    
    logger.error(f"Geçersiz tarih formatı: '{date_str}'")
    return None


# =============================================================================
# DATETIME CONVERSION UTILITIES - singledispatch ile type-safe
# =============================================================================
@singledispatch
def convert_times_to_str(obj: Any) -> Any:
    """
    Tüm dict/list içindeki datetime.time ve datetime.date objelerini stringe çevirir.
    singledispatch ile type-safe ve performanslı.
    
    Args:
        obj: Herhangi bir obje
        
    Returns:
        String'e çevrilmiş obje veya orijinal obje
    """
    return obj


@convert_times_to_str.register(dict)
def _(obj: dict) -> dict:
    """Dict objelerini recursive olarak çevir."""
    return {k: convert_times_to_str(v) for k, v in obj.items()}


@convert_times_to_str.register(list)
def _(obj: list) -> list:
    """List objelerini recursive olarak çevir."""
    return [convert_times_to_str(i) for i in obj]


@convert_times_to_str.register(tuple)
def _(obj: tuple) -> tuple:
    """Tuple objelerini recursive olarak çevir."""
    return tuple(convert_times_to_str(i) for i in obj)


@convert_times_to_str.register(time)
def _(obj: time) -> str:
    """datetime.time objesini string'e çevir."""
    return obj.strftime("%H:%M")


@convert_times_to_str.register(date)
def _(obj: date) -> str:
    """datetime.date objesini string'e çevir."""
    return obj.strftime("%Y-%m-%d")


@convert_times_to_str.register(datetime)
def _(obj: datetime) -> str:
    """datetime.datetime objesini string'e çevir."""
    return obj.strftime("%Y-%m-%d %H:%M")


# =============================================================================
# JINJA2 FILTERS
# =============================================================================
def format_date(value, format="%d/%m/%Y"):
    """Jinja2 date formatting helper."""
    if value is None:
        return ""
    if isinstance(value, str):
        try:
            value = datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            return value
    return value.strftime(format)


def format_time(value, format="%H:%M"):
    """Jinja2 time formatting helper."""
    if value is None:
        return ""
    if isinstance(value, str):
        try:
            value = datetime.strptime(value, "%H:%M").time()
        except ValueError:
            return value
    return value.strftime(format)


def safe_round(value, decimals=2):
    """Jinja2 rounding helper."""
    try:
        if value is None:
            return "-"
        return round(float(value), decimals)
    except (ValueError, TypeError):
        return "-"


# =============================================================================
# ASTROLOGY UTILITIES
# =============================================================================
def get_element_class(sign_name: str) -> str:
    """
    Burç ismine göre element sınıfını döndürür.
    
    Args:
        sign_name: Burç adı (Türkçe veya İngilizce)
        
    Returns:
        Element sınıfı: "fire", "earth", "air", "water" veya ""
        
    Examples:
        >>> get_element_class("Koç")
        'fire'
        >>> get_element_class("Boğa")
        'earth'
        >>> get_element_class("Aries")
        'fire'
    """
    if not sign_name:
        return ""
    
    sign_lower = sign_name.lower()
    
    if sign_lower in [s.lower() for s in Constants.ELEMENT_FIRE]:
        return "fire"
    elif sign_lower in [s.lower() for s in Constants.ELEMENT_EARTH]:
        return "earth"
    elif sign_lower in [s.lower() for s in Constants.ELEMENT_AIR]:
        return "air"
    elif sign_lower in [s.lower() for s in Constants.ELEMENT_WATER]:
        return "water"
    else:
        return ""


def get_planet_symbol(planet_name: str) -> str:
    """
    Gezegen adından sembol döndürür.
    
    Args:
        planet_name: Gezegen adı
        
    Returns:
        Gezegen sembolü veya orijinal isim
    """
    return Constants.PLANET_SYMBOLS.get(planet_name, planet_name)


def get_zodiac_sign(degree: float) -> str:
    """
    Dereceye göre Zodyak burcunu döndürür.
    
    Args:
        degree: Derece (0-360 arası)
        
    Returns:
        Burç adı
    """
    degree = float(degree) % 360  # Normalize to 0-360
    
    signs = [
        (0, "Koç"), (30, "Boğa"), (60, "İkizler"), (90, "Yengeç"),
        (120, "Aslan"), (150, "Başak"), (180, "Terazi"), (210, "Akrep"),
        (240, "Yay"), (270, "Oğlak"), (300, "Kova"), (330, "Balık")
    ]
    
    for sign_degree, sign_name in reversed(signs):
        if degree >= sign_degree:
            return sign_name
    
    return "Bilinmeyen"


# =============================================================================
# VALIDATION UTILITIES
# =============================================================================
def validate_coordinates(latitude: float, longitude: float) -> bool:
    """
    Koordinatları doğrular.
    
    Args:
        latitude: Enlem (-90 ile 90 arası)
        longitude: Boylam (-180 ile 180 arası)
        
    Returns:
        True if valid, False otherwise
    """
    try:
        lat = float(latitude)
        lon = float(longitude)
        return -90 <= lat <= 90 and -180 <= lon <= 180
    except (ValueError, TypeError):
        return False


def validate_date(date_obj: Union[date, str]) -> bool:
    """
    Tarihin geçerli olup olmadığını kontrol eder.
    
    Args:
        date_obj: date objesi veya string
        
    Returns:
        True if valid, False otherwise
    """
    if isinstance(date_obj, date) and not isinstance(date_obj, datetime):
        return True
    
    if isinstance(date_obj, str):
        return parse_date_flexible(date_obj) is not None
    
    return False


# =============================================================================
# LOGGING UTILITIES
# =============================================================================
def log_function_call(func):
    """
    Fonksiyon çağrılarını log'layan decorator.
    
    Usage:
        @log_function_call
        def my_function():
            pass
    """
    from functools import wraps
    @wraps(func)
    def wrapper(*args, **kwargs):
        logger.debug(f"Calling {func.__name__} with args={args}, kwargs={kwargs}")
        try:
            result = func(*args, **kwargs)
            logger.debug(f"{func.__name__} completed successfully")
            return result
        except Exception as e:
            logger.error(f"{func.__name__} failed with error: {e}", exc_info=True)
            raise
    return wrapper


# =============================================================================
# DICTIONARY UTILITIES
# =============================================================================
def safe_get(data: dict, *keys, default=None):
    """
    Nested dict'ten güvenli şekilde değer alır.
    
    Args:
        data: Dict objesi
        *keys: Anahtarlar (sıralı)
        default: Varsayılan değer
        
    Returns:
        Değer veya default
        
    Examples:
        >>> data = {"user": {"name": "John"}}
        >>> safe_get(data, "user", "name")
        'John'
        >>> safe_get(data, "user", "age", default=0)
        0
    """
    if not data:
        return default
    
    current = data
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default
    
    return current


def flatten_dict(data: dict, parent_key: str = "", sep: str = "_") -> dict:
    """
    Nested dict'i flat hale getirir.
    
    Args:
        data: Nested dict
        parent_key: Ebeveyn anahtar
        sep: Ayırıcı
        
    Returns:
        Flat dict
    """
    items = []
    for key, value in data.items():
        new_key = f"{parent_key}{sep}{key}" if parent_key else key
        if isinstance(value, dict):
            items.extend(flatten_dict(value, new_key, sep=sep).items())
        else:
            items.append((new_key, value))
    return dict(items)


if __name__ == "__main__":
    # Test
    print("Testing utils.py...")
    
    # Test time parsing
    print(f"parse_time_flexible('14:30'): {parse_time_flexible('14:30')}")
    print(f"parse_time_flexible('invalid'): {parse_time_flexible('invalid')}")
    
    # Test element class
    print(f"get_element_class('Koç'): {get_element_class('Koç')}")
    print(f"get_element_class('Boğa'): {get_element_class('Boğa')}")
    
    # Test zodiac sign
    print(f"get_zodiac_sign(45.5): {get_zodiac_sign(45.5)}")
    
    # Test convert_times_to_str
    test_dict = {
        "time": time(14, 30),
        "date": date(2024, 1, 15),
        "nested": {"time2": time(9, 0)}
    }
    print(f"convert_times_to_str(test_dict): {convert_times_to_str(test_dict)}")
    
    # Test safe_get
    test_data = {"user": {"profile": {"name": "John"}}}
    print(f"safe_get(test_data, 'user', 'profile', 'name'): {safe_get(test_data, 'user', 'profile', 'name')}")
    
    print("✅ All tests passed!")
