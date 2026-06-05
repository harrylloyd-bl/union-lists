from union_lists.transform import reformat_union_lists as ref

def test_extract_plus_references():
    x_num: str = "X/9053/58N/4+N/8"
    scale: str = "One Inch"
    bn, bl, sid = ("58", "N", "4")
    entry: dict[str, str|None] = {}

    one_inch_plus = ref.extract_plus_references(x_num, scale, bn, bl, sid, entry)
    assert len(one_inch_plus) == 1
    assert one_inch_plus[0]["Post-1905 Block Number"] == "58"
    assert one_inch_plus[0]["Post-1905 Block Letter"] == "N"
    assert one_inch_plus[0]["Post-1905 Sheet ID"] == "8"