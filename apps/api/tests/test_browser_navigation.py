import asyncio
import os
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace

from app.config import Settings
from app.services.browser_navigation import BrowserNavigationService


class StubPage:
    async def evaluate(self, script: str) -> str:
        assert "document.body" in script
        return "Oppilaan vastaus\nTest answer"

    async def screenshot(self) -> str:
        return "dGVzdA=="

    async def get_url(self) -> str:
        return "https://example.com/exam"


class StubBrowserSession:
    def __init__(self) -> None:
        self.screenshot_path: Path | None = None
        self.started = False
        self.navigated_to: str | None = None

    async def start(self) -> None:
        self.started = True

    async def get_current_page_url(self) -> str:
        return "https://example.com/exam"

    async def get_current_page(self) -> StubPage:
        return StubPage()

    async def take_screenshot(self, path: str, full_page: bool) -> bytes:
        self.screenshot_path = Path(path)
        self.screenshot_path.write_bytes(b"test")
        assert full_page is True
        return b"test"

    async def navigate_to(self, url: str, new_tab: bool = False) -> None:
        assert new_tab is False
        self.navigated_to = url


class StubBrowserSessionWithTabs:
    def __init__(self) -> None:
        self.focused_target = None
        self.switched_target_id: str | None = None
        self.tabs = [
            SimpleNamespace(target_id="blank-tab", url="about:blank", title=""),
            SimpleNamespace(target_id="sanoma-tab", url="https://www.sanomapro.fi/auth/login/", title="SanomaPro"),
            SimpleNamespace(target_id="exam-tab", url="https://arvi.sanomapro.fi/exam/session/123", title="TEAS"),
        ]

    def get_focused_target(self):
        return self.focused_target

    async def get_current_page_url(self) -> str:
        return "about:blank"

    async def get_current_page(self):
        return None

    async def get_tabs(self):
        return self.tabs

    async def on_SwitchTabEvent(self, event) -> str:
        self.switched_target_id = event.target_id
        for tab in self.tabs:
            if tab.target_id == event.target_id:
                self.focused_target = SimpleNamespace(url=tab.url)
                return tab.target_id
        raise RuntimeError("Unknown target id")


class StubBrowserSessionWithTabsNoCDP(StubBrowserSessionWithTabs):
    def __init__(self) -> None:
        super().__init__()
        self._cdp_client_root = None
        self.agent_focus_target_id: str | None = None

    async def on_SwitchTabEvent(self, event) -> str:
        raise AssertionError("Root CDP client not initialized")


def test_get_current_page_url_uses_browser_session_api() -> None:
    service = BrowserNavigationService(Settings())
    current_url = asyncio.run(service.get_current_page_url(StubBrowserSession()))

    assert current_url == "https://example.com/exam"


def test_get_current_page_url_switches_to_best_existing_non_blank_tab() -> None:
    settings = Settings().model_copy(update={"browser_start_url": "https://www.sanomapro.fi/auth/login/"})
    service = BrowserNavigationService(settings)

    session = StubBrowserSessionWithTabs()
    current_url = asyncio.run(service.get_current_page_url(session))

    assert current_url == "https://arvi.sanomapro.fi/exam/session/123"
    assert session.switched_target_id == "exam-tab"


def test_get_current_page_url_falls_back_to_direct_focus_when_cdp_root_is_not_ready() -> None:
    settings = Settings().model_copy(update={"browser_start_url": "https://www.sanomapro.fi/auth/login/"})
    service = BrowserNavigationService(settings)

    session = StubBrowserSessionWithTabsNoCDP()
    current_url = asyncio.run(service.get_current_page_url(session))

    assert current_url == "https://arvi.sanomapro.fi/exam/session/123"
    assert session.agent_focus_target_id == "exam-tab"


def test_launch_interactive_browser_opens_default_login_page(monkeypatch) -> None:
    stub_session = StubBrowserSession()
    settings = Settings().model_copy(update={"browser_start_url": "https://www.sanomapro.fi/auth/login/"})
    service = BrowserNavigationService(settings)
    monkeypatch.setattr(service, "_build_interactive_session", lambda job_id: stub_session)

    session_id, browser_session = asyncio.run(service.launch_interactive_browser("job-1"))

    assert session_id == "job-1"
    assert browser_session is stub_session
    assert stub_session.started is True
    assert stub_session.navigated_to == "https://www.sanomapro.fi/auth/login/"


def test_launch_interactive_browser_can_keep_current_page(monkeypatch) -> None:
    stub_session = StubBrowserSession()
    settings = Settings().model_copy(update={"browser_start_url": "https://www.sanomapro.fi/auth/login/"})
    service = BrowserNavigationService(settings)
    monkeypatch.setattr(service, "_build_interactive_session", lambda job_id: stub_session)

    session_id, browser_session = asyncio.run(
        service.launch_interactive_browser(
            "job-keep-page",
            navigate_to_start_url=False,
        )
    )

    assert session_id == "job-keep-page"
    assert browser_session is stub_session
    assert stub_session.started is True
    assert stub_session.navigated_to is None


def test_capture_page_state_saves_screenshot_and_extracts_text(tmp_path) -> None:
    service = BrowserNavigationService(Settings())
    screenshot_path = tmp_path / "page.png"

    current_url, extracted_text = asyncio.run(
        service._capture_page_state(
            StubBrowserSession(),
            "https://example.com/fallback",
            screenshot_path,
        )
    )

    assert current_url == "https://example.com/exam"
    assert extracted_text == "Oppilaan vastaus\nTest answer"
    assert screenshot_path.exists()


def test_build_interactive_session_uses_persistent_profile_dir(tmp_path) -> None:
    settings = Settings().model_copy(
        update={
            "browser_persistent_profile_dir": str(tmp_path / "persistent-profile"),
            "browser_use_system_chrome": False,
            "browser_direct_persistent_profile": True,
        }
    )
    service = BrowserNavigationService(settings)

    session = service._build_interactive_session("job-1")

    assert Path(str(session.browser_profile.user_data_dir)) == tmp_path / "browser-use-user-data-dir-persistent-profile"
    assert session.browser_profile.profile_directory == "Default"
    assert session.browser_profile.enable_default_extensions is False


def test_build_interactive_session_can_attach_to_existing_chrome() -> None:
    settings = Settings().model_copy(
        update={
            "browser_attach_to_existing_chrome": True,
            "browser_debug_port": 9333,
        }
    )
    service = BrowserNavigationService(settings)

    session = service._build_interactive_session("job-attach")

    assert session.cdp_url == "http://127.0.0.1:9333"


def test_system_chrome_bootstrap_copies_once_into_persistent_profile(tmp_path, monkeypatch) -> None:
    source_root = tmp_path / "chrome-user-data"
    source_profile = source_root / "Default"
    source_profile.mkdir(parents=True)
    (source_profile / "Network").mkdir()
    (source_profile / "Network" / "Cookies").write_text("cookie-db", encoding="utf-8")
    (source_profile / "Preferences").write_text("prefs", encoding="utf-8")
    (source_root / "Local State").write_text("state", encoding="utf-8")

    monkeypatch.setattr(
        "app.services.browser_navigation.get_chrome_profile_path",
        lambda profile: str(source_root),
    )
    monkeypatch.setattr(
        "app.services.browser_navigation.find_chrome_executable",
        lambda: "C:/Program Files/Google/Chrome/Application/chrome.exe",
    )

    target_root = Path("artifacts/browser/test-persistent-login-state")
    shutil.rmtree(target_root, ignore_errors=True)

    try:
        settings = Settings().model_copy(
            update={
                "browser_persistent_profile_dir": str(target_root),
                "browser_use_system_chrome": True,
                "browser_direct_persistent_profile": True,
                "browser_chrome_profile_directory": "Default",
            }
        )
        service = BrowserNavigationService(settings)

        session = service._build_interactive_session("job-2")

        expected_root = target_root.parent / f"browser-use-user-data-dir-{target_root.name}"
        assert Path(str(session.browser_profile.user_data_dir)) == expected_root.resolve()
        assert str(session.browser_profile.executable_path) == "C:/Program Files/Google/Chrome/Application/chrome.exe"
        assert (expected_root / "Default" / "Network" / "Cookies").exists()
        assert not (expected_root / "Default" / "Preferences").exists()
        assert (expected_root / "Local State").exists()
    finally:
        shutil.rmtree(target_root, ignore_errors=True)
        shutil.rmtree(target_root.parent / f"browser-use-user-data-dir-{target_root.name}", ignore_errors=True)


def test_cleanup_browser_artifacts_removes_run_downloads_and_old_temp_dirs(tmp_path, monkeypatch) -> None:
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    downloads_dir = artifact_dir / "job-1-downloads"
    downloads_dir.mkdir()
    (downloads_dir / "answer.txt").write_text("download", encoding="utf-8")

    old_screenshot = artifact_dir / "old.png"
    old_screenshot.write_bytes(b"old")
    new_screenshot = artifact_dir / "job-1.png"
    new_screenshot.write_bytes(b"new")
    os.utime(old_screenshot, (1, 1))
    os.utime(new_screenshot, None)

    system_temp_dir = tmp_path / "system-temp"
    system_temp_dir.mkdir()
    stale_agent_dir = system_temp_dir / "browser_use_agent_old"
    stale_agent_dir.mkdir()
    (stale_agent_dir / "step_1.png").write_bytes(b"tmp")
    os.utime(stale_agent_dir, (1, 1))

    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(system_temp_dir))

    settings = Settings().model_copy(
        update={
            "browser_cleanup_stale_after_seconds": 0,
            "browser_max_saved_screenshots": 1,
        }
    )
    service = BrowserNavigationService(settings)
    monkeypatch.setattr(service, "_artifact_dir", lambda: artifact_dir)

    cleanup_result = service.cleanup_browser_artifacts(current_job_id="job-1")

    assert cleanup_result["removed_paths"] >= 2
    assert not downloads_dir.exists()
    assert not stale_agent_dir.exists()
    assert new_screenshot.exists()
    assert not old_screenshot.exists()


def test_cleanup_agent_runtime_dir_removes_browser_use_agent_directory(tmp_path) -> None:
    agent_dir = tmp_path / "browser_use_agent_test"
    agent_dir.mkdir()
    (agent_dir / "step_1.png").write_bytes(b"png")
    service = BrowserNavigationService(Settings())

    cleanup_result = service.cleanup_agent_runtime_dir(SimpleNamespace(agent_directory=agent_dir))

    assert cleanup_result["removed_paths"] == 1
    assert cleanup_result["removed_bytes"] > 0
    assert not agent_dir.exists()
