"""Admin depends on billing (which depends on auth) — two hops from auth."""

from billing.invoice import create_invoice


def admin_overview(token: str) -> dict:
    invoice = create_invoice(token, 0)
    return {"ok": True, "invoice": invoice}
