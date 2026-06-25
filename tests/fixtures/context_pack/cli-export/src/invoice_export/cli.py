from decimal import ROUND_HALF_UP, Decimal


def invoice_export_rounding(amount: str) -> str:
    value = Decimal(amount)
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def export_invoice_total(amounts: list[str]) -> str:
    total = sum(Decimal(amount) for amount in amounts)
    return invoice_export_rounding(str(total))


def main() -> None:
    print(export_invoice_total(["10.005", "2.015"]))
