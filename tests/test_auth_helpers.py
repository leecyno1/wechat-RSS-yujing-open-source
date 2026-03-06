from apis.auth import _split_csv


def test_split_csv_basic():
    assert _split_csv("a,b,c") == ["a", "b", "c"]


def test_split_csv_trim_and_empty():
    assert _split_csv(" a, ,b ,, c ") == ["a", "b", "c"]
    assert _split_csv("") == []
    assert _split_csv(None) == []
