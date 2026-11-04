"""Published outputs must be aggregated: no OCIDs, supplier ids or natural-person tokens."""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = [p for p in (ROOT / "outputs").rglob("*.csv") if "private" not in p.parts]


@pytest.mark.skipif(not PUBLIC, reason="pipeline has not been run")
@pytest.mark.parametrize("path", PUBLIC, ids=lambda p: str(p.relative_to(ROOT)))
def test_public_outputs_are_aggregated(path):
    text = path.read_text(encoding="utf-8")
    header = text.splitlines()[0].split(",") if text else []
    assert "ocid" not in header and "supplier_id" not in header and "buyer_id" not in header
    assert "NP-" not in text            # no pseudonymised person tokens either
    assert "ocds-" not in text and "PE-RUC-" not in text
