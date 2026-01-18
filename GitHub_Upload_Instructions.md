# העלאת הפרויקט ל-GitHub (פרוטוקול SSH)

## שם פרוייקט מומלץ
אני ממליץ על השם: **`salesforce-ui-automation`**
שם זה ברור, מתאר את הטכנולוגיה (Salesforce + UI) ומציין שמדובר באוטומציה.

---

## שלב 1: וידוא מפתח SSH ב-GitHub
ראיתי שיש לך כבר מפתחות SSH במחשב (`id_ed25519`). עליך לוודא שהמפתח הציבורי שלך מוגדר בחשבון ה-GitHub:
1.  הרץ את הפקודה הבאה בטרמינל כדי להעתיק את המפתח ללוח:
    ```powershell
    Get-Content ~/.ssh/id_ed25519.pub | Set-Clipboard
    ```
2.  לך ל-GitHub -> **Settings** -> **SSH and GPG keys**.
3.  לחץ על **New SSH key**, תן כותרת (למשל "My Laptop"), והדבק את המפתח.

## שלב 2: יצירת Repository חדש
1.  ב-GitHub, צור Repository חדש (הפלוס למעלה בצד שמאל).
2.  השתמש בשם המומלץ: `salesforce-ui-automation`.
3.  אל סמן שום תיבת סימון (README/gitignore), יצרנו אותם כבר.
4.  לחץ **Create repository**.

## שלב 3: חיבור ודחיפת הקוד (SSH)
לאחר יצירת ה-Repo, ודא שאתה בוחר בלשונית **SSH** (ולא HTTPS) בראש עמוד ההוראות של GitHub. הכתובת צריכה להתחיל ב-`git@github.com`.

הרץ את הפקודות הבאות בטרמינל בתוך תיקיית הפרויקט:

```powershell
# חיבור התיקייה ל-GitHub ב-SSH
git remote add origin git@github.com:YOUR_USERNAME/salesforce-ui-automation.git

# וידוא שהענף הראשי הוא main
git branch -M main

# דחיפת הקבצים לענן
git push -u origin main
```

> **שים לב**: החלף את `YOUR_USERNAME` בשם המשתמש שלך ב-GitHub.
