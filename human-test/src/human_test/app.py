"""Choose and save a practice setup, then explicitly start the interview."""

import asyncio
import queue
import threading
import time
import tkinter as tk
from contextlib import suppress
from tkinter import messagebox, ttk

from training_client.capture import microphones, probe_microphone
from training_client.pms_client import ClientError
from training_client.runtime import SPEECH_STALL_LIMIT_MS as SPEECH_STALL_LIMIT_MS
from training_client.runtime import Runtime
from training_client.speech import patient_gender
from training_contracts.languages import DEFAULT_REGISTRY, get_pack
from training_contracts.scenarios import Vitals

from . import theme
from .camera_view import CameraView
from .config import Settings
from .manikin import Manikin
from .overflow_menu import OverflowMenu
from .retry_notice import RetryNotice
from .theme import BG, INK, MUTED, NAVY, TEAL

REHEARSAL_NOTICE = (
    "Fictional examples for staff rehearsal • Clinical approval is required before learner use."
)
VITALS = (
    ("temperature_c", "Temperature", "°C"),
    ("heart_rate_bpm", "Heart rate", "bpm"),
    ("pulse_bpm", "Pulse", "bpm"),
    ("respirations_per_minute", "Respirations", "/min"),
    ("systolic_mmhg", "Systolic BP", "mmHg"),
    ("diastolic_mmhg", "Diastolic BP", "mmHg"),
    ("spo2_percent", "Oxygen saturation", "%"),
    ("pain_0_10", "Pain score", "/10"),
)

LANGUAGES = {pack.name: pack.language for pack in DEFAULT_REGISTRY.all()}
DEFAULT_VOICE_CHOICE = "Default for this patient"
# Spoken only when the operator presses Hear, so a voice can be judged without a question.
VOICE_PREVIEW = {pack.language: pack.clarification for pack in DEFAULT_REGISTRY.all()}


# Capture is muted while speech is still reaching the device, so the patient's own answer is
# never heard back as the next question. Only a stall this long releases it, so a long answer
# is never cut into and a stuck device cannot strand input.
def _now():
    """The app's own clock seam, so tests can advance playback time without sleeping."""
    return time.monotonic()


def portrait(parent):
    c = tk.Canvas(parent, width=126, height=128, bg="white", highlightthickness=0)
    c.create_oval(8, 5, 118, 115, fill="#e3f2f1", outline="")
    c.create_arc(23, 62, 105, 148, start=0, extent=180, fill=TEAL, outline="")
    c.create_rectangle(55, 57, 74, 79, fill="#c68c6d", outline="")
    c.create_oval(42, 23, 86, 72, fill="#dca787", outline="")
    c.create_arc(39, 13, 89, 58, start=0, extent=180, fill=NAVY, outline="")
    c.create_line(52, 46, 56, 46, fill=INK, width=2)
    c.create_line(73, 46, 77, 46, fill=INK, width=2)
    c.create_arc(55, 48, 75, 62, start=200, extent=135, style="arc", outline=INK, width=2)
    c.create_line(48, 79, 63, 96, 81, 79, fill="white", width=3)
    return c


class Window:
    def __init__(self, root, settings):
        self.root, self.settings = root, settings
        self.events = queue.Queue(maxsize=256)
        self.loop = asyncio.new_event_loop()
        self.worker = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.worker.start()
        self.controller = self.active = None
        self.model_dialog = None
        self.running = self.listening = self.closing = False
        self.reopen_provisioning = False
        self.retrying = False
        self.retry_exhausted = False
        self.capture_quality = None
        # One listening session: the device stays open and finished questions are processed in
        # order by a single worker, so capture never waits for transcription or playback.
        self.playback_progress = None
        self.playback_stalled_at = None
        self.catalog_data = self.saved = self.loaded_case = None
        self.scenario_selected = False
        self.page = "setup"
        self.runtime = Runtime(settings, self.emit)
        self.speaker = self.runtime.speaker
        self.send_now = self.runtime.send_now
        root.title("Patient practice")
        root.geometry(f"1180x{max(680, min(860, root.winfo_screenheight() - 100))}")
        root.minsize(1080, 680)
        theme.apply_styles(root)
        header = tk.Frame(root, bg=NAVY, padx=26, pady=12)
        header.pack(fill="x")
        self.provision_button = ttk.Button(
            header, text="⚙", width=3, style="Icon.TButton", command=self.open_provisioning
        )
        self.provision_button.pack(side="right", padx=(14, 0))
        hint = None

        def hide_hint(_event=None):
            nonlocal hint
            if hint is not None:
                hint.destroy()
                hint = None

        def show_hint(_event=None):
            nonlocal hint
            hide_hint()
            hint = tk.Toplevel(root)
            hint.overrideredirect(True)
            ttk.Label(hint, text="Device connection settings", padding=8).pack()
            hint.geometry(
                f"+{self.provision_button.winfo_rootx() - 260}"
                f"+{self.provision_button.winfo_rooty() + self.provision_button.winfo_height() + 6}"
            )

        for event in ("<Enter>", "<FocusIn>"):
            self.provision_button.bind(event, show_hint)
        for event in ("<Leave>", "<FocusOut>", "<ButtonPress>", "<Destroy>"):
            self.provision_button.bind(event, hide_hint)
        tk.Label(header, text="✚  PATIENT PRACTICE", bg=NAVY, fg="white", font=theme.font(16, "bold")).pack(
            side="left"
        )
        self.practice_identity = tk.StringVar(value="Standalone practice · No trainee assigned")
        tk.Label(
            header, textvariable=self.practice_identity, bg=NAVY, fg="#9be1db", font=theme.font(10, "bold")
        ).pack(side="right")
        steps = ttk.Frame(root, padding=(26, 10, 26, 6))
        steps.pack(fill="x")
        self.step = tk.StringVar(value="01  Practice setup     →     02  Conversation")
        ttk.Label(steps, textvariable=self.step, font=theme.font(11, "bold")).pack(side="left")
        self.health = tk.StringVar(value="Connecting to PMS…")
        ttk.Label(steps, textvariable=self.health, foreground=MUTED).pack(side="right")
        from .session_queue import SessionQueue

        self.session_queue = SessionQueue(self, root)
        self.history_window = None
        self.history_turn = None
        # View state for the conversation page. Both default off on every launch: the stage
        # belongs to the patient, and the operator opens what they need from the ⋮ menu.
        self.show_text = tk.BooleanVar(value=False)
        self.show_typing = tk.BooleanVar(value=False)
        self.body = ttk.Frame(root, padding=(26, 6, 26, 12))
        self.body.pack(fill="both", expand=True)
        self.setup_frame, self.talk_frame = ttk.Frame(self.body), ttk.Frame(self.body)
        self.setup_frame.columnconfigure(0, weight=1)
        self.setup_frame.rowconfigure(0, weight=1)
        self.setup_canvas = tk.Canvas(self.setup_frame, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.setup_frame, orient="vertical", command=self.setup_canvas.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.setup_canvas.grid(row=0, column=0, sticky="nsew")
        self.setup_canvas.configure(yscrollcommand=scrollbar.set)
        self.setup_content = ttk.Frame(self.setup_canvas)
        content_id = self.setup_canvas.create_window((0, 0), window=self.setup_content, anchor="nw")
        self.setup_content.bind(
            "<Configure>", lambda e: self.setup_canvas.configure(scrollregion=self.setup_canvas.bbox("all"))
        )
        self.setup_canvas.bind(
            "<Configure>", lambda e: self.setup_canvas.itemconfigure(content_id, width=e.width)
        )
        self.build_setup()
        self.build_conversation()
        self.setup_frame.pack(fill="both", expand=True)
        self.state = tk.StringVar(value="Loading your practice setup…")
        footer = ttk.Frame(root, padding=(26, 6, 26, 8))
        footer.pack(side="bottom", fill="x")
        footer.columnconfigure(1, weight=1)
        # Two surfaces, because they answer different questions: whether the microphone is
        # actually hearing, and what is happening to the question already captured. One label
        # could only ever describe one of them, which is what made a working app look idle.
        self.mic_state = tk.StringVar(value="Microphone off")
        ttk.Label(footer, textvariable=self.mic_state, style="Pill.TLabel").grid(
            row=0, column=0, sticky="w", padx=(0, 12)
        )
        ttk.Label(footer, textvariable=self.state, style="Footer.TLabel", wraplength=760).grid(
            row=0, column=1, sticky="ew"
        )
        self.record_label = ttk.Label(footer, text="●  REC", style="Record.TLabel")
        self.record_label.grid(row=0, column=2, sticky="e", padx=(12, 0))
        self.record_label.grid_remove()
        self.timing = tk.StringVar(value="")
        ttk.Label(footer, textvariable=self.timing, style="FooterMuted.TLabel").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(4, 0)
        )
        self.history_message = tk.StringVar(value="")
        ttk.Label(footer, textvariable=self.history_message, style="FooterMuted.TLabel").grid(
            row=1, column=2, sticky="e", pady=(4, 0)
        )
        # Reserve the footer before allocating the expandable conversation area.
        self.body.pack_forget()
        self.body.pack(fill="both", expand=True)
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(30, self.drain)
        self.submit(self.initialize(), "initialized")

    def open_history(self):
        from .history_view import HistoryView

        if not self.controller:
            return
        if self.history_window and self.history_window.window.winfo_exists():
            self.history_window.window.lift()
            self.history_window.refresh()
        else:
            self.history_window = HistoryView(self.root, self.loop, self.controller)

    def retry_sync(self):
        sync = getattr(self.controller, "sync", None)
        if sync:
            sync.retry()

    def card(self, parent):
        return ttk.Frame(parent, style="Card.TFrame", padding=22)

    def label(self, parent, text, style="Card.TLabel", **kwargs):
        return ttk.Label(parent, text=text, style=style, **kwargs)

    def build_setup(self):
        input_font = ("Segoe UI", 11)
        self.setup_content.columnconfigure(1, weight=1)
        self.setup_content.rowconfigure(0, weight=1)
        person = self.card(self.setup_content)
        person.configure(padding=(18, 14))
        person.grid(row=0, column=0, sticky="nsew", padx=(0, 18))
        portrait(person).pack(anchor="w")
        self.patient_name = tk.StringVar(value="Patient")
        ttk.Label(person, textvariable=self.patient_name, style="Title.TLabel").pack(anchor="w", pady=(6, 6))
        self.patient_info = tk.StringVar(value="Loading patient identity…")
        ttk.Label(
            person, textvariable=self.patient_info, style="Muted.TLabel", justify="left", wraplength=228
        ).pack(anchor="w", pady=(0, 12))
        ttk.Separator(person).pack(fill="x", pady=6)
        self.label(person, "Patient details follow the case.", font=("Segoe UI", 10, "bold")).pack(
            anchor="w", pady=(12, 8)
        )
        self.label(
            person,
            "Choose the interview you want to practise. The patient history and answers follow the selected case.",
            "Muted.TLabel",
            wraplength=228,
        ).pack(anchor="w")
        self.label(person, "HOW IT WORKS", "Muted.TLabel", font=("Segoe UI", 9, "bold")).pack(
            anchor="w", pady=(16, 8)
        )
        self.label(
            person,
            "1   Choose a case\n2   Check initial observations\n3   Save and start the interview",
            wraplength=228,
        ).pack(anchor="w")
        self.label(person, REHEARSAL_NOTICE, "Muted.TLabel", wraplength=228).pack(anchor="w", pady=(16, 0))
        main = self.card(self.setup_content)
        main.configure(padding=(22, 12))
        main.grid(row=0, column=1, sticky="nsew")
        main.columnconfigure(0, weight=3)
        main.columnconfigure(1, weight=1)
        self.label(main, "Prepare your patient", "Title.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w"
        )
        self.setup_note = tk.StringVar(value="Your choices are saved in PMS for this staff account.")
        ttk.Label(main, textvariable=self.setup_note, style="Muted.TLabel", wraplength=670).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(5, 12)
        )
        self.category, self.patient_profile, self.case_choice = tk.StringVar(), tk.StringVar(), tk.StringVar()
        self.language = tk.StringVar(
            value=next(label for label, code in LANGUAGES.items() if code in self.settings.language_choices)
        )
        self.label(main, "Practice case", font=input_font).grid(row=2, column=0, sticky="w")
        self.case_box = ttk.Combobox(
            main, textvariable=self.case_choice, state="disabled", width=30, font=input_font
        )
        self.case_box.grid(row=3, column=0, sticky="ew", pady=(6, 10))
        self.case_box.bind("<<ComboboxSelected>>", lambda e: self.load_case())
        self.label(main, "Interview language", font=input_font).grid(
            row=2, column=1, sticky="w", padx=(14, 0)
        )
        self.lang_box = ttk.Combobox(
            main,
            textvariable=self.language,
            state="readonly",
            font=input_font,
            width=16,
            values=[label for label, code in LANGUAGES.items() if code in self.settings.language_choices],
        )
        self.lang_box.grid(row=3, column=1, sticky="ew", padx=(14, 0), pady=(6, 10))
        case_info = ttk.Frame(main, style="CaseInfo.TFrame", padding=12)
        case_info.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(2, 10))
        case_info.columnconfigure(0, weight=1, uniform="case_details")
        case_info.columnconfigure(2, weight=1, uniform="case_details")
        self.label(
            case_info, "CASE INFORMATION", "CaseInfoCaption.TLabel", font=("Segoe UI", 9, "bold")
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
        self.label(case_info, "Clinical specialty", "CaseInfoCaption.TLabel").grid(
            row=1, column=0, sticky="w"
        )
        self.category_box = ttk.Combobox(
            case_info, textvariable=self.category, state="disabled", font=input_font
        )
        self.category_box.grid(row=2, column=0, sticky="ew", pady=(4, 0))
        self.category_box.bind("<<ComboboxSelected>>", lambda e: self.category_changed())
        self.category_display = ttk.Label(
            case_info, textvariable=self.category, style="CaseInfo.TLabel", wraplength=280, justify="left"
        )
        self.category_display.grid(row=2, column=0, sticky="nw", pady=(4, 0))
        self.category_box.grid_remove()
        ttk.Separator(case_info, orient="vertical").grid(row=1, column=1, rowspan=2, sticky="ns", padx=18)
        self.label(case_info, "Patient profile", "CaseInfoCaption.TLabel").grid(row=1, column=2, sticky="w")
        self.patient_box = ttk.Combobox(
            case_info, textvariable=self.patient_profile, state="disabled", font=input_font
        )
        self.patient_box.grid(row=2, column=2, sticky="ew", pady=(4, 0))
        self.patient_box.bind("<<ComboboxSelected>>", lambda e: self.patient_changed())
        self.patient_display = ttk.Label(
            case_info,
            textvariable=self.patient_profile,
            style="CaseInfo.TLabel",
            wraplength=280,
            justify="left",
        )
        self.patient_display.grid(row=2, column=2, sticky="nw", pady=(4, 0))
        self.patient_box.grid_remove()
        # The popup list has its own font; scope it to the setup dropdowns.
        for box in (self.category_box, self.patient_box, self.lang_box, self.case_box):
            self.root.option_add(f"*{str(box).lstrip('.')}*Listbox.font", input_font)
        self.case_summary = tk.StringVar(value="Choose a practice case to see the patient story.")
        ttk.Label(
            main, textvariable=self.case_summary, style="Muted.TLabel", wraplength=670, justify="left"
        ).grid(row=8, column=0, columnspan=2, sticky="ew", pady=(2, 10))
        ttk.Separator(main).grid(row=9, column=0, columnspan=2, sticky="ew")
        self.label(main, "Initial observations", font=("Segoe UI", 12, "bold")).grid(
            row=10, column=0, columnspan=2, sticky="w", pady=(12, 4)
        )
        self.label(
            main,
            "Adjust measured values if needed. The selected case supplies the history.",
            "Muted.TLabel",
            wraplength=670,
        ).grid(row=11, column=0, columnspan=2, sticky="w", pady=(0, 10))
        grid = ttk.Frame(main, style="Card.TFrame")
        grid.grid(row=12, column=0, columnspan=2, sticky="ew")
        self.vitals, self.vital_entries = {}, []
        for i, (key, label, unit) in enumerate(VITALS):
            grid.columnconfigure(i % 4, weight=1)
            field = ttk.Frame(grid, style="Card.TFrame", padding=(0, 0, 12, 8))
            field.grid(row=i // 4, column=i % 4, sticky="ew")
            self.label(field, label, "Muted.TLabel", font=input_font).pack(anchor="w")
            reading = ttk.Frame(field, style="Card.TFrame")
            reading.pack(fill="x", pady=(4, 2))
            self.vitals[key] = tk.StringVar()
            entry = ttk.Entry(reading, textvariable=self.vitals[key], width=7, font=input_font)
            entry.pack(side="left", fill="x", expand=True)
            self.vital_entries.append(entry)
            self.label(reading, unit, "Muted.TLabel", font=("Segoe UI", 9)).pack(side="left", padx=(5, 0))
        actions = ttk.Frame(self.setup_frame, style="Card.TFrame", padding=(18, 10))
        actions.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        self.reload_button = ttk.Button(actions, text="↻  Reload from PMS", command=self.reload)
        self.reload_button.pack(side="left")
        self.save_button = ttk.Button(
            actions,
            text="Save & continue  →",
            style="Primary.TButton",
            command=self.save_setup,
            state="disabled",
        )
        self.save_button.pack(side="right")

    def build_conversation(self):
        """Stage-first layout: the patient owns the page; everything else is a dock, a
        drawer opened from the ⋮ menu, or the menu itself."""
        panel = ttk.Frame(self.talk_frame)
        panel.pack(fill="both", expand=True)
        self.conversation_panel = panel
        panel.columnconfigure(0, weight=1)
        panel.columnconfigure(1, weight=0, minsize=0)
        panel.rowconfigure(1, weight=1)
        # Row 0: a warning banner across the page, shown only when a turn fails.
        self.turn_warning = tk.StringVar()
        self.warning_label = tk.Label(
            panel,
            textvariable=self.turn_warning,
            bg=theme.AMBER_BG,
            fg=theme.AMBER_INK,
            font=theme.font(9),
            justify="left",
            anchor="w",
            wraplength=900,
            padx=10,
            pady=8,
            highlightthickness=1,
            highlightbackground=theme.AMBER_LINE,
        )
        # Row 1, column 0: the stage.
        stage = ttk.Frame(panel, style="Card.TFrame", padding=theme.SPACE_SM)
        stage.grid(row=1, column=0, sticky="nsew")
        self.patient_panel = stage
        stage.columnconfigure(0, weight=1)
        stage.rowconfigure(1, weight=1)
        head = ttk.Frame(stage, style="Card.TFrame")
        head.grid(row=0, column=0, sticky="ew", pady=(0, theme.SPACE_XS))
        head.columnconfigure(0, weight=1)
        self.stage_head = head
        self.active_case = tk.StringVar(value="Patient")
        case_label = ttk.Label(head, textvariable=self.active_case, style="StageTitle.TLabel", wraplength=600)
        case_label.grid(row=0, column=0, sticky="w", padx=(theme.SPACE_XS, 0))
        self.menu_button = ttk.Button(head, text="⋮", style="Icon.TButton", width=3)
        self.menu_button.grid(row=0, column=1, sticky="ne")
        self.manikin = Manikin(stage)
        self.manikin.grid(row=1, column=0, sticky="nsew")
        notice = ttk.Label(stage, text=REHEARSAL_NOTICE, style="Muted.TLabel", font=theme.font(9))
        notice.grid(row=2, column=0, pady=(theme.SPACE_XS, 0))
        # Row 1, column 1: the drawer, hidden until the operator asks for it.
        drawer = ttk.Frame(panel, style="Card.TFrame", padding=theme.SPACE_MD, width=theme.DRAWER_WIDTH)
        self.interview_panel = drawer
        drawer.columnconfigure(0, weight=1)
        drawer.rowconfigure(1, weight=1)
        drawer.rowconfigure(3, weight=3)
        self.label(drawer, "YOUR QUESTION", "Caption.TLabel").grid(row=0, column=0, sticky="w")
        question_panel = ttk.Frame(drawer, style="Card.TFrame")
        question_panel.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
        question_panel.columnconfigure(0, weight=1)
        question_panel.rowconfigure(0, weight=1)
        self.question = tk.Text(
            question_panel,
            height=2,
            width=1,
            wrap="word",
            font=theme.font(12, family=theme.TEXT_FONT),
            relief="flat",
            bg=theme.SURFACE_ALT,
            fg=INK,
            padx=10,
            pady=8,
            state="disabled",
        )
        self.question.grid(row=0, column=0, sticky="nsew")
        question_scroll = ttk.Scrollbar(question_panel, orient="vertical", command=self.question.yview)
        question_scroll.grid(row=0, column=1, sticky="ns")
        self.question.configure(yscrollcommand=question_scroll.set)
        self.label(drawer, "PATIENT RESPONSE", "Caption.TLabel").grid(
            row=2, column=0, sticky="w", pady=(theme.SPACE_MD, 0)
        )
        answer_panel = ttk.Frame(drawer, style="Card.TFrame")
        answer_panel.grid(row=3, column=0, sticky="nsew", pady=(6, 0))
        answer_panel.columnconfigure(0, weight=1)
        answer_panel.rowconfigure(0, weight=1)
        self.answer = tk.Text(
            answer_panel,
            height=3,
            width=1,
            wrap="word",
            font=theme.font(13, family=theme.TEXT_FONT),
            relief="flat",
            bg=theme.SURFACE_OK,
            fg=INK,
            padx=12,
            pady=8,
            state="disabled",
        )
        self.answer.grid(row=0, column=0, sticky="nsew")
        answer_scroll = ttk.Scrollbar(answer_panel, orient="vertical", command=self.answer.yview)
        answer_scroll.grid(row=0, column=1, sticky="ns")
        self.answer.configure(yscrollcommand=answer_scroll.set)
        response_actions = ttk.Frame(drawer, style="Card.TFrame")
        response_actions.grid(row=4, column=0, sticky="ew", pady=(theme.SPACE_SM, 0))
        response_actions.columnconfigure((0, 1, 2), weight=1, uniform="response")
        ttk.Button(
            response_actions, text="New conversation", style="Compact.TButton", command=self.reset
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(
            response_actions, text="Check last request", style="Compact.TButton", command=self.check_request
        ).grid(row=0, column=1, sticky="ew", padx=(0, 6))
        self.back_button = ttk.Button(
            response_actions, text="←  Practice setup", style="Compact.TButton", command=self.back
        )
        self.back_button.grid(row=0, column=2, sticky="ew")
        ttk.Separator(drawer).grid(row=5, column=0, sticky="ew", pady=(theme.SPACE_MD, theme.SPACE_SM))
        # Audio settings: the same variables the ⋮ menu binds to, kept here for direct editing.
        self.label(drawer, "AUDIO", "Caption.TLabel").grid(row=6, column=0, sticky="w")
        audio = ttk.Frame(drawer, style="Card.TFrame")
        audio.grid(row=7, column=0, sticky="ew", pady=(6, 0))
        audio.columnconfigure(1, weight=1)
        self.microphones = {"System default": None}
        self.microphone_names = {}
        try:
            for i, name in microphones():
                self.microphones[f"{i}: {name}"] = i
                self.microphone_names[f"{i}: {name}"] = name
        except Exception:
            pass
        self.mic = tk.StringVar(
            value=next(
                (
                    label
                    for label, name in self.microphone_names.items()
                    if name == self.settings.microphone_name
                ),
                next(
                    (label for label, id in self.microphones.items() if id == self.settings.microphone),
                    "System default",
                ),
            )
        )
        self.label(audio, "Microphone", "Muted.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.mic_box = ttk.Combobox(
            audio, textvariable=self.mic, values=list(self.microphones), state="readonly", width=16
        )
        self.mic_box.grid(row=0, column=1, sticky="ew")
        self.mic_box.bind("<<ComboboxSelected>>", lambda event: self.check_microphone())
        # Selecting a device checks it, but the default is never selected, so it needs its own way in.
        self.mic_check_button = ttk.Button(
            audio, text="Check", style="Compact.TButton", command=self.check_microphone
        )
        self.mic_check_button.grid(row=0, column=2, sticky="e", padx=(6, 0))
        self.voices = {DEFAULT_VOICE_CHOICE: None} | {
            entry["label"]: entry["key"] for entry in self.speaker.catalogue()
        }
        self.voice = tk.StringVar(value=self.voice_label_for(self.settings))
        self.label(audio, "Voice", "Muted.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(6, 0))
        self.voice_box = ttk.Combobox(
            audio, textvariable=self.voice, values=list(self.voices), state="readonly", width=16
        )
        self.voice_box.grid(row=1, column=1, sticky="ew", pady=(6, 0))
        self.voice_box.bind("<<ComboboxSelected>>", lambda event: self.apply_voice())
        self.preview_button = ttk.Button(
            audio, text="Hear", style="Compact.TButton", command=self.preview_voice
        )
        self.preview_button.grid(row=1, column=2, sticky="e", padx=(6, 0), pady=(6, 0))
        options = ttk.Frame(audio, style="Card.TFrame")
        options.grid(row=2, column=0, columnspan=3, sticky="w", pady=(8, 0))
        self.streaming = tk.BooleanVar(value=self.settings.streaming)
        self.stream_box = ttk.Checkbutton(options, text="Stream response", variable=self.streaming)
        self.stream_box.pack(side="left", padx=(0, 12))
        self.speaker_output = tk.BooleanVar(value=self.settings.speaker_output)
        self.speaker_box = ttk.Checkbutton(
            options, text="Speaker out", variable=self.speaker_output, command=self.apply_speaker_output
        )
        self.speaker_box.pack(side="left")
        ttk.Separator(drawer).grid(row=8, column=0, sticky="ew", pady=(theme.SPACE_MD, theme.SPACE_SM))
        self.label(drawer, "CAMERA", "Caption.TLabel").grid(row=9, column=0, sticky="w")
        # Keep the preview below the title/menu, even when a short window clips it.
        self.camera_view = CameraView(
            drawer, self.settings, preview_host=self.manikin, recording=self.runtime.camera
        )
        self.camera_view.grid(row=10, column=0, sticky="ew", pady=(6, 0))
        # Row 2: the action dock, always visible.
        dock = ttk.Frame(panel, style="Dock.TFrame", padding=(theme.SPACE_MD, theme.SPACE_SM))
        dock.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(theme.SPACE_SM, 0))
        self.conversation_header = dock
        dock.columnconfigure(3, weight=1)
        self.start_button = ttk.Button(
            dock, text="●  Start microphone", style="Primary.TButton", command=self.toggle
        )
        self.start_button.grid(row=0, column=0, sticky="w")
        ttk.Button(dock, text="Send audio now", style="Compact.TButton", command=self.send_now.set).grid(
            row=0, column=1, sticky="w", padx=(theme.SPACE_SM, 0)
        )
        ttk.Button(dock, text="Cancel", style="Compact.TButton", command=self.pause).grid(
            row=0, column=2, sticky="w", padx=(6, 0)
        )
        typed = ttk.Frame(dock, style="Dock.TFrame")
        typed.grid(row=0, column=3, sticky="ew", padx=(theme.SPACE_LG, 0))
        typed.columnconfigure(0, weight=1)
        self.typed_frame = typed
        self.typed_question = tk.StringVar()
        self.question_entry = ttk.Entry(typed, textvariable=self.typed_question, width=12)
        self.question_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.question_entry.bind("<Return>", lambda e: self.ask_text())
        self.ask_button = ttk.Button(
            typed, text="Ask question  →", style="Compact.TButton", command=self.ask_text
        )
        self.ask_button.grid(row=0, column=1, sticky="ns")
        self.previous_button = ttk.Button(dock, text="←  Previous", command=self.back)
        self.previous_button.grid(row=0, column=4, sticky="e", padx=(theme.SPACE_LG, 0))
        self.complete_button = ttk.Button(dock, text="✓  Complete & Close", command=self.confirm_complete)
        self.complete_button.grid(row=0, column=5, sticky="e", padx=(theme.SPACE_SM, 0))
        # The retry overlay centres over the patient, below the stage title row.
        self.retry_notice = RetryNotice(stage, self.pause, head)
        self.menu = OverflowMenu(self, self.menu_button)
        self.menu_button.configure(command=self.menu.open)

        def fit_stage_text(event):
            case_label.configure(wraplength=max(200, event.width - 80))

        stage.bind("<Configure>", fit_stage_text)
        self.apply_layout()

    def apply_layout(self):
        """The one place that shows or hides the drawer and the typed entry."""
        panel = self.conversation_panel
        if self.show_text.get():
            panel.columnconfigure(1, minsize=theme.DRAWER_WIDTH)
            self.interview_panel.grid(row=1, column=1, sticky="nsew", padx=(theme.SPACE_MD, 0))
        else:
            self.interview_panel.grid_remove()
            panel.columnconfigure(1, minsize=0)
        if self.show_typing.get():
            self.typed_frame.grid()
            self.question_entry.focus_set()
        else:
            self.typed_frame.grid_remove()

    def show_warning(self, note):
        self.turn_warning.set(note)
        self.warning_label.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, theme.SPACE_SM))

    async def initialize(self):
        if self.controller is None:
            self.controller = await self.runtime.initialize()
            self.camera_view.sync_provider = lambda: self.controller.sync
        self.emit("catalog", await self.runtime.prepare())
        self.emit("ready", "PMS connected · microphone off")

    def open_models(self):
        if self.session_queue.assigned():
            self.state.set("Complete the assigned session before changing models.")
            return
        if self.running or self.listening or not self.controller:
            self.state.set("Finish the current operation before reloading models.")
            return
        if self.model_dialog:
            self.model_dialog.window.lift()
            return
        from .model_dialog import ModelDialog

        self.model_dialog = ModelDialog(self)

    def reload(self):
        if self.session_queue.assigned():
            self.state.set("Complete the assigned session before reloading setup.")
            return
        if not self.running:
            self.clear_case()
            self.submit(self.initialize(), "initialized")

    def apply_catalog(self, catalog, saved):
        self.catalog_data, self.saved = catalog, saved
        if "scenarios" in catalog:
            self.apply_scenarios(catalog, saved)
            return
        self.scenario_selected = bool(saved and saved.get("scenario_id"))
        self.categories = {c["name"]: c for c in catalog["categories"]}
        self.category_box.configure(values=list(self.categories))
        self.clear_case()
        self.patients = {}
        self.cases = {}
        self.category.set("")
        self.patient_profile.set("")
        self.patient_box.configure(values=[])
        self.case_choice.set("")
        self.case_box.configure(values=[])
        if self.scenario_selected:
            document = saved.get("document") or {}
            self.loaded_case = {
                "id": saved["scenario_id"],
                "revision": saved["template_revision"],
                "category_id": None,
                "patient_identity_id": None,
                "document": document,
            }
            self.case_choice.set(document.get("title") or "Published scenario")
            self.case_box.configure(values=[self.case_choice.get()], state="disabled")
            self.category_box.configure(state="disabled")
            self.patient_box.configure(state="disabled")
            self.language.set(
                next(
                    (
                        label
                        for label, code in LANGUAGES.items()
                        if code == saved["language"] and code in self.settings.language_choices
                    ),
                    next(
                        label for label, code in LANGUAGES.items() if code in self.settings.language_choices
                    ),
                )
            )
            self.render_case(self.loaded_case)
            # Binding/resetting a conversation belongs to the worker when the user saves.
            # Refresh only restores the form; Tk's thread has no asyncio event loop.
            self.setup_note.set("Published scenario restored from Practice. Review and save to continue.")
            self.state.set("Published scenario ready for practice.")
            return
        if not catalog["categories"] or not catalog["patients"] or not catalog["cases"]:
            note = "Ask a tenant clinical author to publish a scenario, then reload this app."
            if saved and saved.get("legacy"):
                note += (
                    " Your historical global-case setup needs an active tenant case before another interview."
                )
            self.setup_note.set(note)
            self.state.set("No published scenarios available. Reload after one is published.")
            return
        selected = next(
            (
                c
                for c in catalog["cases"]
                if saved and not saved.get("legacy") and c["id"] == saved["template_id"]
            ),
            None,
        )
        current = bool(
            selected and selected["revision"] == saved.get("template_revision", selected["revision"])
        )
        available_category_ids = {c["category_id"] for c in catalog["cases"]}
        category = next(
            (c for c in catalog["categories"] if selected and c["id"] == selected["category_id"]),
            next(c for c in catalog["categories"] if c["id"] in available_category_ids),
        )
        self.category.set(category["name"])
        self.category_changed(load=False)
        if selected:
            self.patient_profile.set(
                next(
                    label
                    for label, row in self.patients.items()
                    if row["id"] == selected["patient_identity_id"]
                )
            )
            self.patient_changed(load=False)
        if current:
            self.case_choice.set(
                next(label for label, row in self.cases.items() if row["id"] == selected["id"])
            )
            self.render_case({**selected, "document": saved["document"]})
            self.language.set(
                next(
                    (
                        label
                        for label, code in LANGUAGES.items()
                        if code == saved["language"] and code in self.settings.language_choices
                    ),
                    next(
                        label for label, code in LANGUAGES.items() if code in self.settings.language_choices
                    ),
                )
            )
            self.setup_note.set("Previous tenant setup restored. Review and save to continue.")
            self.state.set("Previous tenant setup restored. Review and save to continue.")
        else:
            if saved and saved.get("legacy"):
                self.setup_note.set(
                    "This historical setup uses a global case. Choose an active tenant case and save "
                    "before starting a new interview."
                )
            elif saved:
                self.setup_note.set(
                    "The saved case was updated or is no longer active. Choose a current tenant case and save."
                )
            else:
                self.setup_note.set("Choose one of this tenant's active cases, then save your setup.")
            self.state.set("Choose a case, check observations, then save to continue.")

    def apply_scenarios(self, catalog, saved):
        self.scenario_selected = True
        self.clear_case()
        self.category_box.configure(state="disabled")
        self.patient_box.configure(state="disabled")
        self.category.set("No case selected")
        self.patient_profile.set("No case selected")
        self.cases = {
            f"{i + 1}. {row['title']} (v{row['version']})": row
            for i, row in enumerate(catalog["scenarios"])
            if set(row["languages"]) & set(self.settings.language_choices) & set(LANGUAGES.values())
        }
        self.case_box.configure(values=list(self.cases), state="readonly")
        default = catalog.get("default") or {}
        preferred = [saved.get("scenario_id") if saved else None, default.get("scenario_id")]
        chosen = next(
            (label for identity in preferred for label, row in self.cases.items() if row["id"] == identity),
            next(iter(self.cases), ""),
        )
        self.case_choice.set(chosen)
        language = saved.get("language") if saved and saved.get("scenario_id") else default.get("language")
        if language in LANGUAGES.values():
            self.language.set(next(label for label, code in LANGUAGES.items() if code == language))
        if not chosen:
            self.setup_note.set(
                "No published scenario is available in a supported language. Ask a tenant clinical author to publish one, then reload."
            )
            self.state.set("No published scenarios available.")
            return
        self.load_published_case()

    def load_published_case(self):
        row = self.cases.get(self.case_choice.get())
        if not row:
            return
        self.clear_case()
        choices = [
            label
            for label, code in LANGUAGES.items()
            if code in row["languages"] and code in self.settings.language_choices
        ]
        self.lang_box.configure(values=choices)
        if self.language.get() not in choices:
            self.language.set(choices[0])
        self.category.set(row.get("specialty") or "Not specified")
        self.patient_profile.set("Available after saving this case")
        saved = self.saved if self.saved and self.saved.get("scenario_id") == row["id"] else None
        self.loaded_case = {
            "id": row["id"],
            "revision": row["version"],
            "category_id": None,
            "patient_identity_id": None,
            "document": saved["document"] if saved else {"vitals": row.get("vitals") or {}},
        }
        if saved:
            self.render_case(self.loaded_case)
        else:
            self.patient_name.set("Published scenario")
            self.patient_info.set("Patient details appear after you save this selection.")
            self.case_summary.set(row["title"])
            for key, value in self.vitals.items():
                reading = (row.get("vitals") or {}).get(key)
                value.set(f"{reading:g}" if reading is not None else "")
        self.setup_note.set(
            "Choose a published scenario, language and initial observations, then save to start."
        )
        self.state.set("Published scenario ready for desktop practice.")
        self.save_button.configure(state="normal")

    def category_changed(self, load=True):
        if not self.catalog_data:
            return
        category = self.categories.get(self.category.get())
        patient_ids = {
            c["patient_identity_id"]
            for c in self.catalog_data["cases"]
            if category and c["category_id"] == category["id"]
        }
        profiles = [p for p in self.catalog_data["patients"] if p["id"] in patient_ids]
        duplicate_names = len({p["name"].casefold() for p in profiles}) != len(profiles)
        self.patients = {
            (f"{p['name']} ({p['code']})" if duplicate_names else p["name"]): p for p in profiles
        }
        self.patient_box.configure(values=list(self.patients))
        self.patient_profile.set(next(iter(self.patients), ""))
        self.patient_changed(load=load)

    def patient_changed(self, load=True):
        if not self.catalog_data:
            return
        category = self.categories.get(self.category.get())
        patient = self.patients.get(self.patient_profile.get())
        rows = [
            c
            for c in self.catalog_data["cases"]
            if category
            and patient
            and c["category_id"] == category["id"]
            and c["patient_identity_id"] == patient["id"]
        ]
        # Titles are display text, not identifiers; identical titles must remain selectable.
        duplicate_titles = len({c["title"] for c in rows}) != len(rows)
        self.cases = {
            (f"{index + 1}. {c['title']}" if duplicate_titles else c["title"]): c
            for index, c in enumerate(rows)
        }
        self.case_box.configure(values=list(self.cases))
        self.case_choice.set(next(iter(self.cases), ""))
        self.clear_case()
        if load:
            self.load_case()

    def load_case(self):
        if self.running:
            return
        if self.scenario_selected and "scenarios" in self.catalog_data:
            self.load_published_case()
            return
        case = self.cases.get(self.case_choice.get())
        if not case:
            return
        self.clear_case()
        self.state.set("Loading case from PMS…")

        async def fetch():
            self.emit("case", await self.controller.pms.case(case["id"]))

        self.submit(fetch(), "case_loaded")

    def clear_case(self):
        self.loaded_case = None
        self.patient_name.set("Patient")
        self.patient_info.set("Choose a case to see the patient details.")
        self.case_summary.set("Choose a practice case to see the patient story.")
        for value in self.vitals.values():
            value.set("")
        self.save_button.configure(state="disabled")

    def render_case(self, case):
        self.loaded_case = case
        document = case["document"]
        patient = dict(document["patient"])
        profile = next(
            (p for p in self.catalog_data["patients"] if p["id"] == case["patient_identity_id"]),
            None,
        )
        if profile:
            for key in ("name", "age_years", "sex", "height_cm", "weight_kg"):
                if key in profile:
                    patient[key] = profile[key]
            if "occupations" in profile:
                patient["occupation"] = profile["occupations"]
        language = LANGUAGES.get(self.language.get(), self.settings.language)
        self.patient_name.set(patient["name"])
        if self.scenario_selected:
            self.patient_profile.set(patient["name"])
        age = patient.get("age_years")
        measurements = [
            f"{float(patient[key]):g} {unit}"
            for key, unit in (("height_cm", "cm"), ("weight_kg", "kg"))
            if patient.get(key) is not None
        ]
        self.patient_info.set(
            (f"{age} years" if age is not None else "Age not specified")
            + f"  |  {(patient.get('sex') or 'unspecified').title()}\n"
            + (patient.get("occupation") or {}).get(language, "")
            + ("\n\n" + "  |  ".join(measurements) if measurements else "")
        )
        presentation = document.get("presentation") or {}
        preferred = (
            LANGUAGES.get(self.language.get(), self.settings.language),
            document.get("source_language"),
            "en",
        )

        def preview_text(field):
            translated = presentation.get(field) or {}
            return next(
                (translated[code] for code in preferred if code in translated),
                next(iter(translated.values()), ""),
            )

        self.case_summary.set(
            "\n".join(text for text in (preview_text("chief_complaint"), preview_text("onset")) if text)
        )
        for key, value in self.vitals.items():
            reading = (document.get("vitals") or {}).get(key)
            value.set(f"{reading:g}" if reading is not None else "")

    def save_setup(self):
        if self.session_queue.next and self.session_queue.standalone_active():
            if not self.running and self.saved:
                self.emit("saved", self.saved)
            return
        if self.session_queue.assigned():
            if self.session_queue.active and not self.session_queue.finishing and not self.running:
                self.emit("saved", self.saved)
            return
        if self.session_queue.blocks_setup():
            if self.session_queue.next:
                self.session_queue.begin()
            else:
                self.state.set("An assigned session is already running. Wait for it to finish.")
            return
        if self.running or not self.loaded_case:
            return
        try:
            values = Vitals.model_validate(
                {key: float(value.get()) for key, value in self.vitals.items()}
            ).model_dump(mode="json")
            if any(value is None for value in values.values()):
                raise ValueError()
            if values["systolic_mmhg"] < values["diastolic_mmhg"]:
                raise ValueError()
        except ValueError:
            self.state.set(
                "Enter a finite number for all eight observations. Temperature and oxygen: 0–100; pain: 0–10; rates and pressures: 0–1000. Systolic pressure must be at least diastolic pressure."
            )
            return
        payload = {
            "expected_revision": self.saved["revision"] if self.saved else 0,
            "language": LANGUAGES[self.language.get()],
            "vitals": values,
        }
        if self.scenario_selected:
            payload["scenario_id"] = self.loaded_case["id"]
        else:
            payload.update(
                {
                    "template_id": self.loaded_case["id"],
                    "template_revision": self.loaded_case["revision"],
                    "category_id": self.loaded_case["category_id"],
                    "patient_identity_id": self.loaded_case["patient_identity_id"],
                }
            )
        self.state.set("Saving practice setup in PMS…")

        async def save():
            selected = await self.runtime.save_selection(payload, scenario=self.scenario_selected)
            self.emit("saved", selected)

        self.submit(save(), "setup_saved")

    def lock_options(self, locked):
        assigned = self.session_queue.assigned() or (
            self.session_queue.next is not None and self.page == "setup"
        )
        for box, display in (
            (self.category_box, self.category_display),
            (self.patient_box, self.patient_display),
        ):
            if self.scenario_selected or self.catalog_data is None:
                box.grid_remove()
                display.grid()
            else:
                display.grid_remove()
                box.grid()
        for box in (self.category_box, self.patient_box, self.case_box, self.lang_box, self.mic_box):
            box.configure(
                state="disabled"
                if locked
                or (assigned and box in (self.case_box, self.lang_box))
                or (self.scenario_selected and box in (self.category_box, self.patient_box))
                else "readonly"
            )
        for entry in self.vital_entries:
            entry.configure(state="disabled" if locked or assigned else "normal")
        for button in (
            self.reload_button,
            self.back_button,
            self.previous_button,
            self.ask_button,
            self.mic_check_button,
        ):
            button.configure(state="disabled" if locked else "normal")
        self.stream_box.configure(state="disabled" if locked else "normal")
        self.voice_box.configure(state="disabled" if locked else "readonly")
        self.preview_button.configure(state="disabled" if locked else "normal")
        self.question_entry.configure(state="disabled" if locked else "normal")
        self.save_button.configure(state="normal" if not locked and self.loaded_case else "disabled")

    def apply_speaker_output(self):
        """Toggling off stops the current sentence instead of waiting for it to finish."""
        self.settings.speaker_output = self.speaker.enabled = self.speaker_output.get()
        if not self.speaker.enabled:
            self.speaker.stop()
            self.manikin.stop_speech_gesture()

    def voice_label_for(self, settings):
        key = settings.voice
        return next((label for label, value in self.voices.items() if value == key), DEFAULT_VOICE_CHOICE)

    def apply_voice(self):
        """A chosen voice replaces the default for its own language only."""
        key = self.voices.get(self.voice.get())
        chosen = self.speaker.prefer(key)
        self.settings.voice = key
        self.speaker.stop()
        self.manikin.stop_speech_gesture()
        if chosen:
            language = get_pack(chosen["language"]).name
            self.state.set(f"{language} voice: {chosen['label']}. Press Hear to listen to it.")
        else:
            self.state.set("Voice now follows the patient's recorded sex and the answer language.")

    def preview_voice(self):
        """Speak one fixed sample so a voice can be chosen by ear, never a patient answer."""
        if self.running or self.listening:
            self.state.set("Pause the microphone before previewing a voice.")
            return
        if not self.speaker.enabled:
            self.state.set("Select Speaker out to hear a voice.")
            return
        key = self.voices.get(self.voice.get())
        chosen = next((entry for entry in self.speaker.catalogue() if entry["key"] == key), None)
        language = chosen["language"] if chosen else self.settings.language
        gender = patient_gender(self.saved) if self.saved else "male"
        self.speaker.stop()
        self.manikin.stop_speech_gesture()
        if self.speaker.speak(VOICE_PREVIEW[language], language, gender):
            self.state.set("Playing a sample of " + (chosen["label"] if chosen else "the default voice"))

    def capture_allowed(self):
        return self.runtime.capture_allowed()

    def begin(self):
        if self.session_queue.finishing or self.session_queue.starting:
            return
        """Open the microphone once for the whole interview and process questions in order."""
        if (
            self.closing
            or not self.listening
            or self.running
            or self.retrying
            or not self.saved
            or self.page != "talk"
        ):
            return
        self.manikin.stop_animation()
        self.speaker.stop()
        self.settings.microphone = self.microphones[self.mic.get()]
        # Remember the name too: an index alone can open a different device after a reboot.
        self.settings.microphone_name = self.microphone_names.get(self.mic.get())
        self.settings.streaming = self.streaming.get()
        self.send_now.clear()
        self.playback_progress = self.playback_stalled_at = None
        self.submit(self.interview(), completion="session_ended")
        # A session holds the operation lock for its whole life, but typing a question is not a
        # competing operation: it is the same worker, in the same order as the spoken ones.
        self.question_entry.configure(state="normal")
        self.ask_button.configure(state="normal")

    async def interview(self):
        await self.runtime.listen()

    def check_microphone(self):
        """Listen to the chosen device for a moment and report the room, so a muted, missing or
        reordered microphone is found here rather than part-way through a session."""
        if self.running or self.listening or self.retrying:
            return
        self.settings.microphone = self.microphones[self.mic.get()]
        self.settings.microphone_name = self.microphone_names.get(self.mic.get())

        async def probe():
            quality = await probe_microphone(self.settings)
            report = quality.snapshot()
            concerns = quality.concerns()
            self.emit(
                "mic_check",
                "Microphone: " + "; ".join(concerns)
                if concerns
                else f"Microphone ready · room noise {report['noise_floor_dbfs']:.0f} dBFS"
                f" · {report['device_name'] or 'system default'}",
            )

        self.submit(probe(), completion="checked")

    def toggle(self):
        if self.listening or self.retrying:
            self.pause()
        elif self.saved and self.page == "talk" and not self.running:
            self.listening = True
            self.start_button.configure(text="Ⅱ  Pause microphone")
            self.begin()

    def pause(self):
        was_listening = self.listening
        self.listening = False
        self.speaker.stop()
        self.manikin.set_status("Ready")
        self.mic_state.set("Microphone off")
        self.start_button.configure(text="●  Start microphone")
        if self.running:
            # Resolve the task on its loop, after the queued start callback has run.
            def cancel_active():
                if self.active:
                    # Read before cancellation unwinds the worker and clears its busy flag.
                    self.idle_listening_pause = was_listening and not getattr(self.controller, "busy", True)
                    self.active.cancel()

            self.loop.call_soon_threadsafe(cancel_active)
        self.state.set(
            "Microphone off. Waiting for the active operation to stop…" if self.running else "Microphone off."
        )

    def ask_text(self):
        if self.session_queue.finishing or self.session_queue.starting:
            return
        # While a session is listening the worker is busy by design, so a typed question joins
        # its queue instead of being refused; with no session it is a one-off operation.
        listening = self.runtime.work is not None
        if (self.running and not listening) or not self.saved or self.page != "talk":
            return
        question = self.typed_question.get().strip()
        if not question:
            self.state.set("Type a question, or start the microphone.")
            return
        self.speaker.stop()
        self.manikin.stop_animation()
        self.settings.streaming = self.streaming.get()
        self.typed_question.set("")
        # A typed question has no capture, so the previous turn's microphone reading must not
        # be shown beside it.
        self.capture_quality = None
        if not listening:
            self.submit(self.runtime.text_turn(question))
            return

        def enqueue():
            try:
                self.runtime.enqueue_text(question)
            except ClientError as error:
                self.emit("turn_failed", str(error))

        self.loop.call_soon_threadsafe(enqueue)

    def confirm_complete(self):
        if self.closing or self.page != "talk" or self.session_queue.starting or self.session_queue.finishing:
            return
        confirmed = messagebox.askyesno(
            "Complete & Close",
            "Complete this practice session and return to Practice setup?",
            parent=self.root,
            default=messagebox.NO,
        )
        # Timer expiry or a web stop can finish the session while the modal is open.
        if (
            confirmed
            and not self.closing
            and self.page == "talk"
            and not self.session_queue.starting
            and not self.session_queue.finishing
        ):
            self.session_queue.finish()

    def back(self):
        if self.running:
            return
        self.camera_view.stop()
        self.pause()
        self.page = "setup"
        self.talk_frame.pack_forget()
        self.setup_frame.pack(fill="both", expand=True)
        self.step.set("01  Practice setup     →     02  Conversation")
        self.state.set("Review your practice setup. Save to start a new conversation.")

    def reset(self):
        if self.session_queue.assigned():
            self.state.set("Complete the assigned session before starting another conversation.")
            return
        if self.running:
            self.state.set("Cancel the current question before starting a new conversation.")
            return
        self.camera_view.stop()
        self.pause()
        self.warning_label.grid_remove()
        if self.controller:
            self.submit(self.runtime.reset_conversation(), "setup_saved")
        self.replace(self.question, "")
        self.replace(self.answer, "Ready for a new interview with the same practice setup.")
        self.state.set("Conversation cleared. Start the microphone or type a question.")

    def check_request(self):
        if not self.controller or self.running or self.page != "talk":
            return

        async def check():
            pms = self.controller.pms
            recovery = pms.recovery_request
            if (recovery and recovery[0] == "speech") or (
                not recovery and pms.last_speech_request and not pms.last_request
            ):
                result = await pms.speech_request_status(recovery[1] if recovery else None)
                self.emit("state", "Last transcription: " + result["status"])
                if result["status"] == "succeeded":
                    self.emit("transcript", result["result"]["text"])
                    self.emit(
                        "state",
                        "Transcript recovered. Submit it as a typed question to continue; audio was not replayed.",
                    )
                return
            if self.controller.runs_locally():
                # This profile runs the model here, so no answer request was ever submitted
                # to PMS and there is nothing for it to recover.
                self.emit(
                    "state",
                    "This reply ran locally and has no central inference request to recover. "
                    "Check History for saved exchanges before asking again.",
                )
                return
            result = await pms.status(recovery[1] if recovery else None)
            self.emit("state", "Last request: " + result["status"])
            if result["status"] == "succeeded":
                self.emit("answer", result["result"]["text"])

        self.submit(check(), "checked")

    def drain(self):
        if self.closing:
            return
        self.camera_view.poll()
        if self.camera_view.recording:
            self.record_label.grid()
        else:
            self.record_label.grid_remove()
        for _ in range(64):
            try:
                kind, value = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "history_status":
                from .history_view import STATUS

                key = value.get("turn_key")
                if value["status"] == "pending_local_save":
                    self.history_turn = key
                if key is None or key == self.history_turn or value["status"] == "not_saved":
                    self.history_message.set(STATUS.get(value["status"], "History status unavailable"))
            elif kind == "session_sync":
                self.history_message.set(value)
            elif kind == "ready":
                self.health.set(value)
            elif kind == "model_dialog":
                if self.model_dialog:
                    self.model_dialog.handle(value)
                # A committed reload must update the main screen even if its dialog
                # closed after the worker applied it and before this event was drained.
                if value[1] == "loaded":
                    self.speaker.stop()
                    self.camera_view.stop()
                    self.page = "setup"
                    self.talk_frame.pack_forget()
                    self.setup_frame.pack(fill="both", expand=True)
                    self.step.set("01  Practice setup → 02  Conversation")
                    if self.catalog_data:
                        self.apply_catalog(self.catalog_data, self.saved)
            elif kind == "local_models_metadata":
                self.voices = {DEFAULT_VOICE_CHOICE: None} | {
                    entry["label"]: entry["key"] for entry in self.speaker.catalogue()
                }
                self.voice_box.configure(values=list(self.voices))
                self.voice.set(self.voice_label_for(self.settings))
            elif kind == "catalog":
                self.apply_catalog(*value)
            elif kind == "queue_begun":
                self.session_queue.begun(*value)
            elif kind == "queue_snapshot":
                self.session_queue.received(value)
            elif kind == "queue_stopping":
                self.session_queue.stopping()
            elif kind in {"queue_start_failed", "queue_unavailable"}:
                self.session_queue.label.configure(text="Queue unavailable · Check the platform connection")
            elif kind == "queue_finished":
                self.root.after(100, self.session_queue.finished)
            elif kind == "queue_finish_failed":
                self.session_queue.label.configure(text="Ending session · Waiting for platform confirmation")
            elif kind == "case":
                self.render_case(value)
            elif kind == "saved":
                self.warning_label.grid_remove()
                self.saved = value
                if self.loaded_case and value.get("scenario_id"):
                    self.render_case({**self.loaded_case, "document": value["document"]})
                self.manikin.configure_patient(value)
                self.active_case.set(value["document"]["patient"]["name"] + "  ·  " + self.case_choice.get())
                self.page = "talk"
                self.setup_frame.pack_forget()
                self.talk_frame.pack(fill="both", expand=True)
                self.step.set("✓  Practice setup saved     →     02  Conversation")
                self.replace(self.question, "")
                self.replace(self.answer, "")
                # Load the voice now so the first answer is not delayed by model load.
                self.speaker.stop()
                self.speaker.warm(value["language"], patient_gender(value))
                self.state.set("Setup saved. Start the microphone or type your first question.")
            elif kind == "state":
                self.state.set(value)
                self.manikin.set_status("Retrying" if self.retrying else value)
            elif kind == "retrying":
                self.retrying = value
                input_state = "normal" if self.listening and not value else "disabled"
                self.question_entry.configure(state=input_state)
                self.ask_button.configure(state=input_state)
                if value:
                    self.manikin.set_status("Retrying")
                else:
                    self.retry_notice.hide()
                self.start_button.configure(
                    text="Cancel queued question"
                    if value
                    else "Ⅱ  Pause microphone"
                    if self.listening
                    else "●  Start microphone"
                )
            elif kind == "retry_status":
                if self.retrying and self.page == "talk":
                    self.retry_notice.show(value)
            elif kind == "retry_exhausted":
                self.retry_exhausted = True
            elif kind == "transcript":
                self.replace(self.question, value)
            elif kind == "input_ignored":
                if self.controller and value["generation"] != getattr(
                    self.controller, "_conversation_generation", 0
                ):
                    continue
                self.warning_label.grid_remove()
                self.replace(self.question, value["text"])
                self.replace(self.answer, "")
                self.manikin.stop_animation()
                self.manikin.set_status("Listening" if self.listening else "Ready")
                self.state.set(
                    "No question to answer. "
                    + ("Still listening." if self.listening else "Ready for your question.")
                )
            elif kind == "answer":
                self.warning_label.grid_remove()
                self.replace(self.answer, value)
                self.manikin.speak(value)
            elif kind == "answer_delta":
                self.replace(self.answer, value, True)
                self.manikin.speak(self.answer.get("1.0", "end-1c"))
            elif kind == "speech_started":
                if value.get("performance"):
                    self.performance_turn_id = value["performance"].turn_id
                self.manikin.stop_speech_gesture()
                self.manikin.prepare_speech_gesture(value["progress"])
            elif kind == "capture":
                self.capture_quality = value
            elif kind == "new_turn":
                self.performance_turn_id = None
                self.replace(self.question, "")
            elif kind == "metrics":
                capture = self.capture_quality.snapshot() if self.capture_quality else None
                mic = (
                    f"    ·    Mic: {capture['speech_dbfs']:.0f} dBFS, SNR {capture['snr_db']} dB"
                    if capture and capture["snr_db"] is not None
                    else ""
                )
                answer_ms = value["pms_roundtrip_ms"]
                answer_time = f"{answer_ms / 1000:.2f} s" if answer_ms is not None else "not requested"
                self.timing.set(
                    f"Transcription: {value['asr_finalize_ms'] / 1000:.2f} s    ·    "
                    f"Answer: {answer_time}{mic}"
                )
            elif kind == "capture_quality":
                # Bad audio must never be mistaken for a bad model, so say so explicitly.
                if value:
                    self.state.set("Microphone: " + "; ".join(value))
            elif kind == "performance":
                if value["turn_id"] != getattr(self, "performance_turn_id", None):
                    continue
                # Monotonic software/device estimates, not claimed physical sound.
                estimate = value.get("estimated_audible_ms")
                if estimate is not None:
                    self.state.set(
                        "Speaking"
                        if value["playback_complete_ms"] is None
                        else "Complete"
                        if value["playback_status"] == "completed"
                        else "Audio stopped"
                    )
                    self.timing.set(
                        f"Response to audio (estimated): {estimate / 1000:.2f} s"
                        + (" · over 5 s" if value["slow"] else "")
                    )
            elif kind == "mic_check":
                self.state.set(value)
            elif kind == "mic":
                # The microphone's own surface: it says whether input is actually being heard,
                # never what is happening to a question already captured.
                self.mic_state.set(value)
            elif kind == "queued":
                if value:
                    self.state.set(f"Queued: {value} question{'s' if value > 1 else ''} waiting")
                    self.manikin.set_status(f"Queued: {value}")
            elif kind == "turn_failed":
                # One question failed; the session is still listening, so the microphone
                # surface is left alone and only the processing surface reports it.
                self.retrying = False
                self.retry_notice.hide()
                self.manikin.set_status("Listening" if self.listening else "Ready")
                self.show_warning(value)
                self.state.set(value + " — still listening; ask again when ready.")
            elif kind in {
                "initialized",
                "case_loaded",
                "setup_saved",
                "turn_complete",
                "session_ended",
                "checked",
                "error",
                "cancelled",
            }:
                self.running = False
                self.retrying = False
                self.retry_notice.hide()
                self.active = None
                self.lock_options(False)
                if kind in {"session_ended", "error", "cancelled"}:
                    # The device is released with the session, so the surface must say so.
                    self.mic_state.set("Microphone off")
                if kind == "initialized" and not self.loaded_case and self.catalog_data:
                    self.load_case()
                elif kind in {"error", "cancelled", "session_ended"}:
                    # The session owned the device for its whole life, so it ending means the
                    # microphone is closed. Nothing reopens it but the operator.
                    self.listening = False
                    self.manikin.set_status("Ready")
                    self.start_button.configure(text="●  Start microphone")
                    local = bool(self.controller) and self.controller.runs_locally()
                    note = (
                        value
                        if kind == "error"
                        else "Listening stopped."
                        if kind == "session_ended"
                        else "Cancelled. Ask the question again."
                        if local
                        else "Cancelled. Check last request to recover a completed answer; no automatic replay."
                    )
                    if kind != "session_ended":
                        self.show_warning(note)
                    self.state.set(note + " Start the microphone to continue.")
        self.manikin.update_speech_gesture(
            self.speaker.speaking and not self.retrying and self.page == "talk", self.speaker.progress
        )
        if self.speaker.speaking and not self.retrying:
            # Real audio drives the expression; the text estimate only covers silent mode.
            self.manikin.hold_speaking()
        elif not self.retrying and (note := self.speaker.last_error):
            # A missing voice or a failed device is reported once, never silently swallowed.
            self.speaker.last_error = None
            self.state.set(note)
        self.manikin.update_idle_gesture(
            self.page == "talk"
            and not self.retrying
            and not self.speaker.speaking
            and (not self.running or self.listening)
        )
        self.manikin.update_blink(self.page == "talk")
        self.root.after(30, self.drain)

    # Retained bounded task/queue and shutdown helpers inserted below.
    def emit(self, kind, value):
        try:
            self.events.put_nowait((kind, value))
        except queue.Full:
            transient = {
                "mic",
                "queued",
                "history_status",
                "session_sync",
                "performance",
                "ready",
                "state",
                "retry_status",
                "answer_delta",
                "queue_snapshot",
                "queue_unavailable",
            }
            if kind in transient:
                # A final answer carries the complete text if streamed deltas are dropped.
                return
            # Preserve committed setup, final answers and lifecycle events. Queue's lock
            # keeps the replacement atomic with producers and the Tk consumer.
            with self.events.mutex:
                pending = self.events.queue
                stale = next((index for index, item in enumerate(pending) if item[0] in transient), None)
                if stale is not None:
                    del pending[stale]
                elif len(pending) >= self.events.maxsize * 2:
                    # Keep a small reserve for completion events when every queued event
                    # is already important, while retaining a hard memory bound.
                    pending.popleft()
                else:
                    self.events.unfinished_tasks += 1
                pending.append((kind, value))
                self.events.not_empty.notify()

    def submit(self, coro, completion="turn_complete"):
        if self.running:
            coro.close()
            return
        self.running = True
        self.idle_listening_pause = False
        self.retry_exhausted = False
        self.lock_options(True)

        def start():
            self.active = self.loop.create_task(coro)

            def done(task):
                if self.closing:
                    with suppress(asyncio.CancelledError, Exception):
                        task.result()
                    return
                try:
                    task.result()
                    self.emit(completion, None)
                except asyncio.CancelledError:
                    self.emit(
                        "session_ended"
                        if completion == "session_ended" and self.idle_listening_pause
                        else "cancelled",
                        None,
                    )
                except Exception as error:
                    if isinstance(error, ClientError) and error.retry_exhausted:
                        self.emit("retry_exhausted", True)
                    message = (
                        str(error)
                        if isinstance(error, ClientError)
                        else type(error).__name__ + "; check service configuration"
                    )
                    self.emit("error", message)

            self.active.add_done_callback(done)

        self.loop.call_soon_threadsafe(start)

    @staticmethod
    def replace(widget, value, append=False):
        if not append and widget.get("1.0", "end-1c") == value:
            return
        widget.configure(state="normal")
        if not append:
            widget.delete("1.0", "end")
        widget.insert("end", value)
        widget.see("end")
        widget.configure(state="disabled")

    def open_provisioning(self):
        if self.closing:
            return
        if not messagebox.askyesno(
            "Device setup",
            "End this Practice session and open device connection settings?",
            parent=self.root,
        ):
            return
        self.reopen_provisioning = True
        self.close()

    def close(self):
        if self.closing:
            return
        self.closing = True
        if self.history_window and self.history_window.window.winfo_exists():
            self.history_window.close()
        self.retry_notice.hide()
        self.camera_view.close()
        self.manikin.stop_animation(redraw=False)
        self.listening = False
        self.speaker.stop()
        if self.active:
            self.loop.call_soon_threadsafe(self.active.cancel)

        async def cleanup():
            if self.active:
                self.active.cancel()
                with suppress(asyncio.CancelledError, Exception):
                    await asyncio.wait_for(self.active, 5)
            await self.runtime.close()
            await self.loop.shutdown_asyncgens()

        future = asyncio.run_coroutine_threadsafe(cleanup(), self.loop)
        deadline = time.monotonic() + 35

        def finish():
            self.camera_view.poll()
            sync = getattr(self.controller, "sync", None)
            disk = getattr(sync, "disk", None)
            writer_busy = bool(disk and disk.is_alive())
            if (
                not future.done() or self.camera_view.recorder.busy or writer_busy
            ) and time.monotonic() < deadline:
                self.root.after(50, finish)
                return
            failed = writer_busy or self.camera_view.recorder.busy or not future.done()
            if future.done():
                try:
                    future.result()
                except Exception:
                    failed = True
            if failed:
                messagebox.showwarning(
                    "Shutdown incomplete",
                    "Some local work may not have finished saving. Check sync after restarting.",
                    parent=self.root,
                )
            self.loop.call_soon_threadsafe(self.loop.stop)
            self.worker.join(timeout=1)
            if not self.worker.is_alive():
                self.loop.close()
            # Tk removes widget commands on destruction but leaves Tcl timers alive.
            # Cancel this window's callbacks before the interpreter is reused for pairing.
            for job in self.root.tk.splitlist(self.root.tk.call("after", "info")):
                self.root.after_cancel(job)
            self.root.destroy()

        finish()


def main():
    # Console entry points and direct module launches use the same pairing wizard.
    # The connection launcher sets this flag only for its prepared desktop child.
    import os
    import subprocess
    import sys
    from pathlib import Path

    if os.environ.get("HUMAN_DESKTOP_PREPARED", "").lower() != "true":
        launcher = Path(__file__).resolve().parents[3] / "start/launch.py"
        raise SystemExit(subprocess.call([sys.executable, "-X", "utf8", str(launcher), *sys.argv[1:]]))
    root = tk.Tk()
    try:
        window = Window(root, Settings())
    except Exception:
        ttk.Label(
            root, text="Could not open patient practice. Check .env and dependencies.", padding=25
        ).pack()
        window = None
    root.mainloop()
    if window is not None and window.reopen_provisioning:
        raise SystemExit(42)


if __name__ == "__main__":
    main()
