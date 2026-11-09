"""Store the Anthropic API key in the macOS login Keychain (generic password).

Uses Security.framework through PyObjC, so the key never touches disk in
plain text or a process's argv.
"""

import logging

log = logging.getLogger(__name__)

SERVICE = "com.smartpaste.app"
ACCOUNT = "anthropic-api-key"


def _base_query() -> dict:
    import Security as S

    return {
        S.kSecClass: S.kSecClassGenericPassword,
        S.kSecAttrService: SERVICE,
        S.kSecAttrAccount: ACCOUNT,
    }


def get_secret() -> str | None:
    """Return the stored key, or None if there is none or the Keychain can't be read."""
    try:
        import Security as S

        query = {**_base_query(), S.kSecReturnData: True, S.kSecMatchLimit: S.kSecMatchLimitOne}
        status, data = S.SecItemCopyMatching(query, None)
        if status == S.errSecItemNotFound:
            return None
        if status != 0 or data is None:
            log.warning("Keychain read failed (OSStatus %s)", status)
            return None
        return bytes(data).decode("utf-8")
    except Exception as exc:
        log.warning("Keychain read failed: %s", exc)
        return None


def set_secret(value: str) -> bool:
    """Create or replace the stored key. Returns False if the Keychain refused."""
    try:
        import Security as S
        from Foundation import NSData

        raw = value.encode("utf-8")
        data = NSData.dataWithBytes_length_(raw, len(raw))
        status = S.SecItemUpdate(_base_query(), {S.kSecValueData: data})
        if status == S.errSecItemNotFound:
            status, _ = S.SecItemAdd({**_base_query(), S.kSecValueData: data}, None)
        if status != 0:
            log.warning("Keychain write failed (OSStatus %s)", status)
            return False
        return True
    except Exception as exc:
        log.warning("Keychain write failed: %s", exc)
        return False


def delete_secret() -> None:
    try:
        import Security as S

        S.SecItemDelete(_base_query())
    except Exception as exc:
        log.warning("Keychain delete failed: %s", exc)
