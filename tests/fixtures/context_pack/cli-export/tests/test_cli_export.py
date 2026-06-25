from invoice_export.cli import export_invoice_total, invoice_export_rounding


def test_invoice_export_rounding_uses_half_up_currency_rule() -> None:
    assert invoice_export_rounding("10.005") == "10.01"


def test_export_invoice_total_rounds_combined_amount() -> None:
    assert export_invoice_total(["10.005", "2.015"]) == "12.02"
