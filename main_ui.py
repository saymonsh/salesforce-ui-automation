import pyvisual as pv

def create_window():
    window = pv.PvWindow(
        title="PyVisual Window",
        width=500,
        height=400,
        bg_color=(80, 160, 225, 1),
        icon=None,
        bg_image=None,
        is_frameless=False,
        is_resizable=False
    )
    return window

def create_ui(window):
    ui = {}
    ui["Text_UserSetting"] = pv.PvText(container=window, x=148, y=40, width=204,
        height=45, bg_color=(255, 255, 255, 0), text='הגדרת משתמשים', is_visible=True,
        text_alignment='center', paddings=(0, 0, 0, 0), font='assets/fonts/OpenSans/OpenSans.ttf', font_size=26,
        font_color=(255, 255, 255, 1), bold=True, italic=False, underline=False,
        strikethrough=False, opacity=1, border_color=None, corner_radius=0,
        tag=None)

    ui["Button_setting"] = pv.PvButton(container=window, x=385, y=37, width=53,
        height=50, text='', font='assets/fonts/Poppins/Poppins.ttf', font_size=16,
        font_color=(255, 255, 255, 1), font_color_hover=None, bold=False, italic=False,
        underline=False, strikethrough=False, idle_color=(255, 255, 255, 1), hover_color=None,
        clicked_color=None, border_color=(100, 100, 100, 1), border_hover_color=None, border_thickness=0,
        corner_radius=25, border_style="solid", box_shadow='1px 2px 4px 0px rgba(0,0,0,0.2)', box_shadow_hover='0px 2px 4px 5px rgba(0,0,0,0.2)',
        icon_path='assets/icons/icon_1.svg', icon_position='right', icon_color=(107, 159, 226, 1), icon_color_hover=None,
        icon_spacing=0, icon_scale=1.3, paddings=(0, 0, 0, 0), is_visible=True,
        is_disabled=False, opacity=1, on_hover=None, on_click=None,
        on_release=None, tag='setting')

    ui["FileDialog_fileUpload"] = pv.PvFileDialog(
        container=window,
        x=170, y=257, width=160, height=50, text="upload", font_size=16, files_filter="Excel files (*.xlsx *.xls)",
        dialog_mode="open", on_file_selected=lambda file_path: print("Selected file:", file_path), enable_drag_drop=True,
        show_file_name=True, font='assets/fonts/Poppins/Poppins.ttf', font_color=(107, 159, 226, 1), bold=True,
        icon_path='assets/icons/icon_2.svg', icon_position='left', icon_color=(107, 159, 226, 1),
        icon_spacing=16, icon_scale=1.2, tag='file_upload', idle_color=(255, 255, 255, 1),
        clicked_color=None, border_color=(0, 0, 0, 1), border_thickness=0, corner_radius=50,
        border_style="solid", box_shadow='1px 2px 4px 0px rgba(0,0,0,0.2)',
        box_shadow_hover='0px 2px 4px 5px rgba(0,0,0,0.2)'
    )

    ui["Text_Header"] = pv.PvText(container=window, x=148, y=71, width=204,
        height=45, bg_color=(255, 255, 255, 0), text='salesforce', is_visible=True,
        text_alignment='center', paddings=(0, 0, 0, 0), font='assets/fonts/Poppins/Poppins.ttf', font_size=26,
        font_color=(255, 255, 255, 1), bold=True, italic=False, underline=False,
        strikethrough=False, opacity=1, border_color=None, corner_radius=0,
        tag=None)

    ui["Button_run"] = pv.PvButton(container=window, x=170, y=180, width=160,
        height=50, text='run', font='assets/fonts/Poppins/Poppins.ttf', font_size=16,
        font_color=(107, 159, 226, 1), font_color_hover=None, bold=True, italic=False,
        underline=False, strikethrough=False, idle_color=(255, 251, 251, 1), hover_color=None,
        clicked_color=None, border_color=(100, 100, 100, 1), border_hover_color=None, border_thickness=0,
        corner_radius=25, border_style="solid", box_shadow='1px 2px 4px 0px rgba(0,0,0,0.2)', box_shadow_hover='0px 2px 4px 5px rgba(0,0,0,0.2)',
        icon_path='assets/icons/icon_4.svg', icon_position='right', icon_color=(107, 159, 226, 1), icon_color_hover=None,
        icon_spacing=36, icon_scale=1.2, paddings=(0, 0, 0, 0), is_visible=True,
        is_disabled=False, opacity=1, on_hover=None, on_click=None,
        on_release=None, tag='run')

    ui["Progressbar"] = pv.PvProgressBar(container=window, x=170, y=215, width=160,
        height=25, min_value=0, max_value=100, value=0,
        track_color=(80, 160, 225, 1), track_border_color=(255, 255, 255, 1), fill_color=(255, 255, 255, 1),
        track_corner_radius=4,
        opacity=1, idle_color=(255, 255, 255, 0), track_border_thickness=4, scale=1,
        track_height=12, is_circular=False, border_thickness=0, suffix='%',
        font='assets/fonts/OpenSans/OpenSans.ttf', font_size=15, font_color=(80, 160, 225, 1), font_color_hover=None,
        bold=True, italic=False, underline=False, strikeout=False,
        is_visible=False, is_disabled=False, on_hover=None, on_click=None,
        on_release=None, tag='Progressbar')

    ui["Text_uploadStatus"] = pv.PvText(container=window, x=139, y=315, width=222,
        height=34, bg_color=(124, 53, 163, 0), text="", is_visible=True,
        text_alignment='center', paddings=(0, 0, 0, 0), font='assets/fonts/Poppins/Poppins.ttf', font_size=16,
        font_color=(254, 254, 254, 1), bold=False, italic=False, underline=False,
        strikethrough=False, opacity=1, border_color=None, corner_radius=0,
        tag='status')

    ui["Text_running"] = pv.PvText(container=window, x=211, y=185, width=85,
        height=25, idle_color=(124, 53, 163, 0), text='running',
        text_alignment='center', paddings=(0, 0, 0, 0), font='assets/fonts/Poppins/Poppins.ttf', font_size=20,
        font_color=(255, 255, 255, 1), bold=True, italic=False, underline=False,
        strikethrough=False, opacity=1, border_color=None, corner_radius=0,
        is_visible=False, on_hover=None, on_click=None, on_release=None, tag=None)

    return ui