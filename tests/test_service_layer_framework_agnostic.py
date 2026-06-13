from pathlib import Path


def test_services_and_db_modules_do_not_import_fastapi() -> None:
    root = Path(__file__).resolve().parents[1]
    checked_files = list((root / "app" / "services").glob("*.py")) + list(
        (root / "app" / "db").glob("*.py")
    )

    assert checked_files
    for path in checked_files:
        text = path.read_text(encoding="utf-8").lower()
        assert "import fastapi" not in text
        assert "from fastapi" not in text
