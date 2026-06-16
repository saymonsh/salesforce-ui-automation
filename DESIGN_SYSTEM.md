# מערכת העיצוב — כיוון Salesforce Automation

שפה עיצובית אחת לכל ה-UI. מקור האמת בקוד הוא [`src/ui/theme.py`](src/ui/theme.py) —
ייבאו ממנו טוקנים ופונקציות-יצרן במקום לכתוב hex/גדלים ידנית בכל מסך.

> **כלל זהב:** אין צבע, גודל או מרווח "קסם" בתוך view. אם חסר טוקן — מוסיפים ל-`theme.py`.

---

## 1. RTL — הבסיס

האפליקציה בעברית ולכן רצה **right-to-left**. במקום טלאי `text_align=RIGHT` פר-שדה,
קוראים פעם אחת בהקמת העמוד:

```python
from src.ui.theme import apply_theme
apply_theme(page)   # מפעיל page.rtl=True, פונט ברירת-מחדל, רקע ו-color scheme
```

מרגע זה: יישור טקסט, סדר אייקון→תווית, וכיוון הדיאלוגים מטופלים אוטומטית.

---

## 2. צבעים (Design Tokens)

נגזרים מהלוגו: יהלום מגנטה → `BRAND`, מילת "כיוון" כהה → `CHARCOAL`, תגית אפורה → ניטרליים.

### מותג
| טוקן | ערך | שימוש |
|------|------|--------|
| `Color.BRAND` | `#de2952` | פעולה ראשית, פוקוס, פרוגרס |
| `Color.BRAND_HOVER` | `#c01f45` | hover/pressed; **טקסט ניווט פעיל** על `BRAND_TINT` (AA 4.9:1) |
| `Color.BRAND_TINT` | `#fbe4ea` | רקע ניווט פעיל, מילויי מותג עדינים |
| `Color.CHARCOAL` | `#2b2b2b` | wordmark, כותרות חזקות |

### סמנטיים
| טוקן | ערך | שימוש |
|------|------|--------|
| `Color.SUCCESS` | `#137a4e` | ריצה שהושלמה |
| `Color.WARNING` | `#8a5a00` | אזהרות / ולידציה (AA כטקסט רגיל, 5.9:1) |
| `Color.DANGER` | `#c0392b` | עצירה / הרסני / שגיאות |
| `Color.INFO` | `#2563eb` | הודעות מידע |

### ניטרליים
| טוקן | ערך | ניגודיות על לבן |
|------|------|------------------|
| `Color.TEXT_PRIMARY` | `#1a1a1a` | ✅ AAA |
| `Color.TEXT_SECONDARY` | `#595959` | ✅ AA (~7:1) — **מחליף את `#828383` שנכשל** |
| `Color.TEXT_TERTIARY` | `#767676` | ✅ גבול AA (placeholder/large) |
| `Color.BORDER` | `#d9d9d9` | גבולות דקורטיביים (שדות/מפרידים) |
| `Color.BORDER_STRONG` | `#767676` | גבול שקובע זהות רכיב (non-text AA, 4.5:1) |
| `Color.SURFACE` | `#ffffff` | כרטיסים, sidebar, שדות |
| `Color.BACKGROUND` | `#f4f4f4` | רקע עמוד |
| `Color.SURFACE_INVERSE` | `#1e1e1e` | רקע לוגים/טרמינל |

**נגישות:** כל זוגות הטקסט/רקע עומדים ב-WCAG AA. זה תיקן את שתי הנפילות מהביקורת —
האפור המשני (`#828383`→`#595959`) וכפתור העצירה (ורוד→`DANGER` אדום).

---

## 3. טיפוגרפיה לעברית

פונט ראשי **Heebo** (נוצר לעברית, נקי ומודרני, מספר משקלים). נטען מ-`assets/fonts/`;
אם חסר — נפילה לפונט המערכת (Segoe UI מטפל בעברית היטב). לוגים ב-`Consolas`.

> **התקנה:** הורידו `Heebo-VariableFont_wght.ttf` מ-Google Fonts ל-`assets/fonts/Heebo/`.
> `apply_theme` רושם את הפונט רק אם הקובץ קיים — אחרת נופל לפונט המערכת ללא שגיאה.

### סולם (`Type`)
| טוקן | גודל / משקל | שימוש |
|------|-------------|--------|
| `Type.H1` | 24 / W700 | כותרת מסך |
| `Type.H2` | 20 / W700 | כותרת מקטע |
| `Type.TITLE` | 18 / W600 | כותרת כרטיס / sidebar |
| `Type.BODY_LG` | 16 / W500 | סטטוס, טקסט בולט |
| `Type.BODY` | 14 / W400 | טקסט ברירת מחדל |
| `Type.CAPTION` | 13 / W400 | רמזים, שורות לוג |

```python
from src.ui.theme import heading, body_text, Type
heading("הגדרות משתמש")                      # H1
body_text("מוכן", Type.BODY_LG, Color.TEXT_SECONDARY)
```

---

## 4. מרווחים, רדיוס, צל

| קטגוריה | טוקנים |
|---------|--------|
| `Space` (בסיס 4px) | `XS=4` · `SM=8` · `MD=12` · `LG=16` · `XL=20` · `XXL=24` · `XXXL=32` |
| `Radius` | `SM=6` · `MD=8` (ברירת מחדל) · `LG=12` · `PILL=999` |
| `Elevation` | `CARD=2` · `DIALOG=6` |

מרווח רכיבים סטנדרטי: `Space.XL` (20) ל-padding של כרטיסים/כפתורים, `Space.LG`/`MD` בין רכיבים.

---

## 5. רכיבי בסיס

כולם פונקציות-יצרן ב-`theme.py` — קוראים להן במקום לבנות `ft.*` ידנית.

### כפתורים
| וריאנט | פונקציה | מתי |
|--------|----------|-----|
| Primary | `primary_button("הפעל", icon=...)` | פעולה ראשית, אחת למסך. מילוי מותג, טקסט לבן |
| Secondary | `secondary_button("בחר קובץ", icon=...)` | פעולה תומכת. מתאר ניטרלי |
| Danger | `danger_button("עצור תהליך", icon=...)` | הרסני/עצירה. אדום מלא — **בולט, לא ורוד-חלש** |

כולם: רדיוס `MD`, padding `XL`. מצבים: default / hover (כהה יותר) / disabled (עמעום Flet).

### שדה טקסט
```python
text_field("USER_NAME", value=...)            # יישור RTL מ-page.rtl, בלי טלאי
text_field("PASSWORD", password=True, can_reveal_password=True)
```
גבול `BORDER`, פוקוס `BRAND`, label ב-`TEXT_SECONDARY`.

### כרטיס
```python
card(ft.Column([...]))                          # משטח לבן, elevation=2, padding XL
```

---

## 6. מצב ההטמעה (migration) — ✅ בוצע

`theme.py` מחובר לכל ה-views:

| קובץ | סטטוס |
|------|--------|
| `src/ui/main_window.py` | ✅ `apply_theme(page)` (RTL); כפתורי `primary/danger/secondary`; sidebar בימין; ניווט = כפתור focusable; מצב סטטוס SUCCESS; אזור לוג כהה עם placeholder |
| `src/ui/settings_window.py` | ✅ `text_field` + `heading` + `primary_button`; `text_align=RIGHT` הוסר (RTL גלובלי) |
| `src/ui/components/progress_bar.py` | ✅ `Color.BRAND` + `Color.BORDER` + `Type` |
| `src/ui/data_grid.py` | ✅ צ'יפים של בורר ה-`סוג` (`CHIP_PLAN_FG`/`CHIP_REPORT_FG`) |
| `src/ui/controller.py` | ✅ מעביר `level="success"/"error"` ל-`set_status` |

**נותר כ-follow-up:** שגיאות ולידציה inline פר-שדה (`error_text`) — דורש מיפוי של
`Config.validate()` לשדות; כרגע מוצג alert מצרפי. (WCAG 3.3.1, מתועד ב-HANDOFF §10.)
