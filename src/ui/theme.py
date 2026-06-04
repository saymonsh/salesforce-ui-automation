"""
Kivun design system — single source of truth for the Flet UI.

Import tokens (Color/Space/Radius/Type) and the component factories
(primary_button, text_field, card, ...) instead of hardcoding hex/sizes
in the views. Call apply_theme(page) once at startup to wire RTL, the
default Hebrew font, and the global Flet theme.

Brand palette derived from the Kivun logo:
  - magenta-red diamond  -> Color.BRAND
  - dark "כיוון" wordmark -> Color.CHARCOAL
  - gray tagline          -> neutral scale
"""
from __future__ import annotations

import os

import flet as ft

# assets/ lives at the project root (two levels above src/ui/).
_ASSETS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "assets",
)


# ---------------------------------------------------------------------------
# Design tokens
# ---------------------------------------------------------------------------
class Color:
    # Brand (from logo)
    BRAND = "#de2952"          # primary actions, focus, progress
    BRAND_HOVER = "#c01f45"    # hover/pressed on brand surfaces; active nav text on BRAND_TINT (AA 4.9:1)
    BRAND_TINT = "#fbe4ea"     # selected nav bg, subtle brand fills
    CHARCOAL = "#2b2b2b"       # logo wordmark, strong headings

    # Semantic
    SUCCESS = "#137a4e"        # completed runs (AA on white)
    WARNING = "#8a5a00"        # validation / caution (AA as normal text, 5.9:1)
    DANGER = "#c0392b"         # destructive / stop / errors (AA white-on)
    DANGER_HOVER = "#a5301f"
    INFO = "#2563eb"

    # Neutrals
    TEXT_PRIMARY = "#1a1a1a"   # body & headings
    TEXT_SECONDARY = "#595959" # secondary text (AA on white, ~7:1)
    TEXT_TERTIARY = "#767676"  # placeholder / hint (AA boundary)
    TEXT_ON_BRAND = "#ffffff"  # text over BRAND / DANGER / SUCCESS

    BORDER = "#d9d9d9"         # default field / divider borders (decorative)
    BORDER_STRONG = "#767676"  # emphasized / identifying borders (non-text AA, 4.5:1)
    SURFACE = "#ffffff"        # cards, sidebar, fields
    BACKGROUND = "#f4f4f4"     # page background
    SURFACE_INVERSE = "#1e1e1e"  # logs / terminal background


class Space:
    """4px base spacing scale."""
    XS = 4
    SM = 8
    MD = 12
    LG = 16
    XL = 20
    XXL = 24
    XXXL = 32


class Radius:
    SM = 6
    MD = 8       # default for buttons, fields, cards
    LG = 12
    PILL = 999


class Elevation:
    CARD = 2
    DIALOG = 6


class Font:
    # Primary Hebrew UI font (loaded in apply_theme). Falls back to the
    # system default (Segoe UI on Windows handles Hebrew well) if the
    # asset is missing.
    HEBREW = "Heebo"
    MONO = "Consolas"


class Type:
    """Type scale: (size, weight). Pair with Font.HEBREW."""
    H1 = (24, ft.FontWeight.W_700)      # screen titles
    H2 = (20, ft.FontWeight.W_700)      # section headers
    TITLE = (18, ft.FontWeight.W_600)   # card / sidebar titles
    BODY_LG = (16, ft.FontWeight.W_500) # status, prominent body
    BODY = (14, ft.FontWeight.W_400)    # default body
    CAPTION = (13, ft.FontWeight.W_400) # hints, log lines


# ---------------------------------------------------------------------------
# Global theme + RTL
# ---------------------------------------------------------------------------
def apply_theme(page: ft.Page) -> None:
    """Wire RTL, the default font, background and the Flet color scheme.

    Call once during page setup. This is what makes the whole app render
    right-to-left, so per-control text_align=RIGHT patches become unnecessary.
    """
    page.rtl = True
    page.bgcolor = Color.BACKGROUND
    page.theme_mode = ft.ThemeMode.LIGHT

    # Register the Hebrew font only if the asset is actually present, so we never
    # ship a broken font reference. Drop Heebo-VariableFont_wght.ttf into
    # assets/fonts/Heebo/ to enable it; otherwise we leave font_family unset and
    # the system default (Segoe UI on Windows) renders Hebrew correctly.
    heebo_path = os.path.join(_ASSETS_DIR, "fonts", "Heebo", "Heebo-VariableFont_wght.ttf")
    font_family = None
    if os.path.exists(heebo_path):
        page.fonts = {Font.HEBREW: "/fonts/Heebo/Heebo-VariableFont_wght.ttf"}
        font_family = Font.HEBREW

    page.theme = ft.Theme(
        font_family=font_family,
        color_scheme=ft.ColorScheme(
            primary=Color.BRAND,
            on_primary=Color.TEXT_ON_BRAND,
            error=Color.DANGER,
            surface=Color.SURFACE,
        ),
    )


# ---------------------------------------------------------------------------
# Component factories — base building blocks
# ---------------------------------------------------------------------------
def heading(text: str, level=Type.H1, color: str = Color.TEXT_PRIMARY) -> ft.Text:
    size, weight = level
    return ft.Text(text, size=size, weight=weight, color=color)


def body_text(
    text: str,
    level=Type.BODY,
    color: str = Color.TEXT_PRIMARY,
    **kwargs,
) -> ft.Text:
    size, weight = level
    return ft.Text(text, size=size, weight=weight, color=color, **kwargs)


def _button_style(bgcolor: str | None, fg: str, border: ft.BorderSide | None = None) -> ft.ButtonStyle:
    return ft.ButtonStyle(
        bgcolor=bgcolor,
        color=fg,
        side=border,
        shape=ft.RoundedRectangleBorder(radius=Radius.MD),
        padding=Space.XL,
    )


def primary_button(text: str, icon=None, **kwargs) -> ft.FilledButton:
    """Main call-to-action (one per view). Brand fill, white text."""
    return ft.FilledButton(
        text,
        icon=icon,
        style=_button_style(Color.BRAND, Color.TEXT_ON_BRAND),
        **kwargs,
    )


def secondary_button(text: str, icon=None, **kwargs) -> ft.OutlinedButton:
    """Supporting action. Outlined, neutral."""
    return ft.OutlinedButton(
        text,
        icon=icon,
        style=_button_style(None, Color.TEXT_SECONDARY, ft.BorderSide(1, Color.BORDER_STRONG)),
        **kwargs,
    )


def danger_button(text: str, icon=None, **kwargs) -> ft.FilledButton:
    """Destructive / stop action. Solid red so it is clearly visible."""
    return ft.FilledButton(
        text,
        icon=icon,
        style=_button_style(Color.DANGER, Color.TEXT_ON_BRAND),
        **kwargs,
    )


def text_field(label: str, value: str = "", **kwargs) -> ft.TextField:
    """Standard form input. RTL alignment comes from page.rtl — no per-field patch."""
    return ft.TextField(
        label=label,
        value=value,
        border_radius=Radius.MD,
        border_color=Color.BORDER,
        focused_border_color=Color.BRAND,
        cursor_color=Color.BRAND,
        # Transparent fill so the field blends with the (glass) surface it sits
        # on instead of showing a solid white box; the border defines it.
        bgcolor=ft.Colors.TRANSPARENT,
        color=Color.TEXT_PRIMARY,
        label_style=ft.TextStyle(color=Color.TEXT_SECONDARY),
        **kwargs,
    )


class SegmentedSelect:
    """Inline single-choice control — all options visible, no popup.

    Chosen over a dropdown so it blends with the glass surface (no opaque menu
    wedged over the form). `options` is a list of (key, text) pairs. Expose
    `.control` to place in a layout and `.value` for the selected key — the same
    `.value` interface as text_field/dropdown, so saving code is unchanged.
    """

    def __init__(self, label: str, options: list[tuple[str, str]], value: str = ""):
        self._value = value or (options[0][0] if options else "")
        self._segments: dict[str, ft.Container] = {}
        seg_row: list[ft.Control] = []
        for key, text in options:
            seg = ft.Container(
                data=key,
                expand=True,
                alignment=ft.Alignment.CENTER,
                padding=ft.padding.symmetric(vertical=Space.SM, horizontal=Space.SM),
                border_radius=Radius.SM,
                on_click=self._on_click,
                content=ft.Text(text, size=Type.BODY[0], weight=ft.FontWeight.W_600, text_align=ft.TextAlign.CENTER),
            )
            self._segments[key] = seg
            seg_row.append(seg)

        segmented = ft.Container(
            border=ft.border.all(1, Color.BORDER),
            border_radius=Radius.MD,
            padding=3,
            content=ft.Row(spacing=3, controls=seg_row),
        )
        self.control = ft.Column(
            spacing=Space.XS,
            controls=[
                ft.Text(label, size=Type.CAPTION[0], color=Color.TEXT_SECONDARY),
                segmented,
            ],
        )
        self._apply_styles()  # set initial look; do NOT update (not on page yet)

    @property
    def value(self) -> str:
        return self._value

    def _on_click(self, e: ft.ControlEvent) -> None:
        self._value = e.control.data
        self._apply_styles()
        # Mounted now, so push the new selection styling to the UI in one update.
        self.control.update()

    def _apply_styles(self) -> None:
        for key, seg in self._segments.items():
            selected = key == self._value
            seg.bgcolor = Color.BRAND if selected else ft.Colors.TRANSPARENT
            seg.content.color = Color.TEXT_ON_BRAND if selected else Color.TEXT_SECONDARY
            seg.content.weight = ft.FontWeight.W_700 if selected else ft.FontWeight.W_600


def card(content: ft.Control, padding: int = Space.XL) -> ft.Card:
    """Elevated white surface for grouping content."""
    return ft.Card(
        elevation=Elevation.CARD,
        bgcolor=Color.SURFACE,
        content=ft.Container(padding=padding, content=content),
    )
