import asyncio
import io
import json
import os
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace

from PIL import Image
from langchain_core.messages import AIMessage

from app.config import Settings
from app.schemas.api import ExamSessionGradingTaskCreate, ExamSessionGradingTaskResult
from app.services.browser_navigation import (
    BrowserNavigationService,
    SanomaExerciseScoreField,
    SanomaGradingReportEntry,
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
        self.recorded_scripts: list[str] = []

    async def evaluate(self, script: str) -> str:
        self.recorded_scripts.append(script)
        if "__gradeagent_status_overlay__" in script:
            return True
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


def test_discover_running_gradeagent_cdp_url_from_matching_profile(monkeypatch, tmp_path) -> None:
    service = BrowserNavigationService(Settings())
    profile_root = (tmp_path / "browser-use-user-data-dir-gradeagent").resolve()

    class FakeProcess:
        def __init__(self, cmdline: list[str]) -> None:
            self.info = {"cmdline": cmdline}

    monkeypatch.setattr(
        "app.services.browser_navigation.psutil.process_iter",
        lambda attrs: iter(
            [
                FakeProcess(
                    [
                        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                        f"--user-data-dir={tmp_path / 'some-other-profile'}",
                        "--remote-debugging-port=51111",
                    ]
                ),
                FakeProcess(
                    [
                        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                        f"--user-data-dir={profile_root}",
                        "--remote-debugging-port=56995",
                    ]
                ),
            ]
        ),
    )
    monkeypatch.setattr(service, "_cdp_http_url_is_reachable", lambda url: url == "http://127.0.0.1:56995")

    discovered = service._discover_running_gradeagent_cdp_url(profile_root)

    assert discovered == "http://127.0.0.1:56995"


def test_build_interactive_session_reuses_running_gradeagent_browser(monkeypatch, tmp_path) -> None:
    settings = Settings().model_copy(
        update={
            "browser_persistent_profile_dir": str(tmp_path / "persistent-profile"),
            "browser_use_system_chrome": False,
            "browser_direct_persistent_profile": True,
        }
    )
    service = BrowserNavigationService(settings)
    expected_profile_root = (tmp_path / "browser-use-user-data-dir-persistent-profile").resolve()
    seen_profile_roots: list[Path] = []

    def fake_discover(profile_root: Path) -> str | None:
        seen_profile_roots.append(profile_root.resolve())
        return "http://127.0.0.1:56995"

    monkeypatch.setattr(service, "_discover_running_gradeagent_cdp_url", fake_discover)

    session = service._build_interactive_session("job-reuse")

    assert seen_profile_roots == [expected_profile_root]
    assert session.cdp_url == "http://127.0.0.1:56995"


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
        "reviewed_cell_count": 1,
        "unreviewed_cell_count": 1,
        "fully_reviewed": False,
        "pending_candidates": [
            {"selector_index": 1, "score_text": "- / 4", "candidate_key": "1:- / 4"},
        ],
    }

    state = asyncio.run(service._extract_sanomapro_overview_state(page))

    assert isinstance(state, SanomaOverviewState)
    assert state.assignment_title == "Demo exam"
    assert state.visible_cell_count == 2
    assert state.reviewed_cell_count == 1
    assert state.unreviewed_cell_count == 1
    assert state.fully_reviewed is False
    assert state.pending_candidates[0].selector_index == 1


def test_write_sanomapro_grading_report_includes_student_answers_basis_and_links(tmp_path, monkeypatch) -> None:
    service = BrowserNavigationService(Settings())
    monkeypatch.setattr(service, "_artifact_dir", lambda: tmp_path)

    report_path = service._write_sanomapro_grading_report(
        job_id="job-report",
        final_status="completed",
        summary="All visible exercise boxes were reviewed.",
        entries=[
            SanomaGradingReportEntry(
                student_name="Aada Harri",
                student_progress="Oppilas 6/31",
                exercise_label="Tehtävä 4",
                question_text="Käännä lause suomeksi.",
                answer_text="Pidätkö sinä enemmän ja saada nuorten äänet kuuluviin?",
                model_answer_text="Onko sinusta mahdollista vaikuttaa ja saada nuorten äänet kuuluviin?",
                points_text="1 / 2",
                basis_lines=["Summary: Meaning partly matches.", "Field 1: Multiple wording errors."],
                exercise_url="https://arvi.sanomapro.fi/as/teacher/review/demo/activity/a/document/b/exercise?studentId=123",
                status="scored",
            )
        ],
    )

    report_text = report_path.read_text(encoding="utf-8")

    assert "Student: Aada Harri (Oppilas 6/31)" in report_text
    assert "Answer: Pidätkö sinä enemmän ja saada nuorten äänet kuuluviin?" in report_text
    assert "Model Answer: Onko sinusta mahdollista vaikuttaa ja saada nuorten äänet kuuluviin?" in report_text
    assert "Points: 1 / 2" in report_text
    assert "Points basis:" in report_text
    assert "Field 1: Multiple wording errors." in report_text
    assert "https://arvi.sanomapro.fi/as/teacher/review/demo/activity/a/document/b/exercise?studentId=123" in report_text


def test_run_sanomapro_autonomous_exam_flow_only_completes_when_overview_is_fully_reviewed(monkeypatch, tmp_path) -> None:
    service = BrowserNavigationService(Settings())
    page = StubInteractivePage("https://arvi.sanomapro.fi/as/teacher/assignment/demo/review")
    session = StubInteractiveBrowserSession(page)

    async def fake_current_page_url(browser_session):
        return page.url

    async def fake_set_overlay(*args, **kwargs):
        return None

    async def fake_capture_page_state(browser_session, fallback_url, screenshot_path):
        return page.url, "Overview"

    async def fake_extract_overview_state(current_page):
        return SanomaOverviewState(
            route="/as/teacher/assignment/demo/review",
            assignment_title="Demo exam",
            visible_cell_count=3,
            reviewed_cell_count=2,
            unreviewed_cell_count=1,
            fully_reviewed=False,
            pending_candidates=[],
        )

    monkeypatch.setattr(service, "get_current_page_url", fake_current_page_url)
    monkeypatch.setattr(service, "_set_browser_status_overlay", fake_set_overlay)
    monkeypatch.setattr(service, "_capture_page_state", fake_capture_page_state)
    monkeypatch.setattr(service, "_extract_sanomapro_overview_state", fake_extract_overview_state)

    result = asyncio.run(
        service._run_sanomapro_autonomous_exam_flow(
            ExamSessionGradingTaskCreate(instructions="Score the answer."),
            "job-overview-incomplete",
            session,
            current_url=page.url,
            provider="ollama",
            screenshot_path=tmp_path / "result.png",
        )
    )

    assert result.status == "failed"
    assert "not yet fully blue/reviewed" in result.summary
    assert result.report_path is not None
    assert Path(result.report_path).exists()
    assert "No exercise evaluations were recorded" in Path(result.report_path).read_text(encoding="utf-8")


def test_run_sanomapro_autonomous_exam_flow_completes_when_overview_is_fully_reviewed(monkeypatch, tmp_path) -> None:
    service = BrowserNavigationService(Settings())
    page = StubInteractivePage("https://arvi.sanomapro.fi/as/teacher/assignment/demo/review")
    session = StubInteractiveBrowserSession(page)

    async def fake_current_page_url(browser_session):
        return page.url

    async def fake_set_overlay(*args, **kwargs):
        return None

    async def fake_capture_page_state(browser_session, fallback_url, screenshot_path):
        return page.url, "Overview"

    async def fake_extract_overview_state(current_page):
        return SanomaOverviewState(
            route="/as/teacher/assignment/demo/review",
            assignment_title="Demo exam",
            visible_cell_count=3,
            reviewed_cell_count=3,
            unreviewed_cell_count=0,
            fully_reviewed=True,
            pending_candidates=[],
        )

    monkeypatch.setattr(service, "get_current_page_url", fake_current_page_url)
    monkeypatch.setattr(service, "_set_browser_status_overlay", fake_set_overlay)
    monkeypatch.setattr(service, "_capture_page_state", fake_capture_page_state)
    monkeypatch.setattr(service, "_extract_sanomapro_overview_state", fake_extract_overview_state)

    result = asyncio.run(
        service._run_sanomapro_autonomous_exam_flow(
            ExamSessionGradingTaskCreate(instructions="Score the answer."),
            "job-overview-complete",
            session,
            current_url=page.url,
            provider="ollama",
            screenshot_path=tmp_path / "result.png",
        )
    )

    assert result.status == "completed"
    assert "All 3 visible exercise boxes were already marked reviewed." == result.summary
    assert result.report_path is not None
    assert Path(result.report_path).exists()


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


def test_set_browser_status_overlay_injects_visual_overlay_script() -> None:
    service = BrowserNavigationService(Settings())
    page = StubInteractivePage("https://arvi.sanomapro.fi/as/teacher/assignment/demo/review")

    asyncio.run(
        service._set_browser_status_overlay(
            page,
            mode="running",
            headline="Selecting exercise",
            detail="Opening the next ungraded review cell.",
            meta={"Processed": 1, "Skipped": 0},
        )
    )

    assert any("__gradeagent_status_overlay__" in script for script in page.recorded_scripts)
    assert any("Selecting exercise" in script for script in page.recorded_scripts)


def test_sanomapro_exercise_overlay_meta_only_lists_answer_model_answer_and_points() -> None:
    service = BrowserNavigationService(Settings())
    exercise_state = SanomaExerciseState(
        route="https://arvi.sanomapro.fi/as/teacher/review/demo/activity/a/document/b/exercise",
        answer_text="Helsingfors",
        model_answer_text="Helsingfors",
        score_fields=[SanomaExerciseScoreField(index=0, max_score=4)],
    )

    meta = service._sanomapro_exercise_overlay_meta(exercise_state, points_text="4 / 4")

    assert meta == {
        "Oppilaan vastaus": "Helsingfors",
        "Mallivastaus": "Helsingfors",
        "Points": "4 / 4",
    }


def test_sanomapro_exercise_overlay_meta_includes_reasoning_when_present() -> None:
    service = BrowserNavigationService(Settings())
    exercise_state = SanomaExerciseState(
        route="https://arvi.sanomapro.fi/as/teacher/review/demo/activity/a/document/b/exercise",
        answer_text="Helsingfors",
        model_answer_text="Helsingfors",
        score_fields=[SanomaExerciseScoreField(index=0, max_score=4)],
    )

    meta = service._sanomapro_exercise_overlay_meta(
        exercise_state,
        points_text="4 / 4",
        reasoning_text="Full points because the student's answer matches the model answer exactly.",
    )

    assert meta == {
        "Oppilaan vastaus": "Helsingfors",
        "Mallivastaus": "Helsingfors",
        "Points": "4 / 4",
        "Reasoning": "Full points because the student's answer matches the model answer exactly.",
    }


def test_extract_sanomapro_exercise_state_targets_live_dom_answer_and_model_answer_nodes() -> None:
    service = BrowserNavigationService(Settings())

    class SelectorAwarePage(StubInteractivePage):
        async def evaluate(self, script: str) -> str:
            self.recorded_scripts.append(script)
            if (
                ".richtext-display .display" in script
                and ".selection-hint" in script
                and ".word-count" in script
                and ".answer-model .answer-container" in script
                and ".review-item__intro .assessment-content .contents" in script
            ):
                return json.dumps(
                    {
                        "route": self.url,
                        "assignment_title": "Koeviikon koe RUB14.7",
                        "student_name": "Aada Harri",
                        "student_progress": "Oppilas 6/31",
                        "current_student_index": 6,
                        "student_count": 31,
                        "exercise_label": "Tehtävä 4",
                        "current_section_name": "Text 4",
                        "current_progress_document_label": "4",
                        "current_progress_document_selector_index": 3,
                        "next_progress_document_selector_index": 4,
                        "next_progress_document_label": "Text 4 / 5",
                        "question_text": "Käännä lauseet suomeksi.\n4 Tycker du att det är mahdollista...",
                        "answer_text": "Pidätkö sinä enemmän ja saada nuorten äänet kuuluviin?",
                        "model_answer_text": "Onko sinusta mahdollista vaikuttaa ja saada nuorten äänet kuuluviin?",
                        "score_fields": [
                            {
                                "index": 0,
                                "label": "Pistemäärä / 2 pistettä",
                                "current_value": "",
                                "container_text": "Pistemäärä / 2 pistettä",
                                "max_score": 2,
                            }
                        ],
                        "progress_documents": [
                            {
                                "selector_index": 3,
                                "section_name": "Text 4",
                                "label": "4",
                                "reviewed": False,
                                "current": True,
                            },
                            {
                                "selector_index": 4,
                                "section_name": "Text 4",
                                "label": "5",
                                "reviewed": False,
                                "current": False,
                            },
                        ],
                        "previous_student_available": True,
                        "next_student_available": True,
                        "exit_available": True,
                        "score_tab_available": True,
                        "comments_tab_available": True,
                    }
                )
            return json.dumps(
                {
                    "route": self.url,
                    "assignment_title": "Koeviikon koe RUB14.7",
                    "student_name": "Aada Harri",
                    "student_progress": "Oppilas 6/31",
                    "current_student_index": 6,
                    "student_count": 31,
                    "exercise_label": "Tehtävä 4",
                    "current_section_name": "Text 4",
                    "current_progress_document_label": "4",
                    "current_progress_document_selector_index": 3,
                    "next_progress_document_selector_index": 4,
                    "next_progress_document_label": "Text 4 / 5",
                    "question_text": "Wrong fallback question",
                    "answer_text": "Valitse osa oppilaan vastauksesta ja lisää kommentti. 8",
                    "model_answer_text": "Mallivastaus",
                    "score_fields": [],
                    "progress_documents": [],
                    "previous_student_available": True,
                    "next_student_available": True,
                    "exit_available": True,
                    "score_tab_available": True,
                    "comments_tab_available": True,
                }
            )

    page = SelectorAwarePage(
        "https://arvi.sanomapro.fi/as/teacher/review/demo/activity/a/document/b/exercise"
    )

    state = asyncio.run(service._extract_sanomapro_exercise_state(page))

    assert state.question_text.startswith("Käännä lauseet suomeksi.")
    assert state.answer_text == "Pidätkö sinä enemmän ja saada nuorten äänet kuuluviin?"
    assert "Valitse osa oppilaan vastauksesta" not in state.answer_text
    assert state.model_answer_text == "Onko sinusta mahdollista vaikuttaa ja saada nuorten äänet kuuluviin?"
    assert state.current_student_index == 6
    assert state.student_count == 31
    assert state.current_section_name == "Text 4"
    assert state.current_progress_document_label == "4"
    assert state.next_progress_document_selector_index == 4
    assert state.next_progress_document_label == "Text 4 / 5"
    assert state.previous_student_available is True
    assert state.score_fields[0].max_score == 2


def test_run_sanomapro_autonomous_exam_flow_traverses_students_then_switches_exercise_from_menu(
    monkeypatch, tmp_path
) -> None:
    service = BrowserNavigationService(Settings())
    first_document_url = "https://arvi.sanomapro.fi/as/teacher/review/demo/activity/a/document/doc-1/exercise"
    second_document_url = "https://arvi.sanomapro.fi/as/teacher/review/demo/activity/a/document/doc-2/exercise"
    overview_url = "https://arvi.sanomapro.fi/as/teacher/assignment/demo/review"
    page = StubInteractivePage(first_document_url)
    session = StubInteractiveBrowserSession(page)

    start_state = SanomaExerciseState(
        route="/as/teacher/review/demo/activity/a/document/doc-1/exercise",
        assignment_title="Demo exam",
        student_name="Ada",
        student_progress="Oppilas 2/3",
        current_student_index=2,
        student_count=3,
        exercise_label="Tehtävä 1",
        current_section_name="Text 4",
        current_progress_document_label="1",
        current_progress_document_selector_index=0,
        next_progress_document_selector_index=1,
        next_progress_document_label="Text 4 / 2",
        score_fields=[SanomaExerciseScoreField(index=0, max_score=2)],
        previous_student_available=True,
        next_student_available=True,
        exit_available=True,
    )
    states = [
        SanomaExerciseState(
            route="/as/teacher/review/demo/activity/a/document/doc-1/exercise",
            assignment_title="Demo exam",
            student_name="Ada",
            student_progress="Oppilas 1/3",
            current_student_index=1,
            student_count=3,
            exercise_label="Tehtävä 1",
            current_section_name="Text 4",
            current_progress_document_label="1",
            current_progress_document_selector_index=0,
            next_progress_document_selector_index=1,
            next_progress_document_label="Text 4 / 2",
            question_text="Q1",
            answer_text="A1",
            model_answer_text="M1",
            score_fields=[SanomaExerciseScoreField(index=0, max_score=2)],
            previous_student_available=False,
            next_student_available=True,
            exit_available=True,
        ),
        SanomaExerciseState(
            route="/as/teacher/review/demo/activity/a/document/doc-1/exercise",
            assignment_title="Demo exam",
            student_name="Bert",
            student_progress="Oppilas 2/3",
            current_student_index=2,
            student_count=3,
            exercise_label="Tehtävä 1",
            current_section_name="Text 4",
            current_progress_document_label="1",
            current_progress_document_selector_index=0,
            next_progress_document_selector_index=1,
            next_progress_document_label="Text 4 / 2",
            question_text="Q2",
            answer_text="A2",
            model_answer_text="M2",
            score_fields=[SanomaExerciseScoreField(index=0, max_score=2)],
            previous_student_available=True,
            next_student_available=True,
            exit_available=True,
        ),
        SanomaExerciseState(
            route="/as/teacher/review/demo/activity/a/document/doc-1/exercise",
            assignment_title="Demo exam",
            student_name="Cora",
            student_progress="Oppilas 3/3",
            current_student_index=3,
            student_count=3,
            exercise_label="Tehtävä 1",
            current_section_name="Text 4",
            current_progress_document_label="1",
            current_progress_document_selector_index=0,
            next_progress_document_selector_index=1,
            next_progress_document_label="Text 4 / 2",
            question_text="Q3",
            answer_text="A3",
            model_answer_text="M3",
            score_fields=[SanomaExerciseScoreField(index=0, max_score=2)],
            previous_student_available=True,
            next_student_available=False,
            exit_available=True,
        ),
        SanomaExerciseState(
            route="/as/teacher/review/demo/activity/a/document/doc-2/exercise",
            assignment_title="Demo exam",
            student_name="Ada",
            student_progress="Oppilas 1/1",
            current_student_index=1,
            student_count=1,
            exercise_label="Tehtävä 2",
            current_section_name="Text 4",
            current_progress_document_label="2",
            current_progress_document_selector_index=1,
            next_progress_document_selector_index=None,
            next_progress_document_label=None,
            question_text="Q4",
            answer_text="A4",
            model_answer_text="M4",
            score_fields=[SanomaExerciseScoreField(index=0, max_score=2)],
            previous_student_available=False,
            next_student_available=False,
            exit_available=True,
        ),
    ]
    state_index = {"value": -1}
    rewind_calls: list[str] = []
    next_student_calls: list[str] = []
    next_document_calls: list[str] = []
    scored_students: list[str] = []
    exited_to_overview: list[str] = []

    async def fake_current_page_url(browser_session):
        return page.url

    async def fake_set_overlay(*args, **kwargs):
        return None

    async def fake_capture_page_state(browser_session, fallback_url, screenshot_path):
        return page.url, "Exercise"

    async def fake_extract_exercise_state(current_page):
        if state_index["value"] < 0:
            return start_state
        return states[state_index["value"]]

    async def fake_extract_overview_state(current_page):
        return SanomaOverviewState(
            route="/as/teacher/assignment/demo/review",
            assignment_title="Demo exam",
            visible_cell_count=4,
            reviewed_cell_count=4,
            unreviewed_cell_count=0,
            fully_reviewed=True,
            pending_candidates=[],
        )

    async def fake_ensure_score_fields_visible(current_page, current_url):
        return True

    async def fake_build_score_decision(payload, exercise_state):
        return SanomaScoreDecision(
            summary=f"Scored {exercise_state.student_name}",
            confidence=0.9,
            scores=[SanomaScoreDecisionField(index=0, score=2, rationale="Matches the model answer.")],
        )

    async def fake_apply_score(page_obj, current_url, exercise_state, decision, *, dry_run):
        scored_students.append(f"{exercise_state.exercise_label}:{exercise_state.student_progress}")
        return 1

    async def fake_rewind(page_obj, current_url, exercise_state):
        rewind_calls.append(exercise_state.student_progress or "-")
        state_index["value"] = 0
        page.url = first_document_url
        session.current_page_url = first_document_url
        return states[0]

    async def fake_next_student(page_obj, current_url):
        next_student_calls.append(states[state_index["value"]].student_progress or "-")
        state_index["value"] += 1
        page.url = first_document_url
        session.current_page_url = first_document_url
        return True

    async def fake_next_document(page_obj, current_url, exercise_state):
        next_document_calls.append(exercise_state.next_progress_document_label or "-")
        if exercise_state.next_progress_document_selector_index is None:
            return False
        state_index["value"] = 3
        page.url = second_document_url
        session.current_page_url = second_document_url
        return True

    async def fake_exit_to_overview(page_obj, current_url):
        exited_to_overview.append(current_url)
        page.url = overview_url
        session.current_page_url = overview_url
        return True

    monkeypatch.setattr(service, "get_current_page_url", fake_current_page_url)
    monkeypatch.setattr(service, "_set_browser_status_overlay", fake_set_overlay)
    monkeypatch.setattr(service, "_capture_page_state", fake_capture_page_state)
    monkeypatch.setattr(service, "_extract_sanomapro_exercise_state", fake_extract_exercise_state)
    monkeypatch.setattr(service, "_extract_sanomapro_overview_state", fake_extract_overview_state)
    monkeypatch.setattr(service, "_ensure_sanomapro_score_fields_visible", fake_ensure_score_fields_visible)
    monkeypatch.setattr(service, "_build_sanomapro_score_decision", fake_build_score_decision)
    monkeypatch.setattr(service, "_apply_sanomapro_score_decision", fake_apply_score)
    monkeypatch.setattr(service, "_rewind_sanomapro_exercise_to_first_student", fake_rewind)
    monkeypatch.setattr(service, "_go_to_next_sanomapro_student", fake_next_student)
    monkeypatch.setattr(service, "_open_sanomapro_next_progress_document", fake_next_document)
    monkeypatch.setattr(service, "_exit_sanomapro_exercise_to_overview", fake_exit_to_overview)

    result = asyncio.run(
        service._run_sanomapro_autonomous_exam_flow(
            ExamSessionGradingTaskCreate(instructions="Score the answer."),
            "job-student-traversal",
            session,
            current_url=page.url,
            provider="ollama",
            screenshot_path=tmp_path / "result.png",
        )
    )

    assert result.status == "completed"
    assert result.processed_answers == 4
    assert result.filled_point_fields == 4
    assert rewind_calls == ["Oppilas 2/3"]
    assert next_student_calls == ["Oppilas 1/3", "Oppilas 2/3"]
    assert next_document_calls == ["Text 4 / 2", "-"]
    assert len(exited_to_overview) == 1
    assert scored_students == [
        "Tehtävä 1:Oppilas 1/3",
        "Tehtävä 1:Oppilas 2/3",
        "Tehtävä 1:Oppilas 3/3",
        "Tehtävä 2:Oppilas 1/1",
    ]


def test_sanomapro_scoring_policy_detects_two_point_single_score_exercise() -> None:
    service = BrowserNavigationService(Settings())
    exercise_state = SanomaExerciseState(
        route="https://arvi.sanomapro.fi/as/teacher/review/demo/activity/a/document/b/exercise",
        score_fields=[SanomaExerciseScoreField(index=0, max_score=2)],
    )

    assert service._sanomapro_detect_scoring_profile(exercise_state) == "single_score_max_2"
    assert "give 1/2" in service._sanomapro_scoring_policy_text(exercise_state)
    assert "give 1.5/2" in service._sanomapro_scoring_policy_text(exercise_state)
    assert "means the same thing" in service._sanomapro_scoring_policy_text(exercise_state)
    assert "usually 0/2" in service._sanomapro_scoring_policy_text(exercise_state)


def test_sanomapro_scoring_policy_detects_three_point_single_score_exercise() -> None:
    service = BrowserNavigationService(Settings())
    exercise_state = SanomaExerciseState(
        route="https://arvi.sanomapro.fi/as/teacher/review/demo/activity/a/document/b/exercise",
        score_fields=[SanomaExerciseScoreField(index=0, max_score=3)],
    )

    assert service._sanomapro_detect_scoring_profile(exercise_state) == "single_score_max_3"
    assert "give 2/3" in service._sanomapro_scoring_policy_text(exercise_state)
    assert "give 2.5/3" in service._sanomapro_scoring_policy_text(exercise_state)
    assert "give 1/3" in service._sanomapro_scoring_policy_text(exercise_state)
    assert "means the same thing" in service._sanomapro_scoring_policy_text(exercise_state)
    assert "prefer 1/3 or 0/3 rather than 2/3" in service._sanomapro_scoring_policy_text(exercise_state)


def test_build_sanomapro_score_decision_includes_dom_detected_two_point_policy(monkeypatch) -> None:
    service = BrowserNavigationService(
        Settings().model_copy(
            update={
                "sanomapro_exercise_grading_provider": "vertex_ai",
                "sanomapro_exercise_grading_model": "gemini-3.1-pro-preview",
                "vertex_ai_project": "gradeagent-test",
            }
        )
    )
    exercise_state = SanomaExerciseState(
        route="https://arvi.sanomapro.fi/as/teacher/review/demo/activity/a/document/b/exercise",
        assignment_title="Demo exam",
        student_name="Eetu Ahola",
        exercise_label="Tehtävä 1",
        question_text="Kirjoita oikea muoto.",
        answer_text="Jag bor i Helsingfors",
        model_answer_text="Jag bor i Helsingfors.",
        score_fields=[
            SanomaExerciseScoreField(
                index=0,
                label="Pistemäärä",
                current_value="",
                container_text="Pistemäärä / 2 pistettä",
                max_score=2,
            )
        ],
    )

    class CapturingModel:
        def __init__(self) -> None:
            self.messages = None

        async def ainvoke(self, messages):
            self.messages = messages
            return AIMessage(
                content=json.dumps(
                    {
                        "summary": "Minor punctuation issue.",
                        "confidence": 0.91,
                        "scores": [{"index": 0, "score": 1.5, "rationale": "One small detail is wrong."}],
                    }
                )
            )

    model = CapturingModel()
    monkeypatch.setattr(
        "app.services.browser_navigation.build_explicit_grading_chat_model",
        lambda settings, provider, model_name, routing_tier="standard": model,
    )

    decision = asyncio.run(
        service._build_sanomapro_score_decision(
            ExamSessionGradingTaskCreate(instructions="Follow the exercise grading rules."),
            exercise_state,
        )
    )

    prompt_text = model.messages[1].content

    assert decision.scores[0].score == 1.5
    assert "Detected scoring profile from DOM:" in prompt_text
    assert "single_score_max_2" in prompt_text
    assert "give 1/2" in prompt_text
    assert "give 1.5/2" in prompt_text
    assert "meaning-equivalent phrasing as correct" in prompt_text
    assert "Do not be generous when several independent errors accumulate" in prompt_text
    assert "The `summary` must briefly explain why those points were awarded" in prompt_text
    assert "Every field `rationale` must explain why that specific score was chosen." in prompt_text


def test_build_sanomapro_score_decision_falls_back_when_model_returns_non_json(monkeypatch) -> None:
    service = BrowserNavigationService(
        Settings().model_copy(
            update={
                "sanomapro_exercise_grading_provider": "vertex_ai",
                "sanomapro_exercise_grading_model": "gemini-3.1-pro-preview",
                "vertex_ai_project": "gradeagent-test",
            }
        )
    )
    exercise_state = SanomaExerciseState(
        route="https://arvi.sanomapro.fi/as/teacher/review/demo/activity/a/document/b/exercise",
        assignment_title="Demo exam",
        student_name="Eetu Ahola",
        exercise_label="Tehtävä 1",
        question_text="Vad heter huvudstaden i Finland?",
        answer_text="Helsingfors",
        score_fields=[
            SanomaExerciseScoreField(
                index=0,
                label="Pistemäärä",
                current_value="",
                container_text="Pistemäärä / 4 pistettä",
                max_score=4,
            )
        ],
    )

    class FakeModel:
        async def ainvoke(self, messages):
            return AIMessage(content="This answer deserves 4 points because it is correct.")

    monkeypatch.setattr(
        "app.services.browser_navigation.build_explicit_grading_chat_model",
        lambda settings, provider, model_name, routing_tier="standard": FakeModel(),
    )

    decision = asyncio.run(
        service._build_sanomapro_score_decision(
            ExamSessionGradingTaskCreate(instructions="Give full points for correct capitals."),
            exercise_state,
        )
    )

    assert decision.should_skip is False
    assert len(decision.scores) == 1
    assert 0 <= decision.scores[0].score <= 4
    assert "Heuristic fallback applied" in decision.summary


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
