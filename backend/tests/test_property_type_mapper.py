from property_type_mapper import normalize_property_type


def test_住宅_keywords():
    assert normalize_property_type("公寓") == "住宅"
    assert normalize_property_type("住宅大樓") == "住宅"
    assert normalize_property_type("套房") == "住宅"
    assert normalize_property_type("透天厝") == "住宅"


def test_商辦_keywords():
    assert normalize_property_type("辦公室") == "商辦"
    assert normalize_property_type("商業大樓") == "商辦"
    assert normalize_property_type("店面") == "商辦"
    assert normalize_property_type("廠辦") == "商辦"


def test_土地_keywords():
    assert normalize_property_type("土地") == "土地"
    assert normalize_property_type("農地") == "土地"
    assert normalize_property_type("建地") == "土地"


def test_其他_fallback():
    assert normalize_property_type("停車位") == "其他"
    assert normalize_property_type("倉庫") == "其他"
    assert normalize_property_type("") == "其他"
