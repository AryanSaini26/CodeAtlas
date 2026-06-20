from auth.session import verify_token


def test_verify_token() -> None:
    assert verify_token("longenoughtoken")
    assert not verify_token("short")
