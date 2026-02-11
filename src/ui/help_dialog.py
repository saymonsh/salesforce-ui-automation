from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, 
                               QTableWidgetItem, QPushButton, QHeaderView, QLabel)
from PySide6.QtCore import Qt

class HelpDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("מדריך סוגי פעולות - Salesforce Automation")
        self.resize(700, 500)
        self.setStyleSheet("background-color: white;")
        self.setLayoutDirection(Qt.RightToLeft)  
        
        # Main Layout
        layout = QVBoxLayout(self)
        
        # Title
        title_label = QLabel("מדריך סוגי פעולות (Action Types)")
        # Make title slightly larger and bold
        font = title_label.font()
        font.setPointSize(14)
        font.setBold(True)
        title_label.setFont(font)
        title_label.setStyleSheet("color: #2c3e50; border-bottom: 2px solid #2C3E57; padding-bottom: 10px;")
        layout.addWidget(title_label)
        
        # Description
        desc_label = QLabel("האוטומציה פועלת בהתאם לערך המספרי בעמודה 'סוג' בקובץ ה-Excel:")
        desc_label.setStyleSheet("margin: 10px 0;")
        layout.addWidget(desc_label)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["סוג", "פעולות", "משמעות עסקית"])
        self.table.setLayoutDirection(Qt.RightToLeft)
        self.table.setFocusPolicy(Qt.NoFocus)
        
        # Data
        data = [
            ("1", "חיפוש + יצירת שירות 8 ו-ACT_NU + דיווח שירות", "הכנת תוכנית אישית מלאה וסגירת מטלה."),
            ("2", "חיפוש + יצירת שירות 8 ו-ACT_NU (מתוכנן)", "תכנון כפול ללא דיווח ביצוע."),
            ("3", "חיפוש + דיווח שירות על שורה 8", "עדכון ביצוע בלבד לשירות קיים."),
            ("4", "חיפוש + יצירת ACT_NU + דיווח שירות 8", "שילוב יצירת שירות חדש ודיווח סיום."),
            ("5", "חיפוש + יצירת ACT_NU (מתוכנן)", "הקמת שירות מוגדר בלבד."),
            ("6", "חיפוש + דיווח שירות על ACT_NU", "סגירת שירות ספציפי (ACT_NU).")
        ]
        
        self.table.setRowCount(len(data))
        
        for row, (type_val, action, meaning) in enumerate(data):
            # Type (Center Aligned, Bold)
            type_item = QTableWidgetItem(type_val)
            type_item.setTextAlignment(Qt.AlignCenter)
            type_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable) # Read-only
            font_bold = type_item.font()
            font_bold.setBold(True)
            type_item.setFont(font_bold)
            self.table.setItem(row, 0, type_item)
            
            # Action
            action_item = QTableWidgetItem(action)
            action_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.table.setItem(row, 1, action_item)
            
            # Meaning
            meaning_item = QTableWidgetItem(meaning)
            meaning_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.table.setItem(row, 2, meaning_item)

        # Table Styling and Headers
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        # RTL support for header text alignment if needed (Qt usually handles it with layout direction)
        
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: white;
                alternate-background-color: #f9f9f9;
                gridline-color: #d0d0d0;
                selection-background-color: transparent; /* מונע צבע רקע כחול בבחירה */
                selection-color: black; /* שומר על טקסט שחור בבחירה */
            }
            QTableWidget::item:hover {
                background-color: transparent; /* מונע צבע רקע בריחוף עכבר */
            }
            QTableWidget::item:selected {
                background-color: transparent; /* מבטיח שגם אם התא נבחר, הוא יישאר שקוף */
                color: black;
            }
            QHeaderView::section {
                background-color: #f0f0f0;
                padding: 6px;
                border: 1px solid #d0d0d0;
                font-weight: bold;
            }
        """)
        
        layout.addWidget(self.table)
        
        # Footer Note
        note_layout = QVBoxLayout()
        # Using a frame or just a label with background
        note_label = QLabel()
        note_label.setTextFormat(Qt.RichText)
        note_label.setText("<b>שימו לב:</b><br>• שורה 8 = 'הכנת תוכנית אישית'.<br>• <b>ACT_NU</b> = מספר השורה המוגדר בהגדרות המשתמש.")
        note_label.setStyleSheet("QLabel { background-color: white; border: 1px solid black; border-radius: 4px; padding: 10px; color: black; }")
        note_layout.addWidget(note_label)
        layout.addLayout(note_layout)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch() # Push button to the left (start of RTL)
        
        close_btn = QPushButton("סגור")
        close_btn.clicked.connect(self.accept)
        close_btn.setMinimumWidth(80)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #f0f0f0;
                border: 1px solid #c0c0c0;
                border-radius: 4px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
        """)
        
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
