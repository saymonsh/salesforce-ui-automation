import flet as ft

class ProgressBar(ft.Container):
    def __init__(self, width=None):
        super().__init__()
        self.width_val = width
        
        self.progress_bar = ft.ProgressBar(
            value=0,
            width=self.width_val,
            color="#de2952",
            bgcolor="#e0e0e0",
            bar_height=14,
            border_radius=8
        )
        self.text = ft.Text(
            value="0%",
            text_align=ft.TextAlign.CENTER,
            size=14,
            weight=ft.FontWeight.BOLD,
            color="#000000"
        )
        
        self.content = ft.Column(
            controls=[
                self.text,
                self.progress_bar
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=5
        )

    def update_progress(self, value: float, text: str = None):
        """
        value: float between 0.0 and 1.0
        text: optional custom text to display
        """
        clamped_value = max(0.0, min(1.0, value))
        self.progress_bar.value = clamped_value
        
        if text is not None:
            self.text.value = text
        else:
            self.text.value = f"{int(clamped_value * 100)}%"
            
        self.update()

    def reset(self):
        self.progress_bar.value = 0.0
        self.text.value = "0%"
        self.update()
