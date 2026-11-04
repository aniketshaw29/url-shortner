from app.codes import (
    BASE62,
    generate_code,
    is_reserved_alias,
    is_valid_alias,
    normalize_alias,
)


def test_generate_code_length_and_alphabet() -> None:
    code = generate_code()
    assert len(code) == 7
    assert set(code) <= set(BASE62)


def test_generate_code_is_random_enough() -> None:
    codes = {generate_code() for _ in range(1000)}
    assert len(codes) == 1000


def test_alias_normalization_and_validation() -> None:
    assert normalize_alias("  Launch-2026 ") == "launch-2026"
    assert is_valid_alias("launch-2026")
    assert is_valid_alias("a_b")
    assert not is_valid_alias("ab")
    assert not is_valid_alias("has space")
    assert not is_valid_alias("UPPER")
    assert not is_valid_alias("bad!char")


def test_reserved_aliases() -> None:
    assert is_reserved_alias("API")
    assert is_reserved_alias("healthz")
    assert not is_reserved_alias("launch")
