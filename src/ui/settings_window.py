from __future__ import annotations

from dataclasses import dataclass

import flet as ft

from src.ui.theme import (
    Color, Radius, Space, Type, SegmentedSelect, body_text, heading, primary_button, text_field,
)

# TYPE options shown in the settings selector. Keys are the config values
# (1/2/3); labels mirror _TYPE_NAMES in main_window.py.
TYPE_OPTIONS = [
    ("1", "דיווח פעילות"),
    ("2", "מועמדים"),
    ("3", "נוכחות"),
]

# Note: the TYPE 3 compare/upsert sub-mode lives on the MAIN panel (main_window.py),
# not here — the operator picks it at run time so the write-vs-read choice is
# visible at the moment of action, with a confirm before an upsert.



@dataclass
class SettingsFields:
    user_name: ft.TextField
    password: ft.TextField
    secret_key: ft.TextField
    act_description: ft.TextField
    act_nu: ft.TextField
    url: ft.TextField
    type_value: SegmentedSelect
    dev_mode: ft.Switch
    ssh_mirror: ft.Switch
    ssh_remote: ft.TextField
    ssh_key_path: ft.TextField


def build_settings_view(
    initial_values: dict[str, str],
    on_save,
    update_section: ft.Control | None = None,
) -> tuple[ft.Container, SettingsFields]:

    def row(*cells: tuple[ft.Control, int]) -> ft.ResponsiveRow:
        return ft.ResponsiveRow(
            run_spacing=Space.MD,
            controls=[
                ft.Container(control, col={"xs": 12, "md": span}) for control, span in cells
            ],
        )

    # The process group is TYPE-aware: the activity number/description apply only
    # to TYPE 1 (דיווח פעילות), and the system URL only to TYPE 2/3 (TYPE 1 logs
    # in to a fixed home URL). Each shows only for its type; hidden values are
    # still persisted on save, so switching types never loses what was entered.
    init_type = initial_values.get("TYPE", "")
    url_field = text_field("URL", initial_values.get("URL", ""))
    act_nu_field = text_field("ACT_NU", initial_values.get("ACT_NU", ""))
    act_description_field = text_field("ACT_DESCRIPTION", initial_values.get("ACT_DESCRIPTION", ""))

    act_row = ft.Container(
        content=row((act_nu_field, 4), (act_description_field, 8)),
        visible=init_type == "1",
    )
    url_row = ft.Container(
        content=row((url_field, 12)),
        visible=init_type in ("2", "3"),
    )

    def _on_type_change(new_type: str) -> None:
        act_row.visible = new_type == "1"
        url_row.visible = new_type in ("2", "3")
        act_row.update()
        url_row.update()

    # --- Developer mode controls ---
    init_dev = initial_values.get("DEV_MODE", "") == "True"
    init_ssh = initial_values.get("SSH_MIRROR", "") == "True"

    ssh_remote_field = text_field("כתובת SSH", initial_values.get("SSH_REMOTE", ""))
    ssh_remote_field.hint_text = "user@host:/path"
    ssh_remote_field.rtl = False
    ssh_key_path_field = text_field("נתיב מפתח SSH", initial_values.get("SSH_KEY_PATH", ""))
    ssh_key_path_field.rtl = False

    ssh_fields = ft.Container(
        content=ft.Column(spacing=Space.MD, controls=[
            row((ssh_remote_field, 12)),
            row((ssh_key_path_field, 12)),
        ]),
        visible=init_ssh,
    )

    def _on_ssh_toggle(_e) -> None:
        ssh_fields.visible = ssh_mirror_switch.value
        ssh_fields.update()

    _switch_kw = dict(
        active_color=Color.BRAND, active_track_color=Color.BORDER,
        inactive_thumb_color=Color.TEXT_SECONDARY, inactive_track_color=Color.BORDER,
        label_text_style=ft.TextStyle(color=Color.TEXT_SECONDARY),
    )

    ssh_mirror_switch = ft.Switch(value=init_ssh, label="שיקוף לוג SSH", on_change=_on_ssh_toggle, **_switch_kw)
    dev_mode_switch = ft.Switch(value=init_dev, label="מצב מפתחים", **_switch_kw)

    fields = SettingsFields(
        user_name=text_field("USER_NAME", initial_values.get("USER_NAME", "")),
        password=text_field(
            "PASSWORD", initial_values.get("PASSWORD", ""), password=True, can_reveal_password=True
        ),
        secret_key=text_field(
            "SECRET_KEY", initial_values.get("SECRET_KEY", ""), password=True, can_reveal_password=True
        ),
        act_description=act_description_field,
        act_nu=act_nu_field,
        url=url_field,
        type_value=SegmentedSelect(
            "TYPE", TYPE_OPTIONS, init_type, on_change=_on_type_change
        ),
        dev_mode=dev_mode_switch,
        ssh_mirror=ssh_mirror_switch,
        ssh_remote=ssh_remote_field,
        ssh_key_path=ssh_key_path_field,
    )

    def accordion(title: str, *rows: ft.Control, expanded: bool = False) -> ft.ExpansionTile:
        # Collapsible section with an open/close button, so only the open
        # group takes vertical space and the dialog fits without scrolling.
        return ft.ExpansionTile(
            title=body_text(title, level=Type.TITLE, color=Color.TEXT_PRIMARY),
            expanded=expanded,
            maintain_state=True,
            bgcolor=ft.Colors.TRANSPARENT,
            collapsed_bgcolor=ft.Colors.TRANSPARENT,
            icon_color=Color.BRAND,
            collapsed_icon_color=Color.TEXT_SECONDARY,
            text_color=Color.TEXT_PRIMARY,
            collapsed_text_color=Color.TEXT_PRIMARY,
            shape=ft.RoundedRectangleBorder(radius=Radius.MD),
            collapsed_shape=ft.RoundedRectangleBorder(radius=Radius.MD),
            tile_padding=ft.padding.symmetric(horizontal=Space.SM),
            # Top padding gives the fields' floating labels room so they are not
            # clipped by the tile's content edge.
            controls_padding=ft.padding.only(left=Space.SM, right=Space.SM, top=Space.MD, bottom=Space.LG),
            controls=[ft.Column(spacing=Space.MD, controls=list(rows))],
        )

    ssh_mirror_row = ft.Row(controls=[ssh_mirror_switch], alignment=ft.MainAxisAlignment.START)

    advanced_section = ft.Container(
        content=accordion(
            "הגדרות מתקדמות",
            ssh_mirror_row,
            ssh_fields,
        ),
        visible=init_dev,
    )

    def _on_dev_toggle(_e) -> None:
        advanced_section.visible = dev_mode_switch.value
        advanced_section.update()

    dev_mode_switch.on_change = _on_dev_toggle

    fields_column = ft.Column(
        spacing=Space.SM,
        expand=True,
        scroll=ft.ScrollMode.AUTO,
        controls=[
            accordion(
                "הגדרות תהליך",
                row((fields.type_value.control, 12)),
                act_row,
                url_row,
                expanded=True,
            ),
            accordion(
                "פרטי התחברות",
                row((fields.user_name, 6), (fields.password, 6)),
                row((fields.secret_key, 12)),
            ),
            advanced_section,
            # "אודות ועדכונים" — installed version + update status/button. Built by
            # the controller (it owns the update channel/state); None in contexts
            # that don't pass it.
            *( [accordion("אודות ועדכונים", update_section)] if update_section is not None else [] ),
        ],
    )

    save_button = primary_button("שמור הגדרות", icon=ft.Icons.SAVE_OUTLINED)
    save_button.on_click = lambda _: on_save(fields)

    dev_footer = dev_mode_switch

    container = ft.Container(
        expand=True,
        bgcolor=None,  # transparent — the dialog itself provides the opaque surface
        border_radius=8,
        padding=Space.LG,
        content=ft.Column(
            spacing=Space.LG,
            controls=[
                heading("הגדרות משתמש"),
                ft.Divider(color=Color.BORDER),
                ft.Container(content=fields_column, expand=True),
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[dev_footer, save_button],
                ),
            ],
        ),
    )

    return container, fields
