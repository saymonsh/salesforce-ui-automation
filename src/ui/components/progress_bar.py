import pyvisual as pv
from PySide6.QtCore import Qt, QRect, QRectF
from PySide6.QtGui import QPainter, QColor, QRegion, QPainterPath, QPen

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
