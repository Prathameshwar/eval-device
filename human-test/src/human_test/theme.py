"""Design tokens and ttk styles shared by every desktop surface.

One palette, one spacing scale and one set of named styles, so the setup page, the
conversation stage, the dock, the drawer, the menu and the overlays read as a single product.
Tokens are plain constants: Tk has no stylesheet, and every raw ``tk`` widget (menus, banners,
overlays) needs the same values as the ttk styles.
"""

import tkinter as tk
from tkinter import ttk

# Palette
BG = "#edf3f7"  # window ground
SURFACE = "#ffffff"  # cards, dock, drawer
SURFACE_ALT = "#f1f6fa"  # question text, pills
SURFACE_OK = "#eaf7f3"  # answer text
INK = "#183248"
MUTED = "#627788"
LINE = "#d5e2e9"
TEAL = "#007f82"
TEAL_DARK = "#006669"
TEAL_DISABLED = "#b3c9cc"
NAVY = "#102d43"
AMBER = "#936414"
AMBER_BG = "#fff8e8"
AMBER_LINE = "#d9bd80"
AMBER_INK = "#76531a"
RECORD = "#b3261e"
RECORD_BG = "#fdecea"

# Spacing scale (px)
SPACE_XS, SPACE_SM, SPACE_MD, SPACE_LG, SPACE_XL = 4, 8, 12, 16, 24

# Type scale
FONT = "Segoe UI"
TEXT_FONT = "Nirmala UI"  # covers Devanagari for Hindi transcripts and answers


def font(size, weight=None, family=FONT):
    return (family, size, weight) if weight else (family, size)


DRAWER_WIDTH = 340
PREVIEW_INSET = 12


def apply_styles(root):
    """Configure the clam theme with the product palette; idempotent."""
    root.configure(bg=BG)
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("TFrame", background=BG)
    style.configure("Card.TFrame", background=SURFACE)
    style.configure("CaseInfo.TFrame", background=SURFACE_ALT)
    style.configure("CaseInfo.TLabel", background=SURFACE_ALT, foreground=INK, font=font(11, "bold"))
    style.configure("CaseInfoCaption.TLabel", background=SURFACE_ALT, foreground=MUTED, font=font(9))
    style.configure("Dock.TFrame", background=SURFACE)
    style.configure("TLabel", background=BG, foreground=INK, font=font(10))
    style.configure("Card.TLabel", background=SURFACE, foreground=INK)
    style.configure("Muted.TLabel", background=SURFACE, foreground=MUTED)
    style.configure("Caption.TLabel", background=SURFACE, foreground=MUTED, font=font(9, "bold"))
    style.configure("Title.TLabel", background=SURFACE, font=font(17, "bold"))
    style.configure("StageTitle.TLabel", background=SURFACE, foreground=INK, font=font(14, "bold"))
    style.configure("Footer.TLabel", background=BG, foreground=TEAL)
    style.configure("FooterMuted.TLabel", background=BG, foreground=MUTED, font=font(9))
    style.configure(
        "Pill.TLabel", background="#dfe9ee", foreground=NAVY, font=font(9, "bold"), padding=(10, 4)
    )
    style.configure(
        "Record.TLabel", background=RECORD_BG, foreground=RECORD, font=font(9, "bold"), padding=(10, 4)
    )
    style.configure("TButton", padding=(12, 9), font=font(10), foreground=INK)
    style.configure("Primary.TButton", background=TEAL, foreground=SURFACE, borderwidth=0, padding=(18, 10))
    style.map(
        "Primary.TButton",
        background=[("disabled", TEAL_DISABLED), ("active", TEAL_DARK)],
        foreground=[("disabled", SURFACE)],
    )
    style.configure("Compact.TButton", padding=(8, 5), font=font(9))
    style.configure(
        "Icon.TButton",
        padding=(6, 2),
        font=font(14, "bold"),
        foreground=MUTED,
        background=SURFACE,
        borderwidth=0,
        relief="flat",
    )
    style.map(
        "Icon.TButton",
        background=[("active", SURFACE_ALT), ("pressed", LINE)],
        foreground=[("active", INK)],
    )
    style.configure("TCombobox", padding=7)
    style.map("TCombobox", fieldbackground=[("readonly", SURFACE)])
    style.configure("TCheckbutton", background=SURFACE, foreground=INK)
    style.configure("TEntry", padding=7)
    style.configure("Card.TSeparator", background=LINE)
    return style


def menu(parent, **options):
    """A popup menu in the product palette; Windows keeps its own frame but honours fonts."""
    return tk.Menu(
        parent,
        tearoff=0,
        font=font(10),
        bg=SURFACE,
        fg=INK,
        activebackground=TEAL,
        activeforeground=SURFACE,
        disabledforeground="#9fb0bb",
        relief="flat",
        borderwidth=1,
        **options,
    )
