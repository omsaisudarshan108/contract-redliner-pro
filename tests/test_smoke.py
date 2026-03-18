from contract_redliner.services.docx_exporter import export_docx_with_track_changes
from contract_redliner.core.models import RedlineEntry


def test_docx_export_smoke():
    blob = export_docx_with_track_changes(
        "Test",
        [
            RedlineEntry(
                clause_id="1",
                title="Confidentiality",
                original_text="The obligations remain in perpetuity.",
                suggested_text="The obligations remain for three (3) years.",
                reason="Policy mismatch",
                risk_level="medium",
            )
        ],
    )
    assert blob[:2] == b"PK"
