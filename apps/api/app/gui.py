from __future__ import annotations

import asyncio
import threading
import tkinter as tk
from tkinter import messagebox
from uuid import uuid4

from app.config import Settings, get_settings
from app.prompt_library import PromptLibraryService, PromptTemplate
from app.schemas.api import ExamSessionGradingTaskCreate, ExamSessionGradingTaskResult
from app.services.browser_navigation import BrowserNavigationService, SanomaOverviewExerciseColumn


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return tuple(int(color[index : index + 2], 16) for index in (0, 2, 4))


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#" + "".join(f"{max(0, min(255, value)):02x}" for value in rgb)


def _blend(color_a: str, color_b: str, amount: float) -> str:
    rgb_a = _hex_to_rgb(color_a)
    rgb_b = _hex_to_rgb(color_b)
    return _rgb_to_hex(
        tuple(int(round(channel_a + (channel_b - channel_a) * amount)) for channel_a, channel_b in zip(rgb_a, rgb_b))
    )


def _rounded_rect_points(x1: int, y1: int, x2: int, y2: int, radius: int) -> list[int]:
    radius = max(0, min(radius, (x2 - x1) // 2, (y2 - y1) // 2))
    return [
        x1 + radius,
        y1,
        x2 - radius,
        y1,
        x2,
        y1,
        x2,
        y1 + radius,
        x2,
        y2 - radius,
        x2,
        y2,
        x2 - radius,
        y2,
        x1 + radius,
        y2,
        x1,
        y2,
        x1,
        y2 - radius,
        x1,
        y1 + radius,
        x1,
        y1,
    ]


class LiquidGlassButton(tk.Canvas):
    def __init__(
        self,
        parent,
        *,
        text: str,
        command,
        accent: str,
        width: int = 160,
        height: int = 50,
    ) -> None:
        background = parent.cget("bg")
        super().__init__(
            parent,
            width=width,
            height=height,
            bg=background,
            highlightthickness=0,
            bd=0,
            relief="flat",
            cursor="hand2",
        )
        self.command = command
        self.text = text
        self.accent = accent
        self.button_width = width
        self.button_height = height
        self.state = "normal"
        self.hovered = False
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)
        self._redraw()

    def set_state(self, state: str) -> None:
        self.state = state
        self.configure(cursor="hand2" if state == "normal" else "arrow")
        self._redraw()

    def set_text(self, text: str) -> None:
        self.text = text
        self._redraw()

    def _palette(self) -> tuple[str, str, str, str]:
        if self.state != "normal":
            fill = _blend(self.accent, "#ffffff", 0.62)
            border = _blend(fill, "#8ea0b5", 0.34)
            text = _blend("#ffffff", "#5b6b80", 0.64)
            glow = _blend(fill, "#ffffff", 0.35)
            return fill, border, text, glow
        if self.hovered:
            fill = _blend(self.accent, "#ffffff", 0.16)
            border = _blend(fill, "#ffffff", 0.3)
            text = "#ffffff"
            glow = _blend(self.accent, "#ffffff", 0.42)
            return fill, border, text, glow
        fill = self.accent
        border = _blend(fill, "#ffffff", 0.28)
        text = "#ffffff"
        glow = _blend(fill, "#ffffff", 0.5)
        return fill, border, text, glow

    def _redraw(self) -> None:
        self.delete("all")
        fill, border, text_color, glow = self._palette()
        width = self.button_width
        height = self.button_height
        radius = 22
        self.create_polygon(
            _rounded_rect_points(4, 6, width - 4, height - 2, radius),
            smooth=True,
            fill=_blend(glow, "#ffffff", 0.18),
            outline="",
        )
        self.create_polygon(
            _rounded_rect_points(2, 2, width - 2, height - 6, radius),
            smooth=True,
            fill=fill,
            outline=border,
            width=1,
        )
        self.create_line(18, 13, width - 18, 13, fill=_blend("#ffffff", fill, 0.18), width=1)
        self.create_text(
            width // 2,
            height // 2 - 2,
            text=self.text,
            fill=text_color,
            font=("SF Pro Text", 12, "bold"),
        )

    def _on_enter(self, _event) -> None:
        if self.state != "normal":
            return
        self.hovered = True
        self._redraw()

    def _on_leave(self, _event) -> None:
        self.hovered = False
        self._redraw()

    def _on_click(self, _event) -> None:
        if self.state != "normal":
            return
        if callable(self.command):
            self.command()


class GradeAgentGuiController:
    def __init__(
        self,
        settings: Settings | None = None,
        service: BrowserNavigationService | None = None,
    ) -> None:
        self.settings = settings or get_settings().model_copy(
            update={
                "browser_headless": False,
                "browser_attach_to_existing_chrome": False,
            }
        )
        self.service = service or BrowserNavigationService(self.settings)
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, name="gradeagent-gui-loop", daemon=True)
        self._thread.start()
        self._browser_session = None
        self._session_id: str | None = None

    @property
    def has_browser_session(self) -> bool:
        return self._browser_session is not None

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _call(self, coro):
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result()

    def ensure_browser_started(self) -> str:
        if self._browser_session is not None and self._session_id:
            return self._session_id

        session_id, browser_session = self._call(self.service.launch_interactive_browser(str(uuid4())))
        self._session_id = session_id
        self._browser_session = browser_session
        return session_id

    def refresh_exercises(self) -> list[SanomaOverviewExerciseColumn]:
        if self._browser_session is None:
            raise RuntimeError("Käynnistä GradeAgent-selain ensin.")
        overview_state = self._call(self.service.inspect_sanomapro_overview(self._browser_session))
        return [column for column in overview_state.exercise_columns if column.pending_cell_count > 0]

    def grade_exercise(
        self,
        *,
        column_key: str,
        instructions: str,
        max_steps: int = 260,
    ) -> ExamSessionGradingTaskResult:
        if self._browser_session is None:
            raise RuntimeError("Käynnistä GradeAgent-selain ensin.")

        payload = ExamSessionGradingTaskCreate(
            instructions=instructions.strip(),
            max_steps=max_steps,
        )
        return self._call(
            self.service.grade_sanomapro_exercise_column_from_current_page(
                payload=payload,
                job_id=str(uuid4()),
                browser_session=self._browser_session,
                column_key=column_key,
            )
        )

    def shutdown(self) -> None:
        browser_session = self._browser_session
        session_id = self._session_id
        self._browser_session = None
        self._session_id = None

        try:
            if browser_session is not None:
                self._call(browser_session.kill())
        finally:
            if session_id:
                self.service.cleanup_browser_artifacts(current_job_id=session_id)
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=2.0)
            self._loop.close()


class GradeAgentGuiApp:
    def __init__(self, controller: GradeAgentGuiController) -> None:
        self.controller = controller
        self.prompt_library = PromptLibraryService()
        self.prompt_templates: list[PromptTemplate] = self.prompt_library.load_prompts()
        self.current_columns: list[SanomaOverviewExerciseColumn] = []
        self.exercise_prompt_selection: dict[str, str] = {}
        self.exercise_panels: dict[str, dict[str, object]] = {}
        self.exercise_prompt_vars: dict[str, tk.StringVar] = {}
        self.nav_buttons: dict[str, LiquidGlassButton] = {}
        self.current_page_key = "control"
        self.selected_prompt_id: str | None = self.prompt_templates[0].prompt_id if self.prompt_templates else None
        self.draft_prompt: PromptTemplate | None = None
        self.busy = False

        self.root = tk.Tk()
        self.root.title("GradeAgent")
        self.root.geometry("1240x840")
        self.root.minsize(980, 720)
        self.colors = {
            "window": "#d8e3ef",
            "card": "#f7fbff",
            "card_alt": "#eef4fb",
            "card_border": "#ffffff",
            "card_shadow": "#c7d3e0",
            "sidebar": "#d6e0ea",
            "text": "#102132",
            "muted": "#5d7085",
            "prompt_bg": "#fbfdff",
            "footer_bg": "#e7eef6",
            "green": "#34c759",
            "blue": "#0a84ff",
            "mint": "#32d7c5",
            "amber": "#ff9f0a",
        }
        self.root.configure(bg=self.colors["window"])
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.status_var = tk.StringVar(
            value="Avaa selain, siirry Sanoman kokeen yleisnäkymään ja hae sitten arvioitavat tehtävät."
        )
        self.result_var = tk.StringVar(value="Yhtään tehtävää ei ole vielä arvioitu.")
        self.library_summary_var = tk.StringVar(value="")
        self.prompt_mode_var = tk.StringVar(value="")
        self.prompt_hint_var = tk.StringVar(
            value=(
                "Tuetut paikkamerkit: (STUDENT), (PROGRESSION), (OBJECTIVE), (TARGET), (ANSWER), "
                "(MODELANSWER), (MAXPOINTS), (GROUP), (STUDENTS), (CATEGORY), (EXERCISE NUMBER). "
                "Vanhat paikkamerkit kuten (SWE PHRASE) ja (FIN ANSWER) toimivat edelleen."
            )
        )

        self._build_layout()
        self._reload_prompt_templates()
        self._show_page("control")

    def _make_glass_card(
        self,
        parent,
        *,
        bg: str | None = None,
        padx: int = 20,
        pady: int = 20,
    ) -> tuple[tk.Frame, tk.Frame]:
        outer = tk.Frame(parent, bg=self.colors["window"], padx=0, pady=0)
        shadow = tk.Frame(outer, bg=self.colors["card_shadow"], height=1)
        shadow.pack(fill="x", side="bottom", padx=14)
        frame = tk.Frame(
            outer,
            bg=bg or self.colors["card"],
            highlightbackground=self.colors["card_border"],
            highlightthickness=1,
            bd=0,
            padx=padx,
            pady=pady,
        )
        frame.pack(fill="both", expand=True)
        return outer, frame

    def _build_layout(self) -> None:
        shell = tk.Frame(self.root, bg=self.colors["window"])
        shell.pack(fill="both", expand=True, padx=20, pady=20)

        sidebar_outer, sidebar = self._make_glass_card(shell, bg=self.colors["sidebar"], padx=18, pady=20)
        sidebar_outer.pack(side="left", fill="y")
        sidebar_outer.configure(width=220)
        sidebar_outer.pack_propagate(False)
        tk.Label(
            sidebar,
            text="GradeAgent",
            bg=self.colors["sidebar"],
            fg=self.colors["text"],
            font=("SF Pro Display", 22, "bold"),
        ).pack(anchor="w")
        tk.Label(
            sidebar,
            text="Arviointityökalu Sanoman kokeille",
            bg=self.colors["sidebar"],
            fg=self.colors["muted"],
            font=("SF Pro Text", 11),
            wraplength=160,
            justify="left",
        ).pack(anchor="w", pady=(6, 20))

        self.nav_buttons["control"] = LiquidGlassButton(
            sidebar,
            text="Ohjaus",
            command=lambda: self._show_page("control"),
            accent=self.colors["blue"],
            width=168,
        )
        self.nav_buttons["control"].pack(anchor="w", pady=(0, 10))
        self.nav_buttons["criteria"] = LiquidGlassButton(
            sidebar,
            text="Kriteerit",
            command=lambda: self._show_page("criteria"),
            accent=self.colors["mint"],
            width=168,
        )
        self.nav_buttons["criteria"].pack(anchor="w")

        tk.Label(
            sidebar,
            text="GUI-tila käyttää vain Kriteerit-sivun kirjastossa olevia kriteerejä.",
            bg=self.colors["sidebar"],
            fg=self.colors["text"],
            font=("SF Pro Text", 10),
            justify="left",
            wraplength=160,
        ).pack(anchor="w", pady=(22, 0))

        right_shell = tk.Frame(shell, bg=self.colors["window"])
        right_shell.pack(side="left", fill="both", expand=True, padx=(18, 0))

        self.page_container = tk.Frame(right_shell, bg=self.colors["window"])
        self.page_container.pack(fill="both", expand=True)

        footer_outer, footer = self._make_glass_card(right_shell, bg=self.colors["footer_bg"], padx=24, pady=18)
        footer_outer.pack(fill="x", pady=(14, 0))
        tk.Label(
            footer,
            textvariable=self.status_var,
            bg=self.colors["footer_bg"],
            fg=self.colors["text"],
            font=("SF Pro Text", 11, "bold"),
            justify="left",
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            footer,
            textvariable=self.result_var,
            bg=self.colors["footer_bg"],
            fg=self.colors["muted"],
            font=("SF Pro Text", 10),
            justify="left",
            anchor="w",
        ).pack(fill="x", pady=(6, 0))

        self.page_frames: dict[str, tk.Frame] = {}
        self.page_frames["control"] = tk.Frame(self.page_container, bg=self.colors["window"])
        self.page_frames["criteria"] = tk.Frame(self.page_container, bg=self.colors["window"])
        for frame in self.page_frames.values():
            frame.place(relx=0, rely=0, relwidth=1, relheight=1)

        self._build_control_page()
        self._build_criteria_page()

    def _build_control_page(self) -> None:
        page = self.page_frames["control"]

        header_outer, header = self._make_glass_card(page, bg=self.colors["card_alt"], padx=26, pady=22)
        header_outer.pack(fill="x", pady=(0, 14))
        tk.Label(
            header,
            text="Ohjaus",
            bg=self.colors["card_alt"],
            fg=self.colors["text"],
            font=("SF Pro Display", 24, "bold"),
        ).pack(anchor="w")
        tk.Label(
            header,
            text="Avaa hallittu selain, hae arvioitavat tehtävät yleisnäkymästä ja arvioi yksi tehtäväsarja kerrallaan.",
            bg=self.colors["card_alt"],
            fg=self.colors["muted"],
            font=("SF Pro Text", 12),
            justify="left",
            wraplength=860,
        ).pack(anchor="w", pady=(6, 0))

        controls_outer, controls = self._make_glass_card(page, bg=self.colors["card"], padx=24, pady=22)
        controls_outer.pack(fill="x", pady=(0, 14))
        tk.Label(
            controls,
            text="Käynnistys",
            bg=self.colors["card"],
            fg=self.colors["text"],
            font=("SF Pro Text", 13, "bold"),
        ).pack(anchor="w")
        tk.Label(
            controls,
            text="Avaa selain vihreällä painikkeella. Sininen painike ilmestyy vasta, kun selain on varmasti käynnissä.",
            bg=self.colors["card"],
            fg=self.colors["muted"],
            font=("SF Pro Text", 11),
            justify="left",
            wraplength=860,
        ).pack(anchor="w", pady=(4, 14))
        self.control_row = tk.Frame(controls, bg=self.colors["card"])
        self.control_row.pack(fill="x")
        self.start_button = LiquidGlassButton(
            self.control_row,
            text="Käynnistä",
            command=self._start_browser,
            accent=self.colors["green"],
            width=170,
        )
        self.start_button.pack(side="left")
        self.exam_opened_button = LiquidGlassButton(
            self.control_row,
            text="Koe avattu",
            command=self._refresh_exercises,
            accent=self.colors["blue"],
            width=190,
        )
        self.exam_opened_button.set_state("disabled")

        library_outer, library = self._make_glass_card(page, bg=self.colors["card"], padx=24, pady=22)
        library_outer.pack(fill="x", pady=(0, 14))
        tk.Label(
            library,
            text="Kriteerikirjasto",
            bg=self.colors["card"],
            fg=self.colors["text"],
            font=("SF Pro Text", 13, "bold"),
        ).pack(anchor="w")
        tk.Label(
            library,
            text="Jokaiselle tehtäväpaneelille valitaan kirjastosta yksi kriteeri. Vain kirjaston kriteerejä käytetään arvioinnissa.",
            bg=self.colors["card"],
            fg=self.colors["muted"],
            font=("SF Pro Text", 11),
            justify="left",
            wraplength=860,
        ).pack(anchor="w", pady=(4, 8))
        tk.Label(
            library,
            textvariable=self.library_summary_var,
            bg=self.colors["card"],
            fg=self.colors["text"],
            font=("SF Pro Text", 11),
            justify="left",
            anchor="w",
            wraplength=860,
        ).pack(fill="x")

        exercises_outer, exercises = self._make_glass_card(page, bg=self.colors["card"], padx=24, pady=22)
        exercises_outer.pack(fill="both", expand=True)
        tk.Label(
            exercises,
            text="Arvioitavat tehtävät",
            bg=self.colors["card"],
            fg=self.colors["text"],
            font=("SF Pro Text", 13, "bold"),
        ).pack(anchor="w")
        tk.Label(
            exercises,
            text="Yksi paneeli vastaa yhtä tehtäväsarjaa. Valitse ensin kriteeri, sitten aloita arviointi.",
            bg=self.colors["card"],
            fg=self.colors["muted"],
            font=("SF Pro Text", 11),
            justify="left",
            wraplength=860,
        ).pack(anchor="w", pady=(4, 10))

        canvas_frame = tk.Frame(exercises, bg=self.colors["card"])
        canvas_frame.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(canvas_frame, bg=self.colors["card"], highlightthickness=0)
        scrollbar = tk.Scrollbar(canvas_frame, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollable_frame = tk.Frame(self.canvas, bg=self.colors["card"])
        self.scrollable_frame.bind(
            "<Configure>",
            lambda event: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self.scrollable_window = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.bind(
            "<Configure>",
            lambda event: self.canvas.itemconfigure(self.scrollable_window, width=event.width),
        )

    def _build_criteria_page(self) -> None:
        page = self.page_frames["criteria"]

        header_outer, header = self._make_glass_card(page, bg=self.colors["card_alt"], padx=26, pady=22)
        header_outer.pack(fill="x", pady=(0, 14))
        tk.Label(
            header,
            text="Kriteerit",
            bg=self.colors["card_alt"],
            fg=self.colors["text"],
            font=("SF Pro Display", 24, "bold"),
        ).pack(anchor="w")
        tk.Label(
            header,
            text="Tämä kirjasto toimii arvioinnin ainoana promptilähteenä. Luo omat kriteerit täällä ja valitse ne sitten Ohjaus-sivulla.",
            bg=self.colors["card_alt"],
            fg=self.colors["muted"],
            font=("SF Pro Text", 12),
            justify="left",
            wraplength=860,
        ).pack(anchor="w", pady=(6, 0))

        content_row = tk.Frame(page, bg=self.colors["window"])
        content_row.pack(fill="both", expand=True)

        list_outer, list_frame = self._make_glass_card(content_row, bg=self.colors["card"], padx=18, pady=18)
        list_outer.pack(side="left", fill="y", padx=(0, 14))
        list_outer.configure(width=300)
        list_outer.pack_propagate(False)
        tk.Label(
            list_frame,
            text="Kirjasto",
            bg=self.colors["card"],
            fg=self.colors["text"],
            font=("SF Pro Text", 13, "bold"),
        ).pack(anchor="w")
        tk.Label(
            list_frame,
            text="Finder-tyylinen näkymä tallennetuille kriteereille.",
            bg=self.colors["card"],
            fg=self.colors["muted"],
            font=("SF Pro Text", 10),
        ).pack(anchor="w", pady=(4, 10))
        self.prompt_listbox = tk.Listbox(
            list_frame,
            font=("SF Pro Text", 11),
            relief="flat",
            bg=self.colors["prompt_bg"],
            fg=self.colors["text"],
            highlightbackground=_blend(self.colors["window"], "#ffffff", 0.45),
            highlightthickness=1,
            activestyle="none",
            selectbackground=self.colors["blue"],
            selectforeground="#ffffff",
        )
        self.prompt_listbox.pack(fill="both", expand=True)
        self.prompt_listbox.bind("<<ListboxSelect>>", lambda _event: self._on_prompt_selected())
        self.new_prompt_button = LiquidGlassButton(
            list_frame,
            text="Uusi kriteeri",
            command=self._create_new_prompt,
            accent=self.colors["amber"],
            width=168,
        )
        self.new_prompt_button.pack(anchor="w", pady=(12, 0))

        editor_outer, editor = self._make_glass_card(content_row, bg=self.colors["card"], padx=22, pady=22)
        editor_outer.pack(side="left", fill="both", expand=True)
        tk.Label(
            editor,
            text="Valitun kriteerin tiedot",
            bg=self.colors["card"],
            fg=self.colors["text"],
            font=("SF Pro Text", 13, "bold"),
        ).pack(anchor="w")
        tk.Label(
            editor,
            textvariable=self.prompt_mode_var,
            bg=self.colors["card"],
            fg=self.colors["muted"],
            font=("SF Pro Text", 10),
            justify="left",
            anchor="w",
            wraplength=640,
        ).pack(fill="x", pady=(4, 14))

        tk.Label(
            editor,
            text="Nimi",
            bg=self.colors["card"],
            fg=self.colors["text"],
            font=("SF Pro Text", 11, "bold"),
        ).pack(anchor="w")
        self.prompt_title_entry = tk.Entry(
            editor,
            font=("SF Pro Text", 12),
            relief="flat",
            bg=self.colors["prompt_bg"],
            fg=self.colors["text"],
            insertbackground=self.colors["text"],
            highlightbackground=_blend(self.colors["window"], "#ffffff", 0.45),
            highlightthickness=1,
        )
        self.prompt_title_entry.pack(fill="x", pady=(6, 14), ipady=8)

        tk.Label(
            editor,
            text="Prompti",
            bg=self.colors["card"],
            fg=self.colors["text"],
            font=("SF Pro Text", 11, "bold"),
        ).pack(anchor="w")
        self.prompt_body_text = tk.Text(
            editor,
            height=16,
            wrap="word",
            font=("SF Pro Text", 11),
            relief="flat",
            bg=self.colors["prompt_bg"],
            fg=self.colors["text"],
            insertbackground=self.colors["text"],
            highlightbackground=_blend(self.colors["window"], "#ffffff", 0.45),
            highlightthickness=1,
            padx=12,
            pady=12,
        )
        self.prompt_body_text.pack(fill="both", expand=True, pady=(6, 12))
        tk.Label(
            editor,
            textvariable=self.prompt_hint_var,
            bg=self.colors["card"],
            fg=self.colors["muted"],
            font=("SF Pro Text", 10),
            justify="left",
            wraplength=640,
        ).pack(anchor="w")
        self.save_prompt_button = LiquidGlassButton(
            editor,
            text="Tallenna kriteeri",
            command=self._save_current_prompt,
            accent=self.colors["mint"],
            width=190,
        )
        self.save_prompt_button.pack(anchor="e", pady=(14, 0))

    def _show_page(self, page_key: str) -> None:
        self.current_page_key = page_key
        self.page_frames[page_key].lift()
        for key, button in self.nav_buttons.items():
            button.set_state("disabled" if key == page_key else "normal")

    def _prompt_by_id(self, prompt_id: str | None) -> PromptTemplate | None:
        return next((prompt for prompt in self.prompt_templates if prompt.prompt_id == prompt_id), None)

    def _prompt_by_title(self, title: str) -> PromptTemplate | None:
        return next((prompt for prompt in self.prompt_templates if prompt.title == title), None)

    def _prompt_title_by_id(self, prompt_id: str | None) -> str:
        prompt = self._prompt_by_id(prompt_id)
        return prompt.title if prompt is not None else ""

    def _refresh_library_summary(self) -> None:
        count = len(self.prompt_templates)
        if count == 0:
            self.library_summary_var.set("Kirjastossa ei ole vielä yhtään kriteeriä.")
            return
        titles = ", ".join(prompt.title for prompt in self.prompt_templates[:3])
        suffix = "" if count <= 3 else f" ... (+{count - 3} muuta)"
        self.library_summary_var.set(
            f"Kirjastossa on nyt {count} kriteeriä. Ensimmäiset: {titles}{suffix}."
        )

    def _reload_prompt_templates(self, *, selected_prompt_id: str | None = None) -> None:
        self.prompt_templates = self.prompt_library.load_prompts()
        if self.prompt_templates and selected_prompt_id is None:
            selected_prompt_id = self.selected_prompt_id or self.prompt_templates[0].prompt_id
        self.selected_prompt_id = selected_prompt_id or (self.prompt_templates[0].prompt_id if self.prompt_templates else None)
        self._refresh_library_summary()

        if hasattr(self, "prompt_listbox"):
            self.prompt_listbox.delete(0, tk.END)
            for prompt in self.prompt_templates:
                suffix = "  • oletus" if prompt.built_in else ""
                self.prompt_listbox.insert(tk.END, f"{prompt.title}{suffix}")
            self._select_prompt_in_list(self.selected_prompt_id)

        if self.current_columns:
            self._render_exercise_panels(self.current_columns)

    def _select_prompt_in_list(self, prompt_id: str | None) -> None:
        self.prompt_listbox.selection_clear(0, tk.END)
        if prompt_id is None:
            return
        for index, prompt in enumerate(self.prompt_templates):
            if prompt.prompt_id == prompt_id:
                self.prompt_listbox.selection_set(index)
                self.prompt_listbox.activate(index)
                self.prompt_listbox.see(index)
                self._load_prompt_into_editor(prompt)
                return

    def _load_prompt_into_editor(self, prompt: PromptTemplate) -> None:
        self.selected_prompt_id = prompt.prompt_id
        self.draft_prompt = prompt.model_copy()
        self.prompt_title_entry.configure(state="normal")
        self.prompt_body_text.configure(state="normal")
        self.prompt_title_entry.delete(0, tk.END)
        self.prompt_title_entry.insert(0, prompt.title)
        self.prompt_body_text.delete("1.0", tk.END)
        self.prompt_body_text.insert("1.0", prompt.body)
        if prompt.built_in:
            self.prompt_mode_var.set("Oletuskriteeri. Tätä ei voi muokata suoraan. Luo uusi kriteeri, jos haluat oman version.")
            self.prompt_title_entry.configure(state="disabled")
            self.prompt_body_text.configure(state="disabled")
            self.save_prompt_button.set_state("disabled")
        else:
            self.prompt_mode_var.set("Mukautettu kriteeri. Voit muokata ja tallentaa tämän.")
            self.save_prompt_button.set_state("normal")

    def _on_prompt_selected(self) -> None:
        selection = self.prompt_listbox.curselection()
        if not selection:
            return
        prompt = self.prompt_templates[selection[0]]
        self._load_prompt_into_editor(prompt)

    def _create_new_prompt(self) -> None:
        self._show_page("criteria")
        self.draft_prompt = self.prompt_library.new_custom_prompt()
        self.selected_prompt_id = self.draft_prompt.prompt_id
        self.prompt_mode_var.set("Uusi mukautettu kriteeri. Anna nimi ja sisältö, sitten tallenna.")
        self.prompt_title_entry.configure(state="normal")
        self.prompt_body_text.configure(state="normal")
        self.prompt_title_entry.delete(0, tk.END)
        self.prompt_title_entry.insert(0, self.draft_prompt.title)
        self.prompt_body_text.delete("1.0", tk.END)
        self.save_prompt_button.set_state("normal")
        self.prompt_listbox.selection_clear(0, tk.END)

    def _save_current_prompt(self) -> None:
        if self.draft_prompt is None:
            self._create_new_prompt()
        if self.draft_prompt is None:
            return
        title = self.prompt_title_entry.get().strip()
        body = self.prompt_body_text.get("1.0", "end").strip()
        if not title:
            messagebox.showerror("GradeAgent", "Anna kriteerille nimi ennen tallennusta.")
            return
        if not body:
            messagebox.showerror("GradeAgent", "Kirjoita kriteerin sisältö ennen tallennusta.")
            return
        prompt = PromptTemplate(
            prompt_id=self.draft_prompt.prompt_id,
            title=title,
            body=body,
            built_in=False,
        )
        saved_prompt = self.prompt_library.save_prompt(prompt)
        self.status_var.set(f"Kriteeri '{saved_prompt.title}' tallennettiin kirjastoon.")
        self.result_var.set("Kirjaston kriteerit ovat nyt käytettävissä Ohjaus-sivulla.")
        self._reload_prompt_templates(selected_prompt_id=saved_prompt.prompt_id)

    def run(self) -> None:
        self.root.mainloop()

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        start_state = "disabled" if busy or self.controller.has_browser_session else "normal"
        exam_state = "disabled" if busy or not self.controller.has_browser_session else "normal"
        self.start_button.set_state(start_state)
        if self.exam_opened_button.winfo_ismapped():
            self.exam_opened_button.set_state(exam_state)
        self.new_prompt_button.set_state("disabled" if busy else "normal")
        if hasattr(self, "save_prompt_button"):
            current_prompt = self._prompt_by_id(self.selected_prompt_id)
            if current_prompt is not None and current_prompt.built_in:
                self.save_prompt_button.set_state("disabled")
            else:
                self.save_prompt_button.set_state("disabled" if busy else "normal")
        for widgets in self.exercise_panels.values():
            start_button = widgets.get("start_button")
            if isinstance(start_button, LiquidGlassButton):
                start_button.set_state("disabled" if busy else "normal")

    def _run_background(self, *, status_text: str, work, on_success, on_error: str) -> None:
        if self.busy:
            return
        self._set_busy(True)
        self.status_var.set(status_text)

        def worker() -> None:
            try:
                result = work()
            except Exception as exc:
                self.root.after(0, lambda: self._background_failed(f"{on_error}: {exc}"))
                return
            self.root.after(0, lambda: self._background_succeeded(result, on_success))

        threading.Thread(target=worker, name="gradeagent-gui-work", daemon=True).start()

    def _background_failed(self, message: str) -> None:
        self._set_busy(False)
        self.status_var.set(message)
        messagebox.showerror("GradeAgent", message)

    def _background_succeeded(self, result, on_success) -> None:
        self._set_busy(False)
        on_success(result)

    def _start_browser(self) -> None:
        self._run_background(
            status_text="Käynnistetään GradeAgent-selain...",
            work=self.controller.ensure_browser_started,
            on_success=self._browser_started,
            on_error="GradeAgent-selaimen käynnistäminen epäonnistui",
        )

    def _browser_started(self, session_id: str) -> None:
        self.start_button.set_state("disabled")
        if not self.exam_opened_button.winfo_ismapped():
            self.exam_opened_button.pack(side="left", padx=(14, 0))
        self.exam_opened_button.set_state("normal")
        self.status_var.set(
            "Selain on auki. Kirjaudu tarvittaessa sisään, avaa Sanoman kokeen yleisnäkymä ja paina sitten 'Koe avattu'."
        )
        self.result_var.set(f"Selaimen istunto on valmis: {session_id}")

    def _refresh_exercises(self) -> None:
        self._run_background(
            status_text="Luetaan yleisnäkymän DOM-rakenne ja kerätään arvioimattomat tehtävät...",
            work=self.controller.refresh_exercises,
            on_success=self._exercises_loaded,
            on_error="Sanoman yleisnäkymää ei voitu lukea",
        )

    def _exercises_loaded(self, columns: list[SanomaOverviewExerciseColumn]) -> None:
        self.current_columns = columns
        self._render_exercise_panels(columns)
        if columns:
            self.status_var.set(
                f"Löytyi {len(columns)} arvioimatonta tehtäväpaneelia. Valitse paneelista kriteeri ja aloita arviointi."
            )
            self.result_var.set("Selain pysyy auki jokaisen arvioinnin jälkeen. Päivitä näkymä uudelleen, jos kokeen tila muuttuu.")
        else:
            self.status_var.set("Nykyisestä yleisnäkymästä ei löytynyt arvioimattomia tehtäviä.")
            self.result_var.set("Jos tämä näyttää väärältä, varmista että olet kokeen yleisnäkymässä ja hae tehtävät uudelleen.")

    def _render_exercise_panels(self, columns: list[SanomaOverviewExerciseColumn]) -> None:
        for child in self.scrollable_frame.winfo_children():
            child.destroy()
        self.exercise_panels.clear()
        self.exercise_prompt_vars.clear()

        for column in columns:
            frame = tk.Frame(
                self.scrollable_frame,
                bg=self.colors["card_alt"],
                highlightbackground=self.colors["card_border"],
                highlightthickness=1,
                bd=0,
                padx=18,
                pady=18,
            )
            frame.pack(fill="x", pady=(0, 12))
            title = column.label or f"Tehtävä {column.column_index + 1}"
            category_bits = []
            if column.category_name:
                category_bits.append(f"Kategoria: {column.category_name}")
            if column.exercise_number:
                category_bits.append(f"Tehtävänumero: {column.exercise_number}")
            tk.Label(
                frame,
                text=title,
                bg=self.colors["card_alt"],
                fg=self.colors["text"],
                font=("SF Pro Text", 14, "bold"),
            ).pack(anchor="w")
            tk.Label(
                frame,
                text=(
                    " · ".join(
                        [
                            *category_bits,
                            f"Arvioimatta {column.pending_cell_count}/{column.total_cell_count}",
                            f"Valmiina {column.reviewed_cell_count}/{column.total_cell_count}",
                        ]
                    )
                ),
                bg=self.colors["card_alt"],
                fg=self.colors["muted"],
                font=("SF Pro Text", 10),
            ).pack(anchor="w", pady=(4, 12))

            selected_prompt_id = self.exercise_prompt_selection.get(column.column_key)
            if self._prompt_by_id(selected_prompt_id) is None and self.prompt_templates:
                selected_prompt_id = self.prompt_templates[0].prompt_id
            self.exercise_prompt_selection[column.column_key] = selected_prompt_id or ""

            selector_row = tk.Frame(frame, bg=self.colors["card_alt"])
            selector_row.pack(fill="x")
            tk.Label(
                selector_row,
                text="Valittu kriteeri",
                bg=self.colors["card_alt"],
                fg=self.colors["text"],
                font=("SF Pro Text", 11, "bold"),
            ).pack(side="left")

            prompt_var = tk.StringVar(value=self._prompt_title_by_id(selected_prompt_id))
            self.exercise_prompt_vars[column.column_key] = prompt_var
            prompt_titles = [prompt.title for prompt in self.prompt_templates] or ["Ei kriteerejä"]
            prompt_menu = tk.OptionMenu(
                selector_row,
                prompt_var,
                *prompt_titles,
                command=lambda selected_title, key=column.column_key: self._set_exercise_prompt_selection(key, selected_title),
            )
            prompt_menu.configure(
                font=("SF Pro Text", 10),
                bg=self.colors["prompt_bg"],
                fg=self.colors["text"],
                activebackground=self.colors["card"],
                activeforeground=self.colors["text"],
                relief="flat",
                highlightthickness=0,
            )
            prompt_menu["menu"].configure(
                font=("SF Pro Text", 10),
                bg=self.colors["prompt_bg"],
                fg=self.colors["text"],
                activebackground=self.colors["blue"],
                activeforeground="#ffffff",
            )
            prompt_menu.pack(side="right")

            selected_prompt = self._prompt_by_id(self.exercise_prompt_selection.get(column.column_key))
            preview_text = (
                selected_prompt.body
                if selected_prompt is not None
                else "Valitse ensin kriteeri Kriteerit-kirjastosta."
            )
            prompt_preview = tk.Text(
                frame,
                height=6,
                wrap="word",
                font=("SF Pro Text", 11),
                relief="flat",
                bg=self.colors["prompt_bg"],
                fg=self.colors["text"],
                insertbackground=self.colors["text"],
                highlightbackground=_blend(self.colors["window"], "#ffffff", 0.45),
                highlightthickness=1,
                padx=12,
                pady=12,
            )
            prompt_preview.pack(fill="x", pady=(10, 0))
            prompt_preview.insert("1.0", preview_text)
            prompt_preview.configure(state="disabled")

            status_label = tk.Label(
                frame,
                text="Valmis arvioitavaksi.",
                bg=self.colors["card_alt"],
                fg=self.colors["muted"],
                font=("SF Pro Text", 10),
                justify="left",
                anchor="w",
            )
            status_label.pack(fill="x", pady=(10, 0))
            start_button = LiquidGlassButton(
                frame,
                text="Aloita arviointi",
                command=lambda key=column.column_key: self._grade_exercise(key),
                accent=self.colors["blue"],
                width=186,
            )
            start_button.pack(anchor="e", pady=(12, 0))
            self.exercise_panels[column.column_key] = {
                "prompt_preview": prompt_preview,
                "prompt_var": prompt_var,
                "prompt_menu": prompt_menu,
                "status_label": status_label,
                "start_button": start_button,
                "column": column,
            }

    def _set_exercise_prompt_selection(self, column_key: str, selected_title: str) -> None:
        prompt = self._prompt_by_title(selected_title)
        if prompt is None:
            return
        self.exercise_prompt_selection[column_key] = prompt.prompt_id
        widgets = self.exercise_panels.get(column_key)
        if not widgets:
            return
        prompt_preview = widgets.get("prompt_preview")
        if isinstance(prompt_preview, tk.Text):
            prompt_preview.configure(state="normal")
            prompt_preview.delete("1.0", tk.END)
            prompt_preview.insert("1.0", prompt.body)
            prompt_preview.configure(state="disabled")

    def _grade_exercise(self, column_key: str) -> None:
        widgets = self.exercise_panels.get(column_key)
        if not widgets:
            return
        selected_prompt = self._prompt_by_id(self.exercise_prompt_selection.get(column_key))
        if selected_prompt is None:
            messagebox.showerror("GradeAgent", "Valitse tehtävälle kriteeri ennen arvioinnin käynnistystä.")
            return
        status_label = widgets.get("status_label")
        if isinstance(status_label, tk.Label):
            status_label.configure(text=f"Arvioidaan kriteerillä: {selected_prompt.title}")

        def work():
            result = self.controller.grade_exercise(column_key=column_key, instructions=selected_prompt.body)
            columns = self.controller.refresh_exercises()
            return result, columns

        self._run_background(
            status_text="Arvioidaan valittu tehtävä ja päivitetään yleisnäkymä...",
            work=work,
            on_success=lambda data: self._exercise_graded(column_key, data[0], data[1]),
            on_error="Tehtävän arviointi epäonnistui",
        )

    def _exercise_graded(
        self,
        column_key: str,
        result: ExamSessionGradingTaskResult,
        columns: list[SanomaOverviewExerciseColumn],
    ) -> None:
        widgets = self.exercise_panels.get(column_key)
        if widgets:
            status_label = widgets.get("status_label")
            if isinstance(status_label, tk.Label):
                status_label.configure(text=result.summary)
        self.result_var.set(f"{result.summary} Raportti: {result.report_path or '-'}")
        self.status_var.set("Selain on yhä auki. Valitse seuraava tehtävä, kun haluat jatkaa.")
        self.current_columns = columns
        self._render_exercise_panels(columns)

    def _on_close(self) -> None:
        try:
            self.controller.shutdown()
        finally:
            self.root.destroy()


def launch_gradeagent_gui() -> None:
    controller = GradeAgentGuiController()
    app = GradeAgentGuiApp(controller)
    app.run()


if __name__ == "__main__":
    launch_gradeagent_gui()
