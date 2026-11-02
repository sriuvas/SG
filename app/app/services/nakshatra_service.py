from datetime import datetime, timedelta
import math


# ============================================================
# 27 NAKSHATRAS
# ============================================================

NAKSHATRAS = [
    "Ashwini",
    "Bharani",
    "Krittika",
    "Rohini",
    "Mrigashira",
    "Ardra",
    "Punarvasu",
    "Pushya",
    "Ashlesha",
    "Magha",
    "Purva Phalguni",
    "Uttara Phalguni",
    "Hasta",
    "Chitra",
    "Swati",
    "Vishakha",
    "Anuradha",
    "Jyeshtha",
    "Mula",
    "Purva Ashadha",
    "Uttara Ashadha",
    "Shravana",
    "Dhanishtha",
    "Shatabhisha",
    "Purva Bhadrapada",
    "Uttara Bhadrapada",
    "Revati",
]


# Each Nakshatra covers 13 degrees 20 minutes.
NAKSHATRA_SPAN = 360.0 / 27.0


# ============================================================
# HELPER
# ============================================================

def normalize_angle(angle: float) -> float:
    """
    Keep an angle between 0 and 360 degrees.
    """
    return angle % 360.0


# ============================================================
# JULIAN DAY
# ============================================================

def julian_day(dt: datetime) -> float:
    """
    Convert a UTC datetime to Julian Day.
    """

    year = dt.year
    month = dt.month
    day = dt.day

    hour = (
        dt.hour
        + dt.minute / 60.0
        + dt.second / 3600.0
    )

    if month <= 2:
        year -= 1
        month += 12

    A = math.floor(year / 100)

    B = (
        2
        - A
        + math.floor(A / 4)
    )

    jd = (
        math.floor(365.25 * (year + 4716))
        + math.floor(30.6001 * (month + 1))
        + day
        + B
        - 1524.5
        + hour / 24.0
    )

    return jd


# ============================================================
# APPROXIMATE MOON LONGITUDE
# ============================================================

def calculate_moon_longitude(jd: float) -> float:
    """
    Calculate an approximate geocentric Moon longitude.

    This uses a compact astronomical approximation suitable
    for determining the Nakshatra sector.
    """

    T = (jd - 2451545.0) / 36525.0

    # Moon mean longitude
    L0 = (
        218.3164477
        + 481267.88123421 * T
        - 0.0015786 * T * T
        + T * T * T / 538841.0
        - T * T * T * T / 65194000.0
    )

    # Moon mean elongation
    D = (
        297.8501921
        + 445267.1114034 * T
        - 0.0018819 * T * T
        + T * T * T / 545868.0
        - T * T * T * T / 113065000.0
    )

    # Sun mean anomaly
    M = (
        357.5291092
        + 35999.0502909 * T
        - 0.0001536 * T * T
        + T * T * T / 24490000.0
    )

    # Moon mean anomaly
    Mp = (
        134.9633964
        + 477198.8675055 * T
        + 0.0087414 * T * T
        + T * T * T / 69699.0
        - T * T * T * T / 14712000.0
    )

    # Moon argument of latitude
    F = (
        93.2720950
        + 483202.0175233 * T
        - 0.0036539 * T * T
        - T * T * T / 3526000.0
        + T * T * T * T / 863310000.0
    )

    # Main lunar longitude corrections
    correction = (
        6.289 * math.sin(math.radians(Mp))
        + 1.274 * math.sin(
            math.radians(2 * D - Mp)
        )
        + 0.658 * math.sin(
            math.radians(2 * D)
        )
        + 0.214 * math.sin(
            math.radians(2 * Mp)
        )
        - 0.186 * math.sin(
            math.radians(M)
        )
        - 0.059 * math.sin(
            math.radians(2 * D - 2 * Mp)
        )
        - 0.057 * math.sin(
            math.radians(2 * D - M - Mp)
        )
        + 0.053 * math.sin(
            math.radians(2 * D + Mp)
        )
        + 0.046 * math.sin(
            math.radians(2 * D - M)
        )
        + 0.041 * math.sin(
            math.radians(M - Mp)
        )
        - 0.035 * math.sin(
            math.radians(D)
        )
        - 0.031 * math.sin(
            math.radians(M + Mp)
        )
        - 0.015 * math.sin(
            math.radians(2 * F - 2 * D)
        )
        + 0.011 * math.sin(
            math.radians(Mp - 4 * D)
        )
    )

    longitude = L0 + correction

    return normalize_angle(longitude)


# ============================================================
# SIDEREAL CORRECTION
# ============================================================

def calculate_ayanamsa(jd: float) -> float:
    """
    Approximate Lahiri ayanamsa.
    """

    T = (jd - 2451545.0) / 36525.0

    ayanamsa = (
        23.853055
        + 1.396261 * T
        + 0.000308 * T * T
    )

    return ayanamsa


# ============================================================
# NAKSHATRA CALCULATION
# ============================================================

def calculate_nakshatra(
    date_of_birth: str,
    birth_time: str
) -> dict:
    """
    Calculate Nakshatra from date and time.

    Expected:
        date_of_birth = YYYY-MM-DD
        birth_time = HH:MM

    IST (UTC+5:30) is used as the fixed project
    time convention because birthplace is not collected.
    """

    try:
        local_datetime = datetime.strptime(
            f"{date_of_birth} {birth_time}",
            "%Y-%m-%d %H:%M"
        )
    except ValueError:
        raise ValueError(
            "Date must be YYYY-MM-DD and time must be HH:MM"
        )

    # Convert IST to UTC.
    utc_datetime = local_datetime - timedelta(
        hours=5,
        minutes=30
    )

    jd = julian_day(utc_datetime)

    tropical_longitude = calculate_moon_longitude(jd)

    ayanamsa = calculate_ayanamsa(jd)

    # Convert tropical longitude to sidereal longitude.
    sidereal_longitude = normalize_angle(
        tropical_longitude - ayanamsa
    )

    # Determine Nakshatra.
    nakshatra_index = int(
        sidereal_longitude / NAKSHATRA_SPAN
    )

    # Protect against floating-point edge cases.
    nakshatra_index = min(
        nakshatra_index,
        len(NAKSHATRAS) - 1
    )

    nakshatra_name = NAKSHATRAS[
        nakshatra_index
    ]

    # Position inside the Nakshatra.
    position_in_nakshatra = (
        sidereal_longitude
        - (
            nakshatra_index
            * NAKSHATRA_SPAN
        )
    )

    return {
        "nakshatra": nakshatra_name,
        "nakshatra_number": nakshatra_index + 1,
        "sidereal_moon_longitude": round(
            sidereal_longitude,
            6
        ),
        "nakshatra_position_degrees": round(
            position_in_nakshatra,
            6
        )
    }