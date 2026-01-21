import pyvisual as pv
from PySide6.QtCore import Qt, QRect, QRectF
from PySide6.QtGui import QPainter, QColor, QRegion, QPainterPath, QPen

# ============================================================================
# CONSTANTS & CONFIGURATION
# ============================================================================

# --- Fonts ---
FONT_OPENSANS = 'assets/fonts/OpenSans/OpenSans.ttf'
FONT_POPPINS = 'assets/fonts/Poppins/Poppins.ttf'

# --- Colors ---
COLOR_WHITE             = (255, 255, 255, 1)
COLOR_WHITE_TRANSPARENT = (255, 255, 255, 0)
COLOR_BLUE_PRIMARY      = (107, 159, 226, 1)
COLOR_BLUE_BG           = (80, 160, 225, 1)
COLOR_BORDER_GRAY       = (100, 100, 100, 1)
COLOR_PURPLE_TRANSPARENT= (124, 53, 163, 0)
COLOR_BLACK_BORDER      = (0, 0, 0, 1)

# --- Icons ---
ICON_SETTING = 'assets/icons/icon_1.svg'
ICON_UPLOAD  = 'assets/icons/icon_2.svg'
ICON_RUN     = 'assets/icons/icon_4.svg'

# ============================================================================
# CUSTOM WIDGETS
# ============================================================================

class DynamicContrastProgressBar(pv.PvProgressBar):
    """
    A custom ProgressBar that ensures text readability by rendering the text 
    in two passes (over track vs over fill) with high contrast colors.
    It overrides default painting to ensure pixel-perfect rendering without artifacts.
    """
    
    def configure_style(self):
        super().configure_style()
        # Disable default text drawing by the parent class to avoid duplication/overlapping
        self.setTextVisible(False)

    def paintEvent(self, event):
        # Full Custom Painting to ensure visual correctness and eliminate library artifacts.
        # We prevents super().paintEvent(event) because the library's stylesheet logic
        # causes background bleeding when height != track_height.

        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.Antialiasing)

            # --- 1. Setup ---
            if hasattr(self, '_qfont'):
                painter.setFont(self._qfont)

            rect = self.rect()
            w, h = rect.width(), rect.height()
            
            # Helper for color conversion
            def to_qcolor(c_tuple):
                return QColor(c_tuple[0], c_tuple[1], c_tuple[2], int(c_tuple[3]*255))

            track_color = to_qcolor(self._track_color)
            fill_color = to_qcolor(self._fill_color)
            border_color = to_qcolor(self._track_border_color)
            
            # Text Colors: High contrast logic
            # Font color passed in init is used for the "Filled" part (White background -> Blue text)
            font_color_on_fill = to_qcolor(self._font_color) 
            # We hardcode White for the "Track" part (Blue background -> White text)
            font_color_on_track = QColor(255, 255, 255)

            # Dimensions
            border_thickness = self._track_border_thickness
            corner_radius = self._track_corner_radius
            
            # Value Calculation
            val = self.value
            mn = self.min_value
            mx = self.max_value
            if mx == mn:
                ratio = 0.0
            else:
                ratio = max(0.0, min(1.0, (val - mn) / (mx - mn)))

            # --- 2. Geometry & Track ---
            # Deflate rect by half border thickness for centered stroke drawing
            adj = border_thickness / 2.0
            track_rect_f = QRectF(rect).adjusted(adj, adj, -adj, -adj)
            
            track_path = QPainterPath()
            track_path.addRoundedRect(track_rect_f, corner_radius, corner_radius)

            # Draw Track Background
            painter.setPen(Qt.NoPen)
            painter.setBrush(track_color)
            painter.drawPath(track_path)

            # --- 3. Draw Chunk (Fill) ---
            painter.save()
            # Clip to track path to ensure fill renders strictly inside rounded corners
            painter.setClipPath(track_path)

            chunk_width = w * ratio
            chunk_rect_f = QRectF(0, 0, chunk_width, h)
            
            painter.setBrush(fill_color)
            painter.setPen(Qt.NoPen)
            painter.drawRect(chunk_rect_f)
            
            painter.restore()

            # --- 4. Draw Border ---
            if border_thickness > 0:
                pen = QPen(border_color)
                pen.setWidth(border_thickness)
                painter.setBrush(Qt.NoBrush)
                painter.setPen(pen)
                painter.drawPath(track_path)

            # --- 5. Draw Text (Dynamic Contrast) ---
            text_str = f"{int(val)}%" 
            if self._suffix:
                text_str += self._suffix

            # Create Regions for text clipping
            # We use the calculated chunk width to define the "Filled Region" vs "Track Region"
            chunk_rect_int = QRect(0, 0, int(chunk_width), h)
            
            whole_widget_region = QRegion(rect)
            chunk_region = QRegion(chunk_rect_int)
            track_region = whole_widget_region.subtracted(chunk_region)
            
            # Pass 1: Draw White Text on Blue Track
            painter.setPen(font_color_on_track)
            painter.setClipRegion(track_region)
            painter.drawText(rect, Qt.AlignCenter, text_str)
            
            # Pass 2: Draw Blue Text on White Fill
            painter.setPen(font_color_on_fill)
            painter.setClipRegion(chunk_region)
            painter.drawText(rect, Qt.AlignCenter, text_str)

        finally:
            painter.end()

# ============================================================================
# UI FACTORY HELPER FUNCTIONS
# ============================================================================

def _create_header_section(window):
    """Creates the header text and settings button."""
    ui = {}
    
    ui["Text_UserSetting"] = pv.PvText(
        container=window, x=148, y=40, width=204, height=45,
        bg_color=COLOR_WHITE_TRANSPARENT,
        text='הגדרת משתמשים', is_visible=True, text_alignment='center',
        paddings=(0, 0, 0, 0), font=FONT_OPENSANS, font_size=26,
        font_color=COLOR_WHITE, bold=True, italic=False, underline=False,
        strikethrough=False, opacity=1, border_color=None, corner_radius=0,
        tag=None
    )

    ui["Button_setting"] = pv.PvButton(
        container=window, x=385, y=37, width=53, height=50,
        text='', font=FONT_POPPINS, font_size=16,
        font_color=COLOR_WHITE, font_color_hover=None,
        bold=False, italic=False, underline=False, strikethrough=False,
        idle_color=COLOR_WHITE, hover_color=None, clicked_color=None,
        border_color=COLOR_BORDER_GRAY, border_hover_color=None, border_thickness=0,
        corner_radius=25, border_style="solid",
        box_shadow='1px 2px 4px 0px rgba(0,0,0,0.2)',
        box_shadow_hover='0px 2px 4px 5px rgba(0,0,0,0.2)',
        icon_path=ICON_SETTING, icon_position='right',
        icon_color=COLOR_BLUE_PRIMARY, icon_color_hover=None,
        icon_spacing=0, icon_scale=1.3, paddings=(0, 0, 0, 0),
        is_visible=True, is_disabled=False, opacity=1,
        on_hover=None, on_click=None, on_release=None, tag='setting'
    )
    
    ui["Text_Header"] = pv.PvText(
        container=window, x=148, y=71, width=204, height=45,
        bg_color=COLOR_WHITE_TRANSPARENT, text='salesforce', is_visible=True,
        text_alignment='center', paddings=(0, 0, 0, 0),
        font=FONT_POPPINS, font_size=26, font_color=COLOR_WHITE,
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
        font=FONT_POPPINS, font_color=COLOR_BLUE_PRIMARY, bold=True,
        icon_path=ICON_UPLOAD, icon_position='left',
        icon_color=COLOR_BLUE_PRIMARY, icon_spacing=16, icon_scale=1.2,
        tag='file_upload', idle_color=COLOR_WHITE, clicked_color=None,
        border_color=COLOR_BLACK_BORDER, border_thickness=0, corner_radius=50,
        border_style="solid", box_shadow='1px 2px 4px 0px rgba(0,0,0,0.2)',
        box_shadow_hover='0px 2px 4px 5px rgba(0,0,0,0.2)'
    )
    return ui

def _create_action_section(window):
    """Creates the Run button, the Progress Bar, and the 'running' status text."""
    ui = {}
    
    ui["Button_run"] = pv.PvButton(
        container=window, x=170, y=180, width=160, height=50,
        text='run', font=FONT_POPPINS, font_size=16,
        font_color=COLOR_BLUE_PRIMARY, font_color_hover=None,
        bold=True, italic=False, underline=False, strikethrough=False,
        idle_color=(255, 251, 251, 1), hover_color=None, clicked_color=None,
        border_color=COLOR_BORDER_GRAY, border_hover_color=None, border_thickness=0,
        corner_radius=25, border_style="solid",
        box_shadow='1px 2px 4px 0px rgba(0,0,0,0.2)',
        box_shadow_hover='0px 2px 4px 5px rgba(0,0,0,0.2)',
        icon_path=ICON_RUN, icon_position='right',
        icon_color=COLOR_BLUE_PRIMARY, icon_color_hover=None,
        icon_spacing=36, icon_scale=1.2, paddings=(0, 0, 0, 0),
        is_visible=True, is_disabled=False, opacity=1,
        on_hover=None, on_click=None, on_release=None, tag='run'
    )

    # Use our custom class here
    ui["Progressbar"] = DynamicContrastProgressBar(
        container=window, x=170, y=215, width=160, height=25,
        min_value=0, max_value=100, value=0,
        track_color=COLOR_BLUE_BG, track_border_color=COLOR_WHITE,
        fill_color=COLOR_WHITE,
        track_corner_radius=4, opacity=1,
        idle_color=COLOR_WHITE_TRANSPARENT, track_border_thickness=4, scale=1,
        track_height=12, is_circular=False, border_thickness=0, suffix='',
        font=FONT_OPENSANS, font_size=15,
        font_color=COLOR_BLUE_BG, font_color_hover=None,
        bold=True, italic=False, underline=False, strikeout=False,
        is_visible=False, is_disabled=False,
        on_hover=None, on_click=None, on_release=None, tag='Progressbar'
    )

    ui["Text_running"] = pv.PvText(
        container=window, x=211, y=185, width=85, height=25,
        idle_color=COLOR_PURPLE_TRANSPARENT, text='running',
        text_alignment='center', paddings=(0, 0, 0, 0),
        font=FONT_POPPINS, font_size=20, font_color=COLOR_WHITE,
        bold=True, italic=False, underline=False, strikethrough=False,
        opacity=1, border_color=None, corner_radius=0,
        is_visible=False, on_hover=None, on_click=None, on_release=None, tag=None
    )
    
    return ui

def _create_status_section(window):
    """Creates the bottom status text."""
    ui = {}
    ui["Text_uploadStatus"] = pv.PvText(
        container=window, x=139, y=315, width=222, height=34,
        bg_color=COLOR_PURPLE_TRANSPARENT, text="", is_visible=True,
        text_alignment='center', paddings=(0, 0, 0, 0),
        font=FONT_POPPINS, font_size=16, font_color=(254, 254, 254, 1),
        bold=False, italic=False, underline=False,
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
        bg_color=COLOR_BLUE_BG,
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