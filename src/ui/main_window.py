import pyvisual as pv
from PySide6.QtCore import Qt
from src.core import constants as C
from src.ui.components.progress_bar import DynamicContrastProgressBar

# ============================================================================
# UI FACTORY HELPER FUNCTIONS
# ============================================================================

def _create_header_section(window):
    """Creates the header text and settings button."""
    ui = {}
    
    ui["Text_UserSetting"] = pv.PvText(
        container=window, x=148, y=40, width=204, height=45,
        bg_color=C.COLOR_WHITE_TRANSPARENT,
        text='הגדרת משתמשים', is_visible=True, text_alignment='center',
        paddings=(0, 0, 0, 0), font=C.FONT_OPENSANS, font_size=26,
        font_color=C.COLOR_WHITE, bold=True, italic=False, underline=False,
        strikethrough=False, opacity=1, border_color=None, corner_radius=0,
        tag=None
    )

    ui["Button_setting"] = pv.PvButton(
        container=window, x=385, y=37, width=53, height=50,
        text='', font=C.FONT_POPPINS, font_size=16,
        font_color=C.COLOR_WHITE, font_color_hover=None,
        bold=False, italic=False, underline=False, strikethrough=False,
        idle_color=C.COLOR_WHITE, hover_color=None, clicked_color=None,
        border_color=C.COLOR_BORDER_GRAY, border_hover_color=None, border_thickness=0,
        corner_radius=25, border_style="solid",
        box_shadow='1px 2px 4px 0px rgba(0,0,0,0.2)',
        box_shadow_hover='0px 2px 4px 5px rgba(0,0,0,0.2)',
        icon_path=C.ICON_SETTING, icon_position='right',
        icon_color=C.COLOR_BLUE_PRIMARY, icon_color_hover=None,
        icon_spacing=0, icon_scale=1.3, paddings=(0, 0, 0, 0),
        is_visible=True, is_disabled=False, opacity=1,
        on_hover=None, on_click=None, on_release=None, tag='setting'
    )
    
    ui["Text_Header"] = pv.PvText(
        container=window, x=148, y=71, width=204, height=45,
        bg_color=C.COLOR_WHITE_TRANSPARENT, text='salesforce', is_visible=True,
        text_alignment='center', paddings=(0, 0, 0, 0),
        font=C.FONT_POPPINS, font_size=26, font_color=C.COLOR_WHITE,
        bold=True, italic=False, underline=False, strikethrough=False,
        opacity=1, border_color=None, corner_radius=0, tag=None
    )
    
    return ui

def _create_upload_section(window):
    """Creates file upload dialog."""
    ui = {}
    ui["FileDialog_fileUpload"] = pv.PvFileDialog(
        container=window,
        x=170, y=257, width=160, height=50,
        text="upload", font_size=16, files_filter="Excel files (*.xlsx *.xls)",
        dialog_mode="open", on_file_selected=lambda file_path: print("Selected file:", file_path),
        enable_drag_drop=True, show_file_name=True,
        font=C.FONT_POPPINS, font_color=C.COLOR_BLUE_PRIMARY, bold=True,
        icon_path=C.ICON_UPLOAD, icon_position='left',
        icon_color=C.COLOR_BLUE_PRIMARY, icon_spacing=16, icon_scale=1.2,
        tag='file_upload', idle_color=C.COLOR_WHITE, clicked_color=None,
        border_color=C.COLOR_BLACK_BORDER, border_thickness=0, corner_radius=50,
        border_style="solid", box_shadow='1px 2px 4px 0px rgba(0,0,0,0.2)',
        box_shadow_hover='0px 2px 4px 5px rgba(0,0,0,0.2)'
    )
    return ui

def _create_action_section(window):
    """Creates the Run button, the Progress Bar, and the 'running' status text."""
    ui = {}

    ui["Rectangle"] = pv.PvRectangle(container=window, x=170, y=183, width=160,
        height=56, idle_color=(255, 255, 250, 1), border_color=C.COLOR_WHITE, border_thickness=4,
        corner_radius=10, border_style="solid", opacity=1, is_visible=False,
        on_hover=None, on_click=None, on_release=None, tag=None)
    
    ui["Button_run"] = pv.PvButton(
        container=window, x=170, y=180, width=160, height=50,
        text='run', font=C.FONT_POPPINS, font_size=16,
        font_color=C.COLOR_BLUE_PRIMARY, font_color_hover=None,
        bold=True, italic=False, underline=False, strikethrough=False,
        idle_color=(255, 251, 251, 1), hover_color=None, clicked_color=None,
        border_color=C.COLOR_BORDER_GRAY, border_hover_color=None, border_thickness=0,
        corner_radius=25, border_style="solid",
        box_shadow='1px 2px 4px 0px rgba(0,0,0,0.2)',
        box_shadow_hover='0px 2px 4px 5px rgba(0,0,0,0.2)',
        icon_path=C.ICON_RUN, icon_position='right',
        icon_color=C.COLOR_BLUE_PRIMARY, icon_color_hover=None,
        icon_spacing=36, icon_scale=1.2, paddings=(0, 0, 0, 0),
        is_visible=True, is_disabled=False, opacity=1,
        on_hover=None, on_click=None, on_release=None, tag='run'
    )

    ui["Button_stop"] = pv.PvButton(
        container=window, x=140, y=198, width=25, height=25, # Aligned with progress bar (y=215, h=25)
        text='', font=C.FONT_POPPINS, font_size=16,
        font_color=C.COLOR_WHITE, font_color_hover=None,
        bold=True, italic=False, underline=False, strikethrough=False,
        idle_color=C.COLOR_WHITE, hover_color=None, clicked_color=None,
        border_color=C.COLOR_BORDER_GRAY, border_hover_color=None, border_thickness=0,
        corner_radius=45, border_style="solid",
        box_shadow='1px 2px 4px 0px rgba(0,0,0,0.2)',
        box_shadow_hover='0px 2px 4px 5px rgba(0,0,0,0.5)',
        icon_path=C.ICON_STOP,
        icon_position="right",
        icon_color=C.COLOR_BLUE_BG, icon_color_hover=None, # Ensure icon is white
        icon_spacing=0, icon_scale=0.5, paddings=(0, 0, 0, 0),
        is_visible=False, is_disabled=False, opacity=1,
        on_hover=None, on_click=None, on_release=None, tag='stop'
    )

    # Use our custom class here
    ui["Progressbar"] = DynamicContrastProgressBar(
        container=window, x=170, y=215, width=160, height=25,
        min_value=0, max_value=100, value=0,
        track_color=C.COLOR_BLUE_BG, track_border_color=C.COLOR_WHITE,
        fill_color=C.COLOR_WHITE,
        track_corner_radius=7, opacity=1,
        idle_color=C.COLOR_WHITE_TRANSPARENT, track_border_thickness=4, scale=1,
        track_height=12, is_circular=False, border_thickness=0, suffix='',
        font=C.FONT_OPENSANS, font_size=15,
        font_color=C.COLOR_BLUE_BG, font_color_hover=None,
        bold=True, italic=False, underline=False, strikeout=False,
        is_visible=False, is_disabled=False,
        on_hover=None, on_click=None, on_release=None, tag='Progressbar'
    )

    ui["Text_running"] = pv.PvText(
        container=window, x=205, y=187.5, width=90, height=30,
        idle_color=C.COLOR_PURPLE_TRANSPARENT, text='Running',
        text_alignment='center', paddings=(0, 0, 0, 0),
        font=C.FONT_POPPINS, font_size=20, font_color=C.COLOR_BLUE_BG,
        bold=True, italic=False, underline=False, strikethrough=False,
        opacity=1, border_color=None, corner_radius=0,
        is_visible=False, on_hover=None, on_click=None, on_release=None, tag=None
    )

    return ui

def _create_status_section(window):
    """Creates the bottom status text."""
    ui = {}
    ui["Text_mainStatus"] = pv.PvText(
        container=window, x=139, y=315, width=222, height=34,
        bg_color=C.COLOR_PURPLE_TRANSPARENT, text="", is_visible=True,
        text_alignment='center', paddings=(0, 0, 0, 0),
        font=C.FONT_POPPINS, font_size=16, font_color=(254, 254, 254, 1),
        bold=True, italic=False, underline=False,
        strikethrough=False, opacity=1, border_color=None, corner_radius=0,
        tag='status'
    )
    return ui

# ============================================================================
# PUBLIC API
# ============================================================================

def create_window():
    """Initializes and returns the main application window."""
    window = pv.PvWindow(
        title="PyVisual Window",
        width=500,
        height=400,
        bg_color=C.COLOR_BLUE_BG,
        icon=None,
        bg_image=None,
        is_frameless=False,
        is_resizable=False
    )
    return window

def create_ui(window):
    """
    Constructs all UI elements and returns them in a single flat dictionary.
    Safe for external consumption by app.py.
    """
    ui = {}
    
    # Merge all separate sections into the main dictionary
    ui.update(_create_header_section(window))
    ui.update(_create_upload_section(window))
    ui.update(_create_action_section(window))
    ui.update(_create_status_section(window))
    
    return ui
