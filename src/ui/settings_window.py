from __future__ import annotations

from dataclasses import dataclass

import flet as ft


@dataclass
class SettingsFields:
    user_name: ft.TextField
    password: ft.TextField
    secret_key: ft.TextField
    act_description: ft.TextField
    act_nu: ft.TextField
    url: ft.TextField
    type_value: ft.TextField
    uploaded_file_path: ft.TextField


def build_settings_dialog(
    page: ft.Page,
    initial_values: dict[str, str],
    on_save,
) -> tuple[ft.AlertDialog, SettingsFields]:
    fields = SettingsFields(
        user_name=ft.TextField(label="USER_NAME", value=initial_values.get("USER_NAME", ""), text_align=ft.TextAlign.RIGHT),
        password=ft.TextField(
            label="PASSWORD",
            value=initial_values.get("PASSWORD", ""),
            password=True,
            can_reveal_password=True,
            text_align=ft.TextAlign.RIGHT,
        ),
        secret_key=ft.TextField(label="SECRET_KEY", value=initial_values.get("SECRET_KEY", ""), text_align=ft.TextAlign.RIGHT),
        act_description=ft.TextField(
            label="ACT_DESCRIPTION",
            value=initial_values.get("ACT_DESCRIPTION", ""),
            text_align=ft.TextAlign.RIGHT,
        ),
        act_nu=ft.TextField(label="ACT_NU", value=initial_values.get("ACT_NU", ""), text_align=ft.TextAlign.RIGHT),
        url=ft.TextField(label="URL", value=initial_values.get("URL", ""), text_align=ft.TextAlign.RIGHT),
        type_value=ft.TextField(label="TYPE", value=initial_values.get("TYPE", ""), text_align=ft.TextAlign.RIGHT),
        uploaded_file_path=ft.TextField(
            label="UPLOADED_FILE_PATH",
            value=initial_values.get("UPLOADED_FILE_PATH", ""),
            text_align=ft.TextAlign.RIGHT,
        ),
    )

    fields_column = ft.Column(
        spacing=14,
        scroll=ft.ScrollMode.AUTO,
        controls=[
            ft.ResponsiveRow(
                controls=[
                    ft.Container(fields.user_name, col={"xs": 12, "md": 6}),
                    ft.Container(fields.password, col={"xs": 12, "md": 6}),
                ]
            ),
            ft.ResponsiveRow(
                controls=[
                    ft.Container(fields.secret_key, col={"xs": 12, "md": 6}),
                    ft.Container(fields.type_value, col={"xs": 12, "md": 6}),
                ]
            ),
            ft.ResponsiveRow(
                controls=[
                    ft.Container(fields.act_nu, col={"xs": 12, "md": 4}),
                    ft.Container(fields.act_description, col={"xs": 12, "md": 8}),
                ]
            ),
            fields.url,
            fields.uploaded_file_path,
        ],
    )

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("הגדרות משתמש"),
        content=ft.Container(width=760, content=fields_column),
        actions=[
            ft.TextButton("ביטול", on_click=lambda _: _close_dialog(page, dialog)),
            ft.ElevatedButton("שמור", icon=ft.Icons.SAVE_OUTLINED, on_click=lambda _: on_save(fields, dialog)),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )

    return dialog, fields


def _close_dialog(page: ft.Page, dialog: ft.AlertDialog) -> None:
    dialog.open = False
    page.pop_dialog()
    page.update()
