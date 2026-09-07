def test_package_is_importable() -> None:
    import vibepy

    assert vibepy.__all__ == []
