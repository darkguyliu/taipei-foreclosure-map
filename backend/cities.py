# backend/cities.py
"""
City / district reference data shared by scraper.py and realtime_prices.py.

county_code       → COUNTY param for 法務部行政執行署拍賣公告查詢系統 (tpkonsale.moj.gov.tw)
districts[*]      → AREA param for the same system
price_file_prefix → file prefix for 內政部不動產交易實價登錄 open data
                     (e.g. "a_lvr_land_a.json" for 台北市)

District names are unique across the cities currently supported, so callers
can look districts up without also specifying a city.
"""

CITIES = {
    "台北市": {
        "county_code": "A",
        "price_file_prefix": "a",
        "districts": {
            "松山區": "01", "大安區": "02", "中正區": "03",
            "萬華區": "05", "大同區": "09", "中山區": "10",
            "文山區": "11", "南港區": "13", "內湖區": "14",
            "士林區": "15", "北投區": "16", "信義區": "17",
        },
    },
    "新北市": {
        "county_code": "F",
        "price_file_prefix": "f",
        "districts": {
            "新莊區": "01", "林口區": "02", "五股區": "03", "蘆洲區": "04",
            "三重區": "05", "泰山區": "06", "新店區": "07", "石碇區": "08",
            "深坑區": "09", "坪林區": "10", "烏來區": "11", "板橋區": "14",
            "三峽區": "15", "鶯歌區": "16", "樹林區": "17", "中和區": "18",
            "土城區": "19", "瑞芳區": "21", "平溪區": "22", "雙溪區": "23",
            "貢寮區": "24", "金山區": "25", "萬里區": "26", "淡水區": "27",
            "汐止區": "28", "三芝區": "30", "石門區": "31", "八里區": "32",
            "永和區": "33",
        },
    },
}

DISTRICT_CITY = {
    district: city
    for city, info in CITIES.items()
    for district in info["districts"]
}


def _city_name_variants(city: str) -> set:
    """A city's name plus its 台/臺 variant, e.g. {"台北市", "臺北市"}."""
    variants = {city}
    if "台" in city:
        variants.add(city.replace("台", "臺"))
    elif "臺" in city:
        variants.add(city.replace("臺", "台"))
    return variants


# All recognized city-name prefixes (across both 台/臺 variants), used to detect
# whether an address already carries a city prefix before adding one.
KNOWN_CITY_PREFIXES = {
    variant for city in CITIES for variant in _city_name_variants(city)
}


def get_city_for_district(district: str) -> str:
    return DISTRICT_CITY.get(district, "")


def get_county_code(district: str) -> str:
    city = DISTRICT_CITY.get(district)
    return CITIES[city]["county_code"] if city else ""


def get_area_code(district: str) -> str:
    city = DISTRICT_CITY.get(district)
    return CITIES[city]["districts"][district] if city else ""


def get_price_file_prefix(district: str) -> str:
    city = DISTRICT_CITY.get(district)
    return CITIES[city]["price_file_prefix"] if city else ""
