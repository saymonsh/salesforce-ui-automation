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


def build_settings_view(
    initial_values: dict[str, str],
    on_save,
) -> tuple[ft.Container, SettingsFields]:
    
    def make_field(label: str, value: str, password: bool = False, can_reveal_password: bool = False):
        return ft.TextField(
            label=label,
            value=value,
            password=password,
            can_reveal_password=can_reveal_password,
            text_align=ft.TextAlign.RIGHT,
            border_radius=8,
            border_color="#828383",
            focused_border_color="#de2952",
            cursor_color="#de2952",
            bgcolor="#ffffff",
            color="#000000",
        )

    fields = SettingsFields(
        user_name=make_field("USER_NAME", initial_values.get("USER_NAME", "")),
        password=make_field("PASSWORD", initial_values.get("PASSWORD", ""), password=True, can_reveal_password=True),
        secret_key=make_field("SECRET_KEY", initial_values.get("SECRET_KEY", "")),
        act_description=make_field("ACT_DESCRIPTION", initial_values.get("ACT_DESCRIPTION", "")),
        act_nu=make_field("ACT_NU", initial_values.get("ACT_NU", "")),
        url=make_field("URL", initial_values.get("URL", "")),
        type_value=make_field("TYPE", initial_values.get("TYPE", "")),
        uploaded_file_path=make_field("UPLOADED_FILE_PATH", initial_values.get("UPLOADED_FILE_PATH", "")),
    )

    fields_column = ft.Column(
        spacing=15,
        expand=True,
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
            ft.Container(content=fields.url),
            ft.Container(content=fields.uploaded_file_path),
        ],
    )

    save_button = ft.FilledButton(
        "שמור הגדרות",
        icon=ft.Icons.SAVE_OUTLINED,
        style=ft.ButtonStyle(
            bgcolor="#de2952",
            color="#ffffff",
            shape=ft.RoundedRectangleBorder(radius=8),
            padding=20
        ),
        on_click=lambda _: on_save(fields),
    )
    
    header = ft.Text("הגדרות משתמש", size=24, weight=ft.FontWeight.W_700, color="#000000")
    
    container = ft.Container(
        expand=True,
        bgcolor="#ffffff",
        border_radius=8,
        padding=20,
        content=ft.Column(
            spacing=20,
            controls=[
                header,
                ft.Divider(color="#828383"),
                ft.Container(content=fields_column, expand=True),
                ft.Row(controls=[save_button], alignment=ft.MainAxisAlignment.END),
            ]
        )
    )

    return container, fields
