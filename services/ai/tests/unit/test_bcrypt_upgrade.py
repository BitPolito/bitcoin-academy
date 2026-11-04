from app.core.config import get_password_hash, verify_password

def test_long_password_bcrypt_5_compatibility():
    # A password exceeding the 72-byte bcrypt limit
    long_password = "a" * 80
    
    # This should not raise a ValueError
    hashed = get_password_hash(long_password)
    
    # It should correctly verify the truncated byte array
    assert verify_password(long_password, hashed) is True
    assert verify_password("a" * 72, hashed) is True
    assert verify_password("b" * 72, hashed) is False
