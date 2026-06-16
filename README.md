# Salesforce UI Automation Project

אפליקציית דסקטופ ל-Windows שמבצעת אוטומציה לממשק Salesforce Lightning של משרד הרווחה (`welfareministry.lightning.force.com`) — פעולה אחת ב-Salesforce עבור כל שורה שמוזנת בטבלת הנתונים שבתוך האפליקציה. האפליקציה מתחברת אוטומטית (כולל MFA/TOTP), והדפדפן עצמו מוטמע בתוך חלון האפליקציה כך שהמפעיל רואה את הריצה בזמן אמת.

## 📌 תכונות מרכזיות (Features)

*   **אוטומציה מלאה**: התחברות אוטומטית (כולל MFA/TOTP), ניווט, וביצוע פעולות ב-Salesforce.
*   **ממשק משתמש (GUI)**: אפליקציית דסקטופ מבוססת **Flet** (Flutter ל-Python), בעברית (RTL), במסך מלא.
*   **דפדפן מוטמע**: חלון ה-Chrome האמיתי של הריצה מוצג בתוך פאנל באפליקציה (Win32 owned-overlay) — אינטראקטיבי במלואו, ללא כפתור נפרד בשורת המשימות.
*   **טבלת הזנה מובנית**: הנתונים מוזנים בטבלה בתוך האפליקציה — בהקלדה ישירה או בהדבקה מ-Excel/Sheets (Smart Paste). הטיוטה נשמרת אוטומטית (`draft.json`) ומשוחזרת בהפעלה הבאה.
*   **עצירה רספונסיבית (Responsive Stop)**: מנגנון עצירה שיתופי שמאפשר הפסקת ריצה מיידית באמצע תהליך, כולל בזמן המתנות ארוכות.
*   **שני ערוצי פלט**: שדה סטטוס נקי בעברית למפעיל, לצד פיד פעילות טכני מפורט (כולל הפלט של chromedriver).
*   **פרוססים מרובים**: שלושה סוגי תהליכים — דיווחי פעילות, הוספת מועמדים, והזנת נוכחות.
*   **הגדרות גמישות**: קובץ `config.ini` + חלון הגדרות בתוך האפליקציה, ללא צורך בשינוי קוד.

## 🔢 סוגי תהליכים (`TYPE` ב-config)

| TYPE | Processor | מה הוא עושה |
|------|-----------|--------------|
| 1 | `LoginProcessor` | לכל שורה — חיפוש מועמד ויצירת פעילויות/דיווחים לפי עמודת `סוג` (1–6). דורש גם מספר פעילות ותיאור בהגדרות. |
| 2 | `CandidateProcessor` | הוספת מועמדים לסידור שירות לפי תעודת זהות. בסוף הריצה הדפדפן נשאר פתוח ומוטמע ("נדרשת פעולה") כדי שהמפעיל ישלים צעד ידני ויסגור מהפאנל. |
| 3 | `AttendanceProcessor` | הזנת מטריצת נוכחות דרך ה-**Aura API** של Salesforce (ללא קליקים פר-שורה). |

בכל הסוגים הקלט מגיע מטבלת ההזנה שבאפליקציה (בהקלדה או ב-Smart Paste) — אין ייבוא קובץ Excel ואין "הרצת קובץ" ישירות.

## 📂 מבנה הפרויקט (Project Structure)

```text
salesforce-ui-automation/
├── config.ini                # קובץ ההגדרות הראשי (יש ליצור על בסיס config.ini.example)
├── requirements.txt          # רשימת התלויות (Dependencies)
├── src/
│   ├── main.py               # נקודת הכניסה (כולל נעילת instance יחיד)
│   ├── core/                 # config, קבועים, utils, חריגות, לוגים והודעות
│   ├── ui/                   # ממשק משתמש Flet (MVC)
│   │   ├── main_window.py    # החלון הראשי, פאנל הדפדפן המוטמע, פיד הפעילות
│   │   ├── data_grid.py      # טבלת ההזנה (הקלדה + Smart Paste)
│   │   ├── controller.py     # מתאם בין ה-UI לאוטומציה
│   │   ├── worker.py / worker_manager.py  # הרצת ה-Processor ב-Thread נפרד
│   │   └── settings_window.py
│   └── automation/           # מנוע האוטומציה (Selenium)
│       ├── driver_manager.py # הפעלת chromedriver + מסירת חלון Chrome להטמעה
│       ├── win_window.py     # הטמעת הדפדפן בפאנל (Win32 owned-overlay)
│       ├── actions.py        # פעולות Selenium בסיסיות
│       ├── selectors.py      # כל ה-XPaths, מרוכזים
│       ├── api_client.py     # קריאות Aura API (עבור TYPE 3)
│       ├── data_source.py    # שכבת הקלט (מקורות in-memory מהטבלה)
│       └── processors/       # לוגיקה עסקית לפי TYPE
└── assets/                   # קבצים סטטיים (גופנים, אייקונים)
```

## 🚀 התקנה והרצה (Installation & Usage)

### דרישות מוקדמות
*   **Windows** (האפליקציה תלויה ב-Win32 — הטמעת הדפדפן, נעילת instance יחיד).
*   Python 3.10 ומעלה.
*   Google Chrome מותקן.
*   `chromedriver` תואם לגרסת הכרום שלך, בנתיב הקבוע `C:\chromedriver\chromedriver.exe`.

### התקנה
1.  שכפל את המאגר (Clone).
2.  צור סביבה וירטואלית והתקן תלויות:
    ```powershell
    python -m venv .venv
    .\.venv\Scripts\activate
    pip install -r requirements.txt
    ```
3.  צור קובץ `config.ini` בתיקייה הראשית על בסיס `config.ini.example` (בלעדיו האפליקציה לא תעלה).

### הרצה
מהתיקייה הראשית:

```powershell
python -m src.main
```

ניתן להריץ רק עותק אחד של האפליקציה בו-זמנית (הפעלה שנייה תציג הודעה ותיסגר).

## ⚙️ ארכיטקטורה בקצרה

*   **`src/ui/`** — ממשק Flet ב-MVC: ה-View בונה את המסך, ה-Controller מאזין לאירועים ומריץ את ה-Processor המתאים ב-Thread נפרד כדי לא לתקוע את הממשק. עדכוני UI מה-Thread חוזרים ללולאת האירועים של Flet.
*   **`src/automation/`** — מנוע Selenium: `BaseProcessor` מחזיק את מחזור החיים של הדרייבר, ההתחברות (כולל TOTP) ומנגנון העצירה; כל TYPE יורש ממנו. `driver_manager` מפעיל את chromedriver על פורט 9515, מאתר את חלון ה-Chrome ומוסר אותו ל-UI להטמעה.
*   **`src/core/`** — הגדרות (singleton של `config.ini`), קבועים, utils של עצירה שיתופית, ושני ערוצי הלוגים (סטטוס למפעיל / פיד טכני — ראו `docs/logging-channels.md`).

## ⚠️ הערות חשובות (Constraints)

*   **Selenium Selectors**: ה-XPaths ב-`selectors.py` מכוונים מול ה-DOM החי של Salesforce — אין לשנות אותם אלא אם Salesforce עצמה השתנתה.
*   **Waits**: זמני ההמתנה קריטיים ליציבות מול Salesforce ואין לקצר אותם. המערכת משתמשת ב-`smart_sleep` וב-waits אינטרפטיביליים כדי לאפשר עצירה גם בזמן המתנה ארוכה.
*   **הדפדפן המוטמע**: מנגנון ההטמעה (`win_window.py`) נשען על אינווריאנטים שנבדקו בקפידה (ללא `SetParent`, ללא הסתרת החלון בזמן טעינה, ללא maximize). פירוט מלא ב-`CLAUDE.md`.
*   **TYPE 2 — "נדרשת פעולה"**: בסיום ריצה כזו נשארת סשן Salesforce מחובר פתוח בפאנל עד שהמפעיל מסיים את הצעד הידני וסוגר אותו.

---
נכתב ושודרג ע"י **Antigravity (Google DeepMind)** — ינואר–פברואר 2026; הורחב מאז (טבלת הזנה, דפדפן מוטמע) ב-2026.
