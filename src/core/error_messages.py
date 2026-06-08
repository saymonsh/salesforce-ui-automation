"""Map technical exceptions to user-facing Hebrew explanations (issue #12).

The status channel must never show a raw exception string like
``Message: Timed out after 30 sec`` — the operator can't act on that. This
module classifies a failure into a category the *operator* understands.

Each category returns a **(title, hint)** pair:
- ``title`` — short enough to fit the single-line status field on its own.
- ``hint``  — the actionable "what to do", shown in the failure dialog (which
  wraps, so it is never truncated). May be empty.

The full technical detail + traceback still goes to the debug channel (the
logger writes it to the activity feed), so nothing is lost.

Classification uses three signals, in order of reliability:
1. The app's own validation errors are already Hebrew & operator-facing — pass
   them through verbatim as the title (detected by a leading Hebrew character).
2. The stage the run was in when it failed (``login`` / ``aura`` / ``driver`` …),
   read from the logger — disambiguates otherwise-identical timeouts.
3. The exception type name and message text.
"""
from __future__ import annotations

import re

_HEBREW_CHAR = re.compile(r"[֐-׿]")

# Fallback when nothing else matches. Always points at where the raw detail lives.
_FALLBACK = (
    "שגיאה לא צפויה",
    "פתח את זרם הפעילות (הטרמינל) כדי לראות את הפרטים הטכניים המלאים.",
)


def _starts_hebrew(text: str) -> bool:
    t = text.strip()
    return bool(t) and bool(_HEBREW_CHAR.match(t[0]))


def humanize_error(exc, stage: str | None = None) -> tuple[str, str]:
    """Return an operator-facing ``(title, hint)`` for ``exc``.

    ``exc`` may be an exception instance or a plain message string. ``stage`` is
    the run stage at failure time (e.g. from ``logger.current_stage``).
    """
    raw = str(exc).strip() or type(exc).__name__
    # 1. The app's own validation errors are already written for the operator.
    if _starts_hebrew(raw):
        return raw, ""

    low = raw.lower()
    etype = type(exc).__name__ if isinstance(exc, BaseException) else ""
    st = (stage or "").lower()

    # 1b. Salesforce login-error banner (captured by _login when the MFA step
    # times out because Salesforce refused the login). The banner text carries
    # the real reason — branch on it.
    if "security policy" in low or "preventing you from logging in" in low or "restricted ip" in low:
        return ("Salesforce חוסם את ההתחברות",
                "מדיניות האבטחה של הארגון חוסמת התחברות מהכתובת הנוכחית — לרוב בגלל "
                "VPN/proxy או רשת לא מורשית. התנתק מה-VPN או התחבר מרשת מורשית ונסה שוב. "
                "אם זה נמשך, פנה למנהל ה-Salesforce כדי לאשר את הכתובת.")
    if "salesforce login error" in low or "login attempt has failed" in low \
            or "username or password" in low or "check your username" in low \
            or ("password" in low and "incorrect" in low):
        if "locked" in low:
            return ("חשבון Salesforce נעול",
                    "החשבון ננעל עקב ניסיונות התחברות כושלים. המתן מעט או פנה למנהל ה-Salesforce.")
        return ("ההתחברות ל-Salesforce נכשלה",
                "Salesforce דחה את ההתחברות. בדוק שם משתמש וסיסמה בהגדרות ונסה שוב.")

    # 2. Browser / driver lifecycle.
    driver_markers = (
        "chromedriver", "chrome not reachable", "session not created",
        "devtoolsactiveport", "cannot find chrome", "no such window",
        "disconnected", "connection refused", "max retries", "newconnectionerror",
        "failed to establish a new connection",
    )
    if etype in ("WebDriverException", "SessionNotCreatedException", "MaxRetryError") \
            or st == "driver" or any(m in low for m in driver_markers):
        if "version" in low or "session not created" in low:
            return ("גרסת chromedriver לא תואמת ל-Chrome",
                    "גרסת ה-chromedriver אינה תואמת לגרסת Chrome המותקנת. עדכן את "
                    r"chromedriver.exe לגרסה התואמת (ב-C:\chromedriver) ונסה שוב.")
        return ("הדפדפן (Chrome) לא הופעל",
                "Chrome לא נפתח או נסגר באמצע. ודא ש-chromedriver מותקן ותקין, סגור "
                "חלונות Chrome פתוחים ונסה שוב.")

    # 3. Salesforce / Aura API.
    if "client out of sync" in low:
        return ("Salesforce עודכן ברקע",
                "המערכת של Salesforce התעדכנה תוך כדי. רענן את הדף והרץ שוב.")
    if "aura token" in low or "aura context" in low:
        return ("אין תקשורת עם Salesforce",
                "לא הצלחנו להתחבר ל-API של Salesforce. המתן שהדף ייטען במלואו ונסה שוב.")
    if "salesforce error" in low or low.startswith("api error") or "no json found" in low or st == "aura":
        return ("Salesforce החזיר שגיאה",
                "השמירה מול Salesforce נכשלה. פתח את זרם הפעילות (הטרמינל) כדי לראות "
                "את תגובת השרת המלאה.")

    # 4. Excel / input file.
    if etype == "FileNotFoundError" or "no such file" in low:
        return ("קובץ ה-Excel לא נמצא",
                "הקובץ שנבחר לא קיים יותר בנתיב שלו. בחר קובץ קיים ונסה שוב.")
    if etype == "BadZipFile" or "excel file format" in low or "unsupported format" in low \
            or "not a zip file" in low or "no engine for filetype" in low:
        return ("קובץ ה-Excel פגום",
                "לא ניתן לקרוא את הקובץ. פתח אותו ב-Excel ושמור מחדש כקובץ ‎.xlsx ונסה שוב.")
    if etype == "KeyError":
        return ("חסרה עמודה בקובץ ה-Excel",
                "אחת מהעמודות הנדרשות חסרה. ודא שקיימות העמודות: תעודות זהות, סוג, תאריך "
                "(בכותרות, בדיוק כפי שנכתב).")

    # 5. Timeouts / missing elements — meaning depends on the stage.
    if etype == "TimeoutException" or "timed out" in low or "timeout" in low:
        if st == "login":
            # A login timeout with no error banner (the banner case is handled
            # above): the page didn't respond in time — usually network/site.
            return ("ההתחברות ל-Salesforce לא הושלמה",
                    "מסך ההתחברות לא הגיב בזמן. בדוק את החיבור לאינטרנט (ואם אתה מאחורי "
                    "VPN/proxy — ייתכן שהוא חוסם). אם הפרטים בהגדרות תקינים, נסה שוב.")
        return ("רכיב במסך לא נמצא בזמן",
                "הפעולה ארכה זמן רב מדי. ייתכן שהאתר איטי או שעיצוב המסך ב-Salesforce "
                "השתנה. נסה שוב, ואם זה חוזר — ייתכן שצריך לעדכן את הסלקטורים.")
    if etype == "NoSuchElementException" or "no such element" in low or "unable to locate element" in low:
        return ("רכיב במסך לא נמצא",
                "ייתכן שעיצוב המסך ב-Salesforce השתנה. נסה שוב, ואם זה חוזר — פנה לתמיכה.")
    if etype == "ElementClickInterceptedException" or "click intercepted" in low:
        return ("לחיצה במסך נחסמה",
                "רכיב אחר הסתיר את הכפתור. נסה שוב; אם זה חוזר, ודא שאין חלונות קופצים פתוחים.")
    if etype == "StaleElementReferenceException" or "stale element" in low:
        return ("המסך התרענן באמצע פעולה", "נסה להריץ שוב.")

    # 6. Known wrapped failures from the processors.
    if "critical failure" in low and "type 1" in low:
        return ("עיבוד שורה מסוג 1 נכשל",
                "אחת השורות מסוג 1 נכשלה והתהליך נעצר. פתח את זרם הפעילות כדי לראות באיזו "
                "שורה ומה הסיבה.")

    return _FALLBACK
