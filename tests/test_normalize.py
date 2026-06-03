from pathlib import Path

from krs_monitor.normalize import normalize_payload, write_json


def test_normalize_sorts_keys_and_whitespace() -> None:
    payload = {"b": "  Ala\n\tma   kota  ", "a": {"d": "x", "c": " y  z "}}

    assert normalize_payload(payload) == {"a": {"c": "y z", "d": "x"}, "b": "Ala ma kota"}


def test_normalize_removes_technical_metadata() -> None:
    payload = {"requestId": "abc", "dane": {"timestamp": "now", "nazwa": " CGI "}}

    assert normalize_payload(payload) == {"dane": {"nazwa": "CGI"}}


def test_write_json_is_stable(tmp_path: Path) -> None:
    path = tmp_path / "out.json"

    write_json(path, {"b": 1, "a": "Łódź"})

    assert path.read_text(encoding="utf-8") == '{\n  "a": "Łódź",\n  "b": 1\n}\n'
