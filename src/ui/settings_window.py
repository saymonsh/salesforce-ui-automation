import pyvisual as pv
from src.core import constants as C

def create_window():
    window = pv.PvWindow(
        title="PyVisual Window",
        width=400,
        height=360,
        bg_color=(255, 255, 255, 1),
        icon=None,
        bg_image=None,
        is_frameless=False,
        is_resizable=False
    )
    return window


def create_ui(window):
    ui = {}
    ui["PARAMETERS"] = pv.PvRectangle(container=window, x=0, y=0, width=400,
        height=360, idle_color=(80, 160, 225, 1), border_color=(255, 255, 255, 1), border_thickness=2,
        corner_radius=10, border_style="solid", opacity=1, is_visible=True,
        tag='PARAMETERS')

    ui["PASSWORD"] = pv.PvTextInput(container=window, x=208, y=19, width=171,
        height=40, background_color=(255, 255, 255, 1), is_visible=True, placeholder='PASSWORD',
        text_alignment='left', default_text='', paddings=(12, 0, 20, 0), font=C.FONT_POPPINS,
        font_size=10, font_color=(0, 0, 0, 1), border_color=(0, 0, 0, 1), border_thickness=0,
        border_style="solid", corner_radius=6, box_shadow='1px 2px 4px 0px rgba(0,0,0,0.2)', icon_path=None,
        icon_scale=1, icon_position='left', icon_spacing=10, icon_color='none',
        text_type='text', tag='PASSWORD')

    ui["USER_NAME"] = pv.PvTextInput(container=window, x=18, y=19, width=174,
        height=40, background_color=(255, 255, 255, 1), is_visible=True, placeholder='USER_NAME',
        text_alignment='left', default_text='', paddings=(12, 0, 20, 0), font=C.FONT_POPPINS,
        font_size=10, font_color=(0, 0, 0, 1), border_color=(0, 0, 0, 1), border_thickness=0,
        border_style="solid", corner_radius=6, box_shadow='1px 2px 4px 0px rgba(0,0,0,0.2)', icon_path=None,
        icon_scale=1, icon_position='left', icon_spacing=10, icon_color='none',
        text_type='text', tag='USER_NAME')

    ui["SECRET_KEY"] = pv.PvTextInput(container=window, x=18, y=73, width=174,
        height=40, background_color=(255, 255, 255, 1), is_visible=True, placeholder='SECRET_KEY',
        text_alignment='left', default_text='', paddings=(12, 0, 20, 0), font=C.FONT_POPPINS,
        font_size=10, font_color=(0, 0, 0, 1), border_color=(0, 0, 0, 1), border_thickness=0,
        border_style="solid", corner_radius=6, box_shadow='1px 2px 4px 0px rgba(0,0,0,0.2)', icon_path=None,
        icon_scale=1, icon_position='left', icon_spacing=10, icon_color='none',
        text_type='text', tag='SECRET_KEY')

    ui["URL"] = pv.PvTextInput(container=window, x=18, y=178, width=361,
        height=40, background_color=(253, 255, 255, 1), is_visible=True, placeholder='Enter URL',
        text_alignment='left', default_text='', paddings=(10, 0, 3, 0), font=C.FONT_POPPINS,
        font_size=10, font_color=(2, 4, 6, 1), border_color=(0, 0, 0, 1), border_thickness=0,
        border_style="solid", corner_radius=5, box_shadow='1px 2px 4px 0px rgba(0,0,0,0.2)', icon_path=C.ICON_RUN, # Using icon 4 as per original logic which seemed to use icon 4 
        icon_scale=0.4, icon_position='right', icon_spacing=10, icon_color=(107, 159, 226, 1),
        text_type='text', tag='URL')

    ui["ACT_NU"] = pv.PvTextInput(container=window, x=18, y=125, width=76,
        height=40, background_color=(255, 255, 255, 1), is_visible=True, placeholder='ACT_NU',
        text_alignment='left', default_text='', paddings=(12, 0, 20, 0), font=C.FONT_POPPINS,
        font_size=10, font_color=(0, 0, 0, 1), border_color=(0, 0, 0, 1), border_thickness=0,
        border_style="solid", corner_radius=6, box_shadow='1px 2px 4px 0px rgba(0,0,0,0.2)', icon_path=None,
        icon_scale=1, icon_position='left', icon_spacing=10, icon_color='none',
        text_type='text', tag='ACT_NU')

    ui["ACT_description"] = pv.PvTextInput(container=window, x=112, y=125, width=267,
        height=40, background_color=(255, 255, 255, 1), is_visible=True, placeholder='ACT_NU',
        text_alignment='left', default_text='', paddings=(12, 0, 20, 0), font=C.FONT_POPPINS,
        font_size=10, font_color=(0, 0, 0, 1), border_color=(0, 0, 0, 1), border_thickness=0,
        border_style="solid", corner_radius=6, box_shadow='1px 2px 4px 0px rgba(0,0,0,0.2)', icon_path=None,
        icon_scale=1, icon_position='left', icon_spacing=10, icon_color='none',
        text_type='text', tag='ACT_description')

    ui["TYPE"] = pv.PvTextInput(container=window, x=208, y=73, width=171,
        height=40, background_color=(255, 255, 255, 1), is_visible=True, placeholder='TYPE',
        text_alignment='left', default_text='', paddings=(12, 0, 20, 0), font=C.FONT_POPPINS,
        font_size=10, font_color=(0, 0, 0, 1), border_color=(0, 0, 0, 1), border_thickness=0,
        border_style="solid", corner_radius=6, box_shadow='1px 2px 4px 0px rgba(0,0,0,0.2)', icon_path=None,
        icon_scale=1, icon_position='left', icon_spacing=10, icon_color='none',
        text_type='text', tag='TYPE')

    ui["UPLOADED_FILE_PATH"] = pv.PvTextInput(container=window, x=18, y=230, width=361,
        height=40, background_color=(253, 255, 255, 1), is_visible=True, placeholder='UPLOADED_FILE_PATH',
        text_alignment='left', default_text='', paddings=(10, 0, 3, 0), font=C.FONT_POPPINS,
        font_size=10, font_color=(2, 4, 6, 1), border_color=(0, 0, 0, 1), border_thickness=0,
        border_style="solid", corner_radius=5, box_shadow='1px 2px 4px 0px rgba(0,0,0,0.2)', icon_path=None,
        icon_scale=0.4, icon_position='right', icon_spacing=10, icon_color=(107, 159, 226, 1),
        text_type='text', tag='UPLOADED_FILE_PATH')

    ui["SAVE"] = pv.PvButton(container=window, x=140, y=290, width=120,
        height=50, text='SAVE', font=C.FONT_POPPINS, font_size=16,
        font_color=(107, 159, 226, 1), font_color_hover=None, bold=True, italic=False,
        underline=False, strikethrough=False, idle_color=(255, 255, 255, 1), hover_color=None,
        clicked_color=None, border_color=(100, 100, 100, 1), border_hover_color=None, border_thickness=0,
        corner_radius=19, border_style="solid", box_shadow='1px 2px 4px 0px rgba(0,0,0,0.2)', box_shadow_hover='0px 2px 4px 5px rgba(0,0,0,0.2)',
        icon_path=C.ICON_SAVE, icon_position='left', icon_color=(107, 159, 226, 1), icon_color_hover=None,
        icon_spacing=14, icon_scale=1, paddings=(0, 0, 0, 0), is_visible=True,
        is_disabled=False, opacity=1, on_hover=None, on_click=None,
        on_release=None, tag='SAVE')
    
    # Note: I missed icon_8.svg in constants. Checking file system later if needed.

    return ui
