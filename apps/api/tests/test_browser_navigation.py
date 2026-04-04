import asyncio
import io
import json
import os
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from app.config import Settings
from app.schemas.api import ExamSessionGradingTaskCreate, ExamSessionGradingTaskResult
from app.services.browser_navigation import (
    BrowserNavigationService,
    SanomaExerciseScoreField,
    SanomaExerciseState,
    SanomaOverviewState,
    SanomaScoreDecision,
    SanomaScoreDecisionField,
    VisualExamPageAssessment,
)


class StubCDPTargetAPI:
    def __init__(self, session: "StubBrowserSessionWithTabs") -> None:
        self.session = session

    async def getTargets(self) -> dict:
        return {"targetInfos": list(self.session.raw_cdp_targets)}

    async def attachToTarget(self, params: dict) -> dict:
        target_id = params["targetId"]
        for target in self.session.raw_cdp_targets:
            if target["targetId"] != target_id:
                continue
            if not any(tab.target_id == target_id for tab in self.session.tabs):
                self.session.tabs.append(
                    SimpleNamespace(
                        target_id=target["targetId"],
                        url=target["url"],
                        title=target["title"],
                    )
                )
            return {"sessionId": f"session-{target_id}"}
        raise RuntimeError(f"Unknown target id: {target_id}")


class StubCDPSendAPI:
    def __init__(self, session: "StubBrowserSessionWithTabs") -> None:
        self.Target = StubCDPTargetAPI(session)


class StubCDPClientRoot:
    def __init__(self, session: "StubBrowserSessionWithTabs") -> None:
        self.send = StubCDPSendAPI(session)


class StubPage:
    def __init__(self, url: str = "https://example.com/exam", title: str = "Example exam") -> None:
        self.url = url
        self.title = title
        self.readiness_metrics = {
            "readyState": "complete",
            "textLength": 120,
            "uiViewChildren": 1,
            "interactiveCount": 4,
        }

    async def evaluate(self, script: str) -> str:
        if "uiViewChildren" in script and "interactiveCount" in script:
            return self.readiness_metrics
        assert "document.body" in script
        return "Oppilaan vastaus\nTest answer"

    async def screenshot(self) -> str:
        return "dGVzdA=="

    async def get_url(self) -> str:
        return self.url

    async def get_title(self) -> str:
        return self.title


class StubElement:
    def __init__(self) -> None:
        self.click_count = 0
        self.filled_values: list[str] = []

    async def click(self) -> None:
        self.click_count += 1

    async def fill(self, value: str) -> None:
        self.filled_values.append(value)


class StubInteractivePage(StubPage):
    def __init__(self, url: str, title: str = "TEAS") -> None:
        super().__init__(url=url, title=title)
        self.evaluate_result = {}
        self.elements_by_selector: dict[str, list[StubElement]] = {}

    async def evaluate(self, script: str) -> str:
        if "document.body" in script and "innerText" in script:
            return "Oppilaan vastaus\nTest answer"
        if isinstance(self.evaluate_result, str):
            return self.evaluate_result
        return json.dumps(self.evaluate_result)

    async def get_elements_by_css_selector(self, selector: str) -> list[StubElement]:
        return list(self.elements_by_selector.get(selector, []))


class StubBrowserSession:
    def __init__(self) -> None:
        self.screenshot_path: Path | None = None
        self.started = False
        self.navigated_to: str | None = None
        self.current_page_url = "https://example.com/exam"
        self.current_page_title = "Example exam"
        self.current_page_metrics = {
            "readyState": "complete",
            "textLength": 120,
            "uiViewChildren": 1,
            "interactiveCount": 4,
        }

    async def start(self) -> None:
        self.started = True

    async def get_current_page_url(self) -> str:
        return self.current_page_url

    async def get_current_page(self) -> StubPage:
        page = StubPage(url=self.current_page_url, title=self.current_page_title)
        page.readiness_metrics = dict(self.current_page_metrics)
        return page

    async def take_screenshot(self, path: str, full_page: bool) -> bytes:
        self.screenshot_path = Path(path)
        self.screenshot_path.write_bytes(b"test")
        assert full_page is True
        return b"test"

    async def navigate_to(self, url: str, new_tab: bool = False) -> None:
        assert new_tab is False
        self.navigated_to = url


class StubInteractiveBrowserSession(StubBrowserSession):
    def __init__(self, page: StubInteractivePage) -> None:
        super().__init__()
        self.page = page
        self.current_page_url = page.url
        self.current_page_title = page.title

    async def get_current_page(self) -> StubInteractivePage:
        self.page.url = self.current_page_url
        self.page.title = self.current_page_title
        return self.page


class StubBrowserSessionWithTabs:
    def __init__(self) -> None:
        self.focused_target = None
        self.switched_target_id: str | None = None
        self.switch_count = 0
        self.current_page_url = "about:blank"
        self.current_page_title = "TEAS"
        self.tabs = [
            SimpleNamespace(target_id="blank-tab", url="about:blank", title=""),
            SimpleNamespace(target_id="sanoma-tab", url="https://www.sanomapro.fi/auth/login/", title="SanomaPro"),
            SimpleNamespace(target_id="exam-tab", url="https://arvi.sanomapro.fi/exam/session/123", title="TEAS"),
        ]
        self.raw_cdp_targets = [
            {"targetId": tab.target_id, "url": tab.url, "title": tab.title, "type": "page"}
            for tab in self.tabs
        ]
        self._cdp_client_root = StubCDPClientRoot(self)

    def get_focused_target(self):
        return self.focused_target

    async def get_current_page_url(self) -> str:
        return self.current_page_url

    async def get_current_page(self):
        if self.current_page_url == "about:blank":
            return None
        return StubPage(url=self.current_page_url, title=self.current_page_title)

    async def get_tabs(self):
        return self.tabs

    async def on_SwitchTabEvent(self, event) -> str:
        self.switch_count += 1
        self.switched_target_id = event.target_id
        for tab in self.tabs:
            if tab.target_id == event.target_id:
                self.focused_target = SimpleNamespace(url=tab.url)
                self.current_page_url = tab.url
                self.current_page_title = tab.title
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


def test_get_current_page_url_prefers_exam_tab_over_login_tab() -> None:
    settings = Settings().model_copy(update={"browser_start_url": "https://www.sanomapro.fi/auth/login/"})
    service = BrowserNavigationService(settings)

    session = StubBrowserSessionWithTabs()
    session.current_page_url = "https://www.sanomapro.fi/auth/login/"
    session.focused_target = SimpleNamespace(url="https://www.sanomapro.fi/auth/login/", title="SanomaPro")
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


def test_get_current_page_url_accepts_kampus_content_feed_page() -> None:
    settings = Settings().model_copy(update={"browser_start_url": "https://www.sanomapro.fi/auth/login/"})
    service = BrowserNavigationService(settings)
    session = StubBrowserSessionWithTabs()
    session.current_page_url = (
        "https://kampus.sanomapro.fi/content-feed/"
        "59eabd9a-aefa-4ee6-b5c9-8e5df7698662/es:05E62ED5-5AA0-4572-8B29-CC698732E7D6"
    )
    session.current_page_title = "Sanoma Pro Kampus"

    current_url = asyncio.run(service.get_current_page_url(session))

    assert current_url == "https://arvi.sanomapro.fi/exam/session/123"
    assert session.switched_target_id == "exam-tab"


def test_get_current_page_url_can_recover_exam_page_from_raw_cdp_targets() -> None:
    settings = Settings().model_copy(update={"browser_start_url": "https://www.sanomapro.fi/auth/login/"})
    service = BrowserNavigationService(settings)
    session = StubBrowserSessionWithTabs()
    session.tabs = [
        SimpleNamespace(target_id="sanoma-tab", url="https://www.sanomapro.fi/auth/login/", title="SanomaPro"),
    ]
    session.raw_cdp_targets = [
        {"targetId": "sanoma-tab", "url": "https://www.sanomapro.fi/auth/login/", "title": "SanomaPro", "type": "page"},
        {
            "targetId": "review-tab",
            "url": "https://arvi.sanomapro.fi/as/teacher/assignment/08c826c8-bc26-4794-a602-8d55f34b617b/review",
            "title": "",
            "type": "page",
        },
    ]
    session.current_page_url = "https://www.sanomapro.fi/auth/login/"
    session.current_page_title = "SanomaPro"
    session.focused_target = SimpleNamespace(url="https://www.sanomapro.fi/auth/login/", title="SanomaPro")

    current_url = asyncio.run(service.get_current_page_url(session))

    assert (
        current_url
        == "https://arvi.sanomapro.fi/as/teacher/assignment/08c826c8-bc26-4794-a602-8d55f34b617b/review"
    )
    assert session.switched_target_id == "review-tab"


def test_get_current_page_url_can_choose_review_tab_from_visual_assessment(monkeypatch) -> None:
    service = BrowserNavigationService(
        Settings().model_copy(
            update={
                "browser_visual_backend": "ollama",
            }
        )
    )
    session = StubBrowserSessionWithTabs()
    session.tabs = [
        SimpleNamespace(
            target_id="course-tab",
            url="https://kampus.sanomapro.fi/content-feed/launcher",
            title="Sanoma Pro Kampus",
        ),
        SimpleNamespace(
            target_id="review-tab",
            url="https://arvi.sanomapro.fi/as/teacher/assignment/demo/review",
            title="",
        ),
    ]
    session.raw_cdp_targets = [
        {"targetId": tab.target_id, "url": tab.url, "title": tab.title, "type": "page"}
        for tab in session.tabs
    ]
    session.current_page_url = "https://kampus.sanomapro.fi/content-feed/launcher"
    session.current_page_title = "Sanoma Pro Kampus"

    monkeypatch.setattr(
        service,
        "_resolved_visual_navigation_ollama",
        lambda: ("http://127.0.0.1:11434", "qwen3-vl:4b"),
    )

    async def fake_assess(browser_session, **kwargs):
        url = await browser_session.get_current_page_url()
        if url.endswith("/review"):
            return VisualExamPageAssessment(
                page_kind="exam_grading",
                confidence=96,
                page_ready=True,
                reason="Teacher review layout is visible.",
                visible_signals=["Pisteytys", "Oppilaan vastaus"],
            )
        return VisualExamPageAssessment(
            page_kind="course_contents",
            confidence=94,
            page_ready=False,
            reason="Course launcher page with content cards.",
            visible_signals=["Kompassi-digikokeet"],
        )

    monkeypatch.setattr(service, "_assess_current_page_visually", fake_assess)

    current_url = asyncio.run(service.get_current_page_url(session))

    assert current_url == "https://arvi.sanomapro.fi/as/teacher/assignment/demo/review"
    assert session.switched_target_id == "review-tab"
    assert session.switch_count == 1


def test_get_current_page_url_does_not_switch_away_when_current_page_is_visually_exam(monkeypatch) -> None:
    service = BrowserNavigationService(
        Settings().model_copy(
            update={
                "browser_visual_backend": "ollama",
            }
        )
    )
    session = StubBrowserSessionWithTabs()
    session.current_page_url = "https://arvi.sanomapro.fi/as/teacher/assignment/demo/review"
    session.current_page_title = ""

    monkeypatch.setattr(
        service,
        "_resolved_visual_navigation_ollama",
        lambda: ("http://127.0.0.1:11434", "qwen3-vl:4b"),
    )

    async def fake_assess(browser_session, **kwargs):
        return VisualExamPageAssessment(
            page_kind="exam_grading",
            confidence=98,
            page_ready=True,
            reason="Review screen is already visible.",
            visible_signals=["Oppilaan vastaus", "Pisteytys"],
        )

    monkeypatch.setattr(service, "_assess_current_page_visually", fake_assess)

    current_url = asyncio.run(service.get_current_page_url(session))

    assert current_url == "https://arvi.sanomapro.fi/as/teacher/assignment/demo/review"
    assert session.switch_count == 0


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


def test_list_open_tabs_includes_current_page_when_missing_from_cached_tabs() -> None:
    service = BrowserNavigationService(Settings())
    session = StubBrowserSessionWithTabs()
    session.current_page_url = (
        "https://kampus.sanomapro.fi/content-feed/"
        "59eabd9a-aefa-4ee6-b5c9-8e5df7698662/es:05E62ED5-5AA0-4572-8B29-CC698732E7D6"
    )
    session.current_page_title = "Sanoma Pro Kampus"

    tabs = asyncio.run(service.list_open_tabs(session))

    assert tabs[0]["url"] == session.current_page_url
    assert tabs[0]["title"] == "Sanoma Pro Kampus (current page)"


def test_list_open_tabs_includes_raw_cdp_review_tab() -> None:
    service = BrowserNavigationService(Settings())
    session = StubBrowserSessionWithTabs()
    session.tabs = [
        SimpleNamespace(target_id="sanoma-tab", url="https://www.sanomapro.fi/auth/login/", title="SanomaPro"),
    ]
    session.raw_cdp_targets = [
        {"targetId": "sanoma-tab", "url": "https://www.sanomapro.fi/auth/login/", "title": "SanomaPro", "type": "page"},
        {
            "targetId": "review-tab",
            "url": "https://arvi.sanomapro.fi/as/teacher/assignment/08c826c8-bc26-4794-a602-8d55f34b617b/review",
            "title": "",
            "type": "page",
        },
    ]

    tabs = asyncio.run(service.list_open_tabs(session))

    assert any(tab["url"].endswith("/review") for tab in tabs)


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


def test_agent_kwargs_normalize_small_history_to_browser_use_minimum() -> None:
    service = BrowserNavigationService(
        Settings().model_copy(update={"browser_agent_max_history_items": 3})
    )

    assert service._resolved_max_history_items() == 6
    assert service._agent_kwargs()["max_history_items"] == 6


def test_downscale_visual_image_bytes_limits_max_side() -> None:
    service = BrowserNavigationService(Settings().model_copy(update={"browser_visual_max_image_side": 512}))
    image = Image.new("RGB", (1600, 900), color="white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")

    resized_bytes = service._downscale_visual_image_bytes(buffer.getvalue())

    with Image.open(io.BytesIO(resized_bytes)) as resized:
        assert max(resized.size) <= 512


def test_wait_for_exam_page_ready_accepts_rendered_spa() -> None:
    service = BrowserNavigationService(Settings())
    session = StubBrowserSession()
    session.current_page_url = "https://arvi.sanomapro.fi/as/teacher/assignment/demo/review"
    session.current_page_metrics = {
        "readyState": "complete",
        "textLength": 180,
        "uiViewChildren": 2,
        "interactiveCount": 6,
    }

    ready = asyncio.run(service._wait_for_exam_page_ready(session, timeout_seconds=0.1))

    assert ready is True


def test_wait_for_exam_page_ready_can_use_visual_readiness(monkeypatch) -> None:
    service = BrowserNavigationService(
        Settings().model_copy(
            update={
                "browser_visual_backend": "ollama",
            }
        )
    )
    session = StubBrowserSession()
    session.current_page_url = "https://arvi.sanomapro.fi/as/teacher/assignment/demo/review"

    monkeypatch.setattr(
        service,
        "_resolved_visual_navigation_ollama",
        lambda: ("http://127.0.0.1:11434", "qwen3-vl:4b"),
    )

    assessments = iter(
        [
            VisualExamPageAssessment(
                page_kind="loading",
                confidence=88,
                page_ready=False,
                reason="SPA shell is still empty.",
                visible_signals=[],
            ),
            VisualExamPageAssessment(
                page_kind="exam_grading",
                confidence=95,
                page_ready=True,
                reason="Teacher grading controls are visible.",
                visible_signals=["Oppilaan vastaus", "Pisteytys"],
            ),
        ]
    )

    async def fake_assess(browser_session, **kwargs):
        return next(assessments)

    monkeypatch.setattr(service, "_assess_current_page_visually", fake_assess)

    ready = asyncio.run(service._wait_for_exam_page_ready(session, timeout_seconds=2.0))

    assert ready is True


def test_browser_model_supports_vision_uses_forced_visual_fallback() -> None:
    service = BrowserNavigationService(Settings())

    assert service._browser_model_supports_vision() is False
    assert service._resolved_browser_agent_model() == "qwen3.5:9b"

    vision_enabled_service = BrowserNavigationService(
        Settings().model_copy(
            update={
                "browser_agent_model": "qwen3.5:9b",
                "browser_agent_use_vision": True,
                "browser_agent_force_vision": True,
                "browser_agent_visual_model": "qwen3-vl:4b",
            }
        )
    )
    assert vision_enabled_service._browser_model_supports_vision() is True
    assert vision_enabled_service._resolved_browser_agent_model() == "qwen3-vl:4b"


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


def test_extract_sanomapro_overview_state_parses_pending_candidates() -> None:
    service = BrowserNavigationService(Settings())
    page = StubInteractivePage("https://arvi.sanomapro.fi/as/teacher/assignment/demo/review")
    page.evaluate_result = {
        "route": "/as/teacher/assignment/demo/review",
        "assignment_title": "Demo exam",
        "visible_cell_count": 2,
        "pending_candidates": [
            {"selector_index": 1, "score_text": "- / 4", "candidate_key": "1:- / 4"},
        ],
    }

    state = asyncio.run(service._extract_sanomapro_overview_state(page))

    assert isinstance(state, SanomaOverviewState)
    assert state.assignment_title == "Demo exam"
    assert state.visible_cell_count == 2
    assert state.pending_candidates[0].selector_index == 1


def test_apply_sanomapro_score_decision_fills_manual_score_inputs() -> None:
    service = BrowserNavigationService(Settings())
    page = StubInteractivePage("https://arvi.sanomapro.fi/as/teacher/review/demo/activity/a/document/b/exercise")
    score_element = StubElement()
    page.elements_by_selector[
        "input.manual-score[ng-model='ctrl.score'][ng-blur='ctrl.updateScore()']"
    ] = [score_element]
    exercise_state = SanomaExerciseState(
        route=page.url,
        score_fields=[SanomaExerciseScoreField(index=0, max_score=4, container_text="Pistemäärä / 4 pistettä")],
    )
    decision = SanomaScoreDecision(
        summary="Enter 2 points.",
        confidence=0.95,
        scores=[SanomaScoreDecisionField(index=0, score=2, rationale="Matches two correct answers.")],
    )

    filled = asyncio.run(
        service._apply_sanomapro_score_decision(
            page,
            page.url,
            exercise_state,
            decision,
            dry_run=False,
        )
    )

    assert filled == 1
    assert score_element.filled_values == ["2"]


def test_grade_exam_from_current_page_uses_sanomapro_autonomy(monkeypatch, tmp_path) -> None:
    service = BrowserNavigationService(Settings())
    page = StubInteractivePage("https://arvi.sanomapro.fi/as/teacher/assignment/demo/review")
    session = StubInteractiveBrowserSession(page)
    expected_result = ExamSessionGradingTaskResult(
        job_id="job-1",
        status="completed",
        summary="Deterministic autonomy finished.",
        agent_provider="ollama",
        agent_model="qwen3.5:9b",
        current_url=page.url,
        screenshot_path=str(tmp_path / "result.png"),
        extracted_text="Oppilaan vastaus",
        processed_answers=1,
        filled_point_fields=1,
        current_exercise_label="Tehtävä 1",
        current_student_name="Eetu Ahola",
    )

    monkeypatch.setattr("app.services.browser_navigation.build_browser_use_llm", lambda settings: object())

    async def fake_wait_for_ready(browser_session, timeout_seconds=12.0):
        return True

    async def fake_run_autonomy(payload, job_id, browser_session, *, current_url, provider, screenshot_path):
        return expected_result

    async def fake_current_page_url(browser_session):
        return page.url

    monkeypatch.setattr(service, "_wait_for_exam_page_ready", fake_wait_for_ready)
    monkeypatch.setattr(service, "_run_sanomapro_autonomous_exam_flow", fake_run_autonomy)
    monkeypatch.setattr(service, "get_current_page_url", fake_current_page_url)

    result = asyncio.run(
        service.grade_exam_from_current_page(
            ExamSessionGradingTaskCreate(instructions="Score the answer."),
            "job-1",
            browser_session=session,
        )
    )

    assert result is expected_result
