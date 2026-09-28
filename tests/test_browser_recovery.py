from ozon_buyer_mcp.browser import OzonBrowser


class FakePage:
    def __init__(self, closed: bool) -> None:
        self.closed = closed

    def is_closed(self) -> bool:
        return self.closed


class FakeBrowser:
    def __init__(self, connected: bool) -> None:
        self.connected = connected

    def is_connected(self) -> bool:
        return self.connected


def test_page_is_alive_rejects_closed_page() -> None:
    browser = OzonBrowser(headless=True)
    browser._ready = True
    browser._page = FakePage(closed=True)  # type: ignore[assignment]
    assert browser._page_is_alive() is False


def test_page_is_alive_rejects_disconnected_browser() -> None:
    browser = OzonBrowser(headless=True)
    browser._ready = True
    browser._page = FakePage(closed=False)  # type: ignore[assignment]
    browser._browser = FakeBrowser(connected=False)  # type: ignore[assignment]
    assert browser._page_is_alive() is False


def test_page_is_alive_accepts_live_target() -> None:
    browser = OzonBrowser(headless=True)
    browser._ready = True
    browser._page = FakePage(closed=False)  # type: ignore[assignment]
    browser._browser = FakeBrowser(connected=True)  # type: ignore[assignment]
    assert browser._page_is_alive() is True


def test_target_closed_error_detection() -> None:
    exc = RuntimeError("Target page, context or browser has been closed")
    assert OzonBrowser._is_target_closed_error(exc) is True
    assert OzonBrowser._is_target_closed_error(RuntimeError("ordinary timeout")) is False
