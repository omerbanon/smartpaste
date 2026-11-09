"""Launch at Login via SMAppService.mainAppService (macOS 13+).

Only works when running as the bundled SmartPaste.app; from source the
toggle reports itself unavailable. The system's Login Items list is the
source of truth, so nothing is stored in config.json.
"""

import logging

log = logging.getLogger(__name__)

BUNDLE_ID = "com.smartpaste.app"


def is_available() -> bool:
    try:
        from Foundation import NSBundle

        return NSBundle.mainBundle().bundleIdentifier() == BUNDLE_ID
    except Exception:
        return False


def is_enabled() -> bool:
    if not is_available():
        return False
    try:
        import ServiceManagement as SM

        return SM.SMAppService.mainAppService().status() == SM.SMAppServiceStatusEnabled
    except Exception as exc:
        log.warning("Could not read login item status: %s", exc)
        return False


def set_enabled(enabled: bool) -> str | None:
    """Register or unregister the app as a login item. Returns an error message, or None."""
    if not is_available():
        return "Launch at Login works only in the installed SmartPaste.app"
    try:
        import ServiceManagement as SM

        service = SM.SMAppService.mainAppService()
        if enabled:
            ok, err = service.registerAndReturnError_(None)
        else:
            ok, err = service.unregisterAndReturnError_(None)
        if not ok:
            log.warning("Login item change failed: %s", err)
            return str(err.localizedDescription()) if err else "Login item change failed"
        if enabled and service.status() == SM.SMAppServiceStatusRequiresApproval:
            SM.SMAppService.openSystemSettingsLoginItems()
            return "Approve SmartPaste in System Settings > Login Items"
        log.info("Launch at Login %s", "enabled" if enabled else "disabled")
        return None
    except Exception as exc:
        log.warning("Login item change failed: %s", exc)
        return str(exc)
