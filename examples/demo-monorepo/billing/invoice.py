"""Billing depends on auth — a change to auth.verify_token reaches here."""

from auth.session import verify_token


def create_invoice(token: str, amount: int) -> dict:
    if not verify_token(token):
        raise PermissionError("invalid token")
    return {"amount": amount, "status": "created"}
