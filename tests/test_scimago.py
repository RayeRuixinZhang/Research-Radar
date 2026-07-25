import csv
import hashlib
import json

from research_radar.scimago import import_scimago


def test_import_official_scimago_export(tmp_path):
    source = tmp_path / "scimagojr 2025.csv"
    content = (
        "Rank;Title;SJR Best Quartile;H index;Issn;Areas;Year\n"
        '1;Journal Alpha;Q1;100;"1234-567X, 8765-4321";Medicine;2025\n'
        "2;Journal Beta;Q2;50;1111-2222;Medicine;2025\n"
        "3;Engineering Journal;Q1;20;2222-3333;Engineering;2025\n"
    )
    source.write_text(content, encoding="utf-8")

    metadata = import_scimago(source, tmp_path)

    with (tmp_path / "reference/scimago_q1_medicine.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))
    assert rows == [
        {
            "title": "Journal Alpha",
            "issn": "1234-567X;8765-4321",
            "quartile": "Q1",
            "year": "2025",
        }
    ]
    assert metadata["data_year"] == 2025
    assert metadata["journal_count"] == 1
    assert metadata["issn_count"] == 2
    assert metadata["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    saved = json.loads(
        (tmp_path / "reference/scimago_metadata.json").read_text(encoding="utf-8")
    )
    assert saved["is_jcr"] is False
