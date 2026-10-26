"""
themes.py — portable color-theme system, ported from iTeroToolBox's
HTML/CSS theme engine (see themes.css in this same folder for the
original — that version is for a web/HTML app; this one is for Tkinter,
where there's no CSS at all, just widget options you set in Python).

HOW IT WORKS
------------
One flat dict per theme, all using the same set of keys. Nothing in your
UI code should ever hardcode a color — always look it up from whichever
theme dict is currently active, e.g. THEMES[current]["text"]. Switching
themes is just switching which dict is "current" and re-applying it to
every widget (see apply_theme_to_widget / apply_theme_to_ttk below).

TOKEN REFERENCE
---------------
Surfaces (4-step elevation, low to high):        bg, bg2, bg3, bg4
Borders (2-step):                                border, border2
Text (3-step hierarchy):                         text, text2, text3
Semantic colors (+ a pale "_bg" tint each,
blue also gets a "_dim" hover/pressed step):      blue / blue_bg / blue_dim
                                                   green / green_bg
                                                   amber / amber_bg
                                                   red / red_bg
                                                   teal / teal_bg
                                                   purple / purple_bg
Brand accent (usually mirrors blue, kept
separate so it CAN diverge):                      accent / accent_dim

Optional secondary set — only meaningful if your app has a distinctly
colored title/header bar separate from the main window background (a
few of the themes below use this for a colorful bar with a badge on it;
skip it entirely if your Tkinter window doesn't have anything like that):
    titlebar_bg, tb_name, tb_role, tb_role_bg, tb_role_border

ADDING A NEW THEME
-------------------
Copy any existing dict, rename the key, fill in every color. Every
theme repeats the full key set on purpose (no inheritance/fallback like
the CSS version has via :root) — Tkinter has no cascade, so an
apply_theme() call needs every key to actually be present.
"""

THEMES = {
    # ---- dark — the default theme -----------------------------------
    "dark": {
        "bg": "#0d0f12", "bg2": "#13161b", "bg3": "#191d24", "bg4": "#1f242d",
        "border": "#252b36", "border2": "#2e3848",
        "text": "#edf1f7", "text2": "#9ab2c8", "text3": "#60788e",
        "blue": "#5fa8e8", "blue_bg": "#111d2e", "blue_dim": "#152238",
        "green": "#4ab87e", "green_bg": "#0d1f17",
        "amber": "#e09b3a", "amber_bg": "#1f1608",
        "red": "#d95a4a", "red_bg": "#1e0f0d",
        "teal": "#5fa8e8", "teal_bg": "#111d2e",       # aliased to blue
        "purple": "#5fa8e8", "purple_bg": "#111d2e",   # aliased to blue
        "accent": "#5fa8e8", "accent_dim": "#152238",
    },

    "light": {
        "bg": "#f0f3f7", "bg2": "#ffffff", "bg3": "#f5f7fa", "bg4": "#e8ecf2",
        "border": "#dde3eb", "border2": "#bcc7d4",
        "text": "#1a2636", "text2": "#3d5a72", "text3": "#6e8fa8",
        "blue": "#1a72c4", "blue_bg": "#deedfb", "blue_dim": "#c2dff7",
        "green": "#1d8a55", "green_bg": "#d4f1e3",
        "amber": "#b5720a", "amber_bg": "#fdf0d9",
        "red": "#c42828", "red_bg": "#fce8e6",
        "teal": "#1a72c4", "teal_bg": "#deedfb",
        "purple": "#1a72c4", "purple_bg": "#deedfb",
        "accent": "#1a72c4", "accent_dim": "#c2dff7",
    },

    # ---- "character" themes — same tokens, plus the optional
    #      titlebar set for a colorful header bar with a badge --------
    "theme_warm_cream": {  # was "pompompurin"
        "bg": "#fdf2cf", "bg2": "#fffaf0", "bg3": "#fbeec9", "bg4": "#f5e1a8",
        "border": "#e8d3a0", "border2": "#d4b876",
        "text": "#4a2c1c", "text2": "#6e4226", "text3": "#8f5a36",
        "blue": "#7a4a2e", "blue_bg": "#f5e6c8", "blue_dim": "#d4ad79",
        "green": "#4d6e2e", "green_bg": "#e8f0d4",
        "amber": "#a8600f", "amber_bg": "#fbe8c4",
        "red": "#a3402c", "red_bg": "#f7e0d4",
        "teal": "#7a4a2e", "teal_bg": "#f5e6c8",
        "purple": "#7a4a2e", "purple_bg": "#f5e6c8",
        "accent": "#7a4a2e", "accent_dim": "#d4ad79",
        "titlebar_bg": "#7a4a2e", "tb_name": "#fff8e8", "tb_role": "#4a2c1c",
        "tb_role_bg": "#fffaf0", "tb_role_border": "#e8d3a0",
    },

    "theme_forest_dark": {  # was "roronoa"
        "bg": "#000000", "bg2": "#11150f", "bg3": "#1a2017", "bg4": "#232b1d",
        "border": "#3f4f3c", "border2": "#566b4f",
        "text": "#eaf2e6", "text2": "#a9c2a0", "text3": "#74926a",
        "blue": "#2fbd1f", "blue_bg": "#0a3d0f", "blue_dim": "#0f5717",
        "green": "#2fbd1f", "green_bg": "#0a3d0f",
        "amber": "#c98a4a", "amber_bg": "#241a10",
        "red": "#a3402c", "red_bg": "#241616",
        "teal": "#2fbd1f", "teal_bg": "#0a3d0f",
        "purple": "#8a5c5c", "purple_bg": "#241616",
        "accent": "#2fbd1f", "accent_dim": "#0f5717",
        "titlebar_bg": "#0a3d0f", "tb_name": "#eaf2e6", "tb_role": "#a9c2a0",
        "tb_role_bg": "#11150f", "tb_role_border": "#3f4f3c",
    },

    "theme_blush_pink": {  # was "melody"
        "bg": "#fdf3f9", "bg2": "#fff8fc", "bg3": "#f3ddec", "bg4": "#ecc9e3",
        "border": "#ddb2ee", "border2": "#c98fd4",
        "text": "#5a3a52", "text2": "#7a5470", "text3": "#9c7693",
        "blue": "#e08bab", "blue_bg": "#fbe4ee", "blue_dim": "#f0a0bb",
        "green": "#6a9e7a", "green_bg": "#e7f0e9",
        "amber": "#c99a5a", "amber_bg": "#f5ead8",
        "red": "#c96a7a", "red_bg": "#f7e2e6",
        "teal": "#e08bab", "teal_bg": "#fbe4ee",
        "purple": "#c98fd4", "purple_bg": "#f0ddf5",
        "accent": "#e08bab", "accent_dim": "#f0a0bb",
        "titlebar_bg": "#cf7aa0", "tb_name": "#fdf3f9", "tb_role": "#5a3a52",
        "tb_role_bg": "#fff8fc", "tb_role_border": "#ddb2ee",
    },

    "theme_midnight_maroon": {  # was "itachi"
        "bg": "#1c1e22", "bg2": "#22252b", "bg3": "#2b3550", "bg4": "#333d5c",
        "border": "#3a4565", "border2": "#4a5680",
        "text": "#dcdcd8", "text2": "#a8acb5", "text3": "#7d8194",
        "blue": "#3f72b0", "blue_bg": "#163e6e", "blue_dim": "#2a5283",
        "green": "#4a8f6a", "green_bg": "#16261e",
        "amber": "#c98a4a", "amber_bg": "#2a2014",
        "red": "#8e1b30", "red_bg": "#2a1318",
        "teal": "#3f72b0", "teal_bg": "#163e6e",
        "purple": "#8e1b30", "purple_bg": "#2a1318",
        "accent": "#3f72b0", "accent_dim": "#2a5283",
        "titlebar_bg": "#8e1b30", "tb_name": "#f1ece9", "tb_role": "#dcdcd8",
        "tb_role_bg": "#2b3550", "tb_role_border": "#4a5680",
    },

    "theme_amber_orange": {  # was "uzumaki"
        "bg": "#13100a", "bg2": "#1c1710", "bg3": "#2e2010", "bg4": "#3d2c16",
        "border": "#4a3418", "border2": "#6e4e22",
        "text": "#f0e0c0", "text2": "#c8a870", "text3": "#8a7048",
        "blue": "#e07820", "blue_bg": "#3a1c04", "blue_dim": "#a85810",
        "green": "#60943a", "green_bg": "#162008",
        "amber": "#e0a828", "amber_bg": "#342408",
        "red": "#c03828", "red_bg": "#2e0e08",
        "teal": "#e07820", "teal_bg": "#3a1c04",
        "purple": "#e0a828", "purple_bg": "#342408",
        "accent": "#e07820", "accent_dim": "#a85810",
        "titlebar_bg": "#c05818", "tb_name": "#fff0d8", "tb_role": "#ffc870",
        "tb_role_bg": "#3a1c04", "tb_role_border": "#6e4e22",
    },

    "theme_lemon_yellow": {  # was "sponge"
        "bg": "#fffce6", "bg2": "#ffffff", "bg3": "#fdf6c4", "bg4": "#f9ed5b",
        "border": "#f0dc7a", "border2": "#d4b83a",
        "text": "#2b2410", "text2": "#6b5a1f", "text3": "#9c8a4a",
        "blue": "#2f7ec4", "blue_bg": "#dcedfb", "blue_dim": "#7bb4e6",
        "green": "#3f8f4a", "green_bg": "#dff2e1",
        "amber": "#b2793b", "amber_bg": "#f5e6cc",
        "red": "#e53636", "red_bg": "#fbdede",
        "teal": "#2f7ec4", "teal_bg": "#dcedfb",
        "purple": "#b2793b", "purple_bg": "#f5e6cc",
        "accent": "#2f7ec4", "accent_dim": "#7bb4e6",
        "titlebar_bg": "#ebde3d", "tb_name": "#2b2410", "tb_role": "#6b5a1f",
        "tb_role_bg": "#fffef2", "tb_role_border": "#f0dc7a",
    },

    "theme_black_red": {  # was "warner"
        "bg": "#0d0d0d", "bg2": "#161616", "bg3": "#1c1c1c", "bg4": "#242424",
        "border": "#333333", "border2": "#4d4d4d",
        "text": "#f2f0ee", "text2": "#b0aca8", "text3": "#787472",
        "blue": "#b8291f", "blue_bg": "#2a0e0e", "blue_dim": "#8a1f1f",
        "green": "#3fae63", "green_bg": "#0f2a18",
        "amber": "#d9932e", "amber_bg": "#2e2008",
        "red": "#e2342c", "red_bg": "#3a0f0d",
        "teal": "#b8291f", "teal_bg": "#2a0e0e",
        "purple": "#8a1f1f", "purple_bg": "#2a0e0e",
        "accent": "#b8291f", "accent_dim": "#8a1f1f",
        "titlebar_bg": "#000000", "tb_name": "#e2342c", "tb_role": "#f2f0ee",
        "tb_role_bg": "#2a0e0e", "tb_role_border": "#e2342c",
    },
}


# TEMPLATE — copy this to add a new theme:
#
#     "theme_your_name": {
#         "bg": "#______", "bg2": "#______", "bg3": "#______", "bg4": "#______",
#         "border": "#______", "border2": "#______",
#         "text": "#______", "text2": "#______", "text3": "#______",
#         "blue": "#______", "blue_bg": "#______", "blue_dim": "#______",
#         "green": "#______", "green_bg": "#______",
#         "amber": "#______", "amber_bg": "#______",
#         "red": "#______", "red_bg": "#______",
#         "teal": "#______", "teal_bg": "#______",
#         "purple": "#______", "purple_bg": "#______",
#         "accent": "#______", "accent_dim": "#______",
#         # optional, only if this theme has its own colored header bar:
#         "titlebar_bg": "#______", "tb_name": "#______", "tb_role": "#______",
#         "tb_role_bg": "#______", "tb_role_border": "#______",
#     },


# ============================================================================
# APPLYING A THEME TO TKINTER WIDGETS
# ============================================================================
# Tkinter has two widget families that need different treatment:
#   - classic tk widgets (tk.Frame, tk.Label, tk.Entry, tk.Text, ...)
#     accept bg/fg options directly on each widget instance.
#   - ttk widgets (ttk.Frame, ttk.Button, ttk.Entry, ttk.Combobox, ...)
#     are colored through a shared ttk.Style() instead — you configure a
#     *style name* once, and every widget using that style re-colors
#     immediately, no per-widget loop needed.
# A real app almost always has both; use whichever helper matches each
# widget. Adjust the specific options/style names below to whatever your
# actual widget tree uses — this is a starting point, not a drop-in-and
# -done for every possible widget.

import tkinter as tk
from tkinter import ttk


def apply_theme_to_widget(widget, theme):
    """Recursively re-color every classic tk widget under `widget`.
    Silently skips any option/widget that doesn't support bg/fg (that
    includes ttk widgets — use apply_theme_to_ttk for those)."""
    for opt, key in (("bg", "bg2"), ("background", "bg2"),
                     ("fg", "text"), ("foreground", "text")):
        try:
            widget.configure(**{opt: theme[key]})
        except tk.TclError:
            pass
    for child in widget.winfo_children():
        apply_theme_to_widget(child, theme)


def apply_theme_to_ttk(theme, style=None):
    """Configure a ttk.Style() so ttk widgets pick up the theme too.
    Call this once per theme switch — every ttk widget using these style
    names updates on its own, it's not a per-widget walk like the
    classic-tk helper above.

    'clam' is used as the base ttk theme because it's the one most
    willing to accept full color overrides — Windows' native themes
    ('vista', 'winnative') ignore most style.configure() calls and keep
    the OS's own colors regardless of what you set here.
    """
    style = style or ttk.Style()
    style.theme_use("clam")

    style.configure("TFrame", background=theme["bg2"])
    style.configure("TLabel", background=theme["bg2"], foreground=theme["text"])
    style.configure("TButton", background=theme["bg3"], foreground=theme["text"],
                     bordercolor=theme["border"], focuscolor=theme["blue"])
    style.map("TButton",
              background=[("active", theme["bg4"]), ("pressed", theme["bg4"])])
    style.configure("TEntry", fieldbackground=theme["bg3"], foreground=theme["text"],
                     bordercolor=theme["border"])
    style.configure("TCombobox", fieldbackground=theme["bg3"], foreground=theme["text"],
                     background=theme["bg3"])
    style.configure("TCheckbutton", background=theme["bg2"], foreground=theme["text"])
    style.configure("TNotebook", background=theme["bg2"], bordercolor=theme["border"])
    style.configure("TNotebook.Tab", background=theme["bg3"], foreground=theme["text2"])
    style.map("TNotebook.Tab",
              background=[("selected", theme["bg4"])],
              foreground=[("selected", theme["text"])])
    return style


def apply_theme(root, name):
    """One call to re-theme an entire app: classic tk widgets under
    `root` plus the shared ttk style. `root` is your Tk()/Toplevel()
    instance."""
    theme = THEMES[name]
    root.configure(bg=theme["bg"])
    apply_theme_to_widget(root, theme)
    apply_theme_to_ttk(theme)
    return theme


if __name__ == "__main__":
    # Minimal smoke test / live preview — cycles through every theme so
    # you can eyeball the palette before wiring this into a real app.
    root = tk.Tk()
    root.title("Theme preview")
    root.geometry("360x220")

    frame = ttk.Frame(root, padding=16)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="Sample label", font=("Segoe UI", 13, "bold")).pack(anchor="w")
    ttk.Label(frame, text="Secondary text").pack(anchor="w", pady=(2, 10))
    ttk.Entry(frame).pack(fill="x", pady=4)
    ttk.Button(frame, text="Primary action").pack(anchor="w", pady=4)
    combo = ttk.Combobox(frame, values=["Option A", "Option B"])
    combo.pack(fill="x", pady=4)

    names = list(THEMES.keys())
    idx = {"i": 0}

    def cycle():
        apply_theme(root, names[idx["i"]])
        root.title(f"Theme preview — {names[idx['i']]}")
        idx["i"] = (idx["i"] + 1) % len(names)
        root.after(1500, cycle)

    cycle()
    root.mainloop()
