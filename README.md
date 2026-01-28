# Salesforce UI Automation Project

פרויקט זה מספק אוטומציה לממשק המשתמש של Salesforce עבור משרד הרווחה, ומאפשר ביצוע פעולות גורפות (Bulk Actions) באמצעות קבצי Excel.
הפרויקט עבר שדרוג ארכיטקטוני מקיף ("Refactoring") ב-2026 כדי לשפר את התחזוקה, הקריאות והיציבות, תוך שמירה קפדנית על הלוגיקה העסקית והאוטומציה המקורית.

## 📌 תכונות מרכזיות (Features)

*   **אוטומציה מלאה**: התחברות אוטומטית (כולל MFA/TOTP), ניווט, וביצוע פעולות ב-Salesforce.
*   **ממשק משתמש (GUI)**: אפליקציית דסקטופ נוחה (מבוססת PySide6/PyVisual) לטעינת קבצים וניהול הגדרות.
*   **תמיכה בקבצי Excel**: קריאת נתונים מובנית מקבצי אקסל וביצוע פעולות לכל שורה.
*   **פרוססים מרובים**: תמיכה במספר סוגי תהליכים (Login, Add Candidates, Attendance Filling).
*   **הגדרות גמישות**: קובץ `config.ini` לניהול פרמטרים ומשתמשים ללא צורך בשינוי קוד.

## 📂 מבנה הפרויקט (Project Structure)

הקוד עבר ארגון מחדש לתוך תיקיית `src/` למבנה מודולרי:

```text
salesforce-ui-automation/
├── config.ini             # קובץ ההגדרות הראשי (יש ליצור על בסיס config.ini.example)
├── requirements.txt       # רשימת התלויות (Dependencies)
├── src/                   # קוד המקור
│   ├── main.py            # נקודת הכניסה להרצת האפליקציה
│   ├── core/              # ליבת המערכת
│   │   ├── config.py      # טעינת הגדרות מ-config.ini
│   │   └── constants.py   # קבועים נתיבים לנכסים (Assets)
│   ├── ui/                # ממשק משתמש (MVC)
│   │   ├── main_window.py # הגדרת החלון הראשי והאלמנטים
│   │   ├── settings_window.py # חלון ההגדרות
│   │   ├── controller.py  # לוגיקה שמחברת בין ה-UI לאוטומציה
│   │   └── components/    # רכיבי UI מותאמים (למשל: ProgressBar)
│   └── automation/        # מנוע האוטומציה
│       ├── driver_manager.py # ניהול הדרייבר של Chrome
│       ├── actions.py     # פעולות בסיסיות (Selenium Actions)
│       └── processors/    # לוגיקה עסקית לפי תהליך
│           ├── login_processor.py      # תהליך ראשי (Type 1-3)
│           ├── candidate_processor.py  # הוספת מועמדים
│           └── attendance_processor.py # מילוי נוכחות
└── assets/                # קבצים סטטיים (גופנים, אייקונים)
```

## 🚀 התקנה והרצה (Installation & Usage)

### דרישות מוקדמות
*   Python 3.10 ומעלה.
*   Google Chrome מותקן.
*   `chromedriver` תואם לגרסת הכרום שלך (בנתיב `C:\chromedriver\chromedriver.exe`).

### התקנה
1.  שכפל את המאגר (Clone).
2.  צור סביבה וירטואלית והתקן תלויות:
    ```bash
    python -m venv .venv
    .\.venv\Scripts\activate
    pip install -r requirements.txt
    ```
3.  ודא שקיים קובץ `config.ini` תקין בתיקייה הראשית.

### הרצה
להפעלת המערכת יש להריץ את הפקודה הבאה מהתיקייה הראשית:

```bash
python -m src.main
```

## ⚙️ הסבר על המודולים (Modules)

### Automation Core
המערכת משתמשת ב-Selenium לצורך האוטומציה.
*   **`driver_manager.py`**: אחראי על טעינת ה-ChromeDriver עם ההגדרות המתאימות (נטרול התראות, פרוקסי וכו').
*   **`processors/`**: כל קובץ כאן מייצג "Type" של ריצה.
    *   `login_processor`: מטפל בקבצי אקסל בהם יש עמודת "סוג" (1 עד 6), ומבצע פעולות כמו חיפוש, יצירת פעילות, ודיווח שירות.
    *   `attendance_processor`: סקריפט מיוחד שמתחבר ל-Session קיים או יוצר חדש כדי לאפשר למשתמש לסמן נוכחות ידנית/אוטומטית למחצה.

### UI Architecture
הממשק נבנה מחדש להפרדה בין **View** (קבצי `_window.py`) ל-**Controller**.
*   ה-View אחראי רק על יצירת הכפתורים והשדות.
*   ה-Controller (`controller.py`) מאזין ללחיצות, טוען את ההגדרות ומפעיל את ה-Processor המתאים ברקע (Thread נפרד) כדי לא לתקוע את הממשק.

## ⚠️ הערות חשובות (Constraints)
*   **Selenium Selectors**: הוגדרו בצורה קשיחה (Hardcoded XPaths) ואין לשנות אותם אלא אם כן השתנה ה-DOM של Salesforce.
*   **Waits**: זמני ההמתנה (`sleep`, `implicitly_wait`) קריטיים ליציבות המערכת מול Salesforce ואין לקצר אותם.

---
נכתב ושודרג ע"י **Antigravity (Google Deepmind)** - ינואר 2026.
