import flet as ft

from src.ui.theme import Color


HELP_ROWS = [
    ("1", "חיפוש + יצירת שירות 8 ו-ACT_NU + דיווח שירות", "הכנת תוכנית אישית מלאה וסגירת מטלה."),
    ("2", "חיפוש + יצירת שירות 8 ו-ACT_NU (מתוכנן)", "תכנון כפול ללא דיווח ביצוע."),
    ("3", "חיפוש + דיווח שירות על שורה 8", "עדכון ביצוע בלבד לשירות קיים."),
    ("4", "חיפוש + יצירת ACT_NU + דיווח שירות 8", "שילוב יצירת שירות חדש ודיווח סיום."),
    ("5", "חיפוש + יצירת ACT_NU (מתוכנן)", "הקמת שירות מוגדר בלבד."),
    ("6", "חיפוש + דיווח שירות על ACT_NU", "סגירת שירות ספציפי (ACT_NU)."),
]


def create_help_dialog(page: ft.Page) -> ft.AlertDialog:
    table = ft.DataTable(
        bgcolor=Color.SURFACE,
        heading_row_color=Color.BRAND_TINT,
        border=ft.border.all(1, Color.BORDER),
        horizontal_lines=ft.border.BorderSide(1, Color.BORDER),
        vertical_lines=ft.border.BorderSide(1, Color.BORDER),
        column_spacing=16,
        columns=[
            ft.DataColumn(ft.Text("סוג", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("פעולות", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("משמעות עסקית", weight=ft.FontWeight.BOLD)),
        ],
        rows=[
            ft.DataRow(
                cells=[
                    ft.DataCell(ft.Text(type_value, weight=ft.FontWeight.BOLD)),
                    ft.DataCell(ft.Text(action)),
                    ft.DataCell(ft.Text(meaning)),
                ]
            )
            for type_value, action, meaning in HELP_ROWS
        ],
    )

    dialog = ft.AlertDialog(
        modal=True,
        rtl=True,  # lay out the whole dialog (incl. title) right-to-left
        bgcolor=Color.SURFACE,
        shape=ft.RoundedRectangleBorder(radius=12),
        title=ft.Text("מדריך סוגי פעולות - Salesforce Automation"),
        content=ft.Container(
            width=780,
            rtl=True,  # the whole info dialog lays out right-to-left
            content=ft.Column(
                tight=True,
                scroll=ft.ScrollMode.AUTO,
                controls=[
                    ft.Text("האוטומציה פועלת בהתאם לערך המספרי בעמודה 'סוג' בקובץ ה-Excel:"),
                    table,
                    ft.Container(
                        margin=ft.margin.only(top=10),
                        padding=12,
                        border=ft.border.all(1, Color.BORDER),
                        border_radius=10,
                        bgcolor=Color.BRAND_TINT,
                        content=ft.Text(
                            "שימו לב:\n• שורה 8 = 'הכנת תוכנית אישית'.\n• ACT_NU = מספר השורה המוגדר בהגדרות המשתמש."
                        ),
                    ),
                ],
            ),
        ),
        actions=[
            ft.TextButton("סגור", on_click=lambda _: _close_dialog(page, dialog)),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    return dialog


def _close_dialog(page: ft.Page, dialog: ft.AlertDialog) -> None:
    dialog.open = False
    page.pop_dialog()
    page.update()
