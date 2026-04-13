from scripts.instinct_active_patients_audit import _locate_columns, audit_rows


def test_audit_reports_unique_identifier_and_required_fields_present():
    rows = [
        {
            "PMS ID": "FE261",
            "Patient": "bob TEST",
            "Owner": "Greg Test",
            "Email": "greg@example.com",
            "Phone": "3211234567",
            "Species": "canine",
            "Breed": "mix",
            "Sex": "unknown",
        },
        {
            "PMS ID": "FE262",
            "Patient": "sue TEST",
            "Owner": "Greg Test",
            "Email": "greg@example.com",
            "Phone": "3211234567",
            "Species": "canine",
            "Breed": "mix",
            "Sex": "female",
        },
    ]

    columns = _locate_columns(list(rows[0].keys()))
    report = audit_rows(rows, columns)

    assert report.has_unique_identifier is True
    assert report.missing_identifier_rows == 0
    assert report.duplicate_identifier_values == 0
    assert all(v == 0 for v in report.missing_required_counts.values())


def test_audit_reports_duplicate_identifier_and_missing_fields():
    rows = [
        {
            "PMS ID": "FE261",
            "Patient": "bob TEST",
            "Owner": "",
            "Email": "",
            "Phone": "",
            "Species": "",
            "Breed": "",
            "Sex": "",
        },
        {
            "PMS ID": "FE261",
            "Patient": "",
            "Owner": "",
            "Email": "",
            "Phone": "",
            "Species": "",
            "Breed": "",
            "Sex": "",
        },
    ]

    columns = _locate_columns(list(rows[0].keys()))
    report = audit_rows(rows, columns)

    assert report.has_unique_identifier is False
    assert report.duplicate_identifier_values == 1
    assert report.missing_required_counts["patient_name"] == 1
