from backend_api.app.security import create_access_token, decode_access_token, hash_password, verify_password


def test_password_hash_roundtrip() -> None:
    salt, password_hash = hash_password("DemoPass123!")
    assert verify_password("DemoPass123!", salt, password_hash)
    assert not verify_password("WrongPass123!", salt, password_hash)


def test_jwt_roundtrip() -> None:
    token = create_access_token(
        {"sub": "user-123", "username": "demo"}, expires_in=60)
    payload = decode_access_token(token)
    assert payload["sub"] == "user-123"
    assert payload["username"] == "demo"
