# backend/property_type_mapper.py

_RULES = [
    ("商辦", ["辦公", "商業", "店面", "廠辦", "商辦", "事務所"]),
    ("土地", ["土地", "農地", "建地", "林地", "田"]),
    ("住宅", ["公寓", "住宅", "套房", "大樓", "透天", "別墅", "樓層"]),
]


def normalize_property_type(raw: str) -> str:
    """Map raw judicial auction type string to one of: 住宅/商辦/土地/其他."""
    for normalized, keywords in _RULES:
        for kw in keywords:
            if kw in raw:
                return normalized
    return "其他"
