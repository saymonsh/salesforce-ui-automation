import pandas as pd
from datetime import datetime

class ExcelParser:
    @staticmethod
    def parse_attendance_matrix(filepath):
        # Read without header to get exact grid
        df = pd.read_excel(filepath, header=None)
        
        if df.empty or len(df.columns) < 2 or len(df) < 2:
            raise ValueError("קובץ האקסל ריק או שאינו בפורמט תקין.")
            
        a1_val = str(df.iloc[0, 0]).strip()
        try:
            start_time_str, end_time_str = a1_val.split('|')
            # Validate format HH:MM
            datetime.strptime(start_time_str, '%H:%M')
            datetime.strptime(end_time_str, '%H:%M')
        except ValueError:
            raise ValueError(f"תא A1 חייב להיות בפורמט HH:MM|HH:MM, התקבל: {a1_val}")
            
        # Parse dates from B1 onwards
        dates = []
        for col_idx in range(1, len(df.columns)):
            date_val = df.iloc[0, col_idx]
            if pd.isna(date_val):
                continue
            
            # Format could be datetime object or string. Make sure we can format it to YYYY-MM-DD
            if isinstance(date_val, datetime):
                dates.append((col_idx, date_val.strftime('%Y-%m-%d')))
            else:
                try:
                    # Try common Israeli format if it's string
                    parsed_date = pd.to_datetime(date_val, dayfirst=True)
                    dates.append((col_idx, parsed_date.strftime('%Y-%m-%d')))
                except:
                    dates.append((col_idx, str(date_val).strip()))
                    
        if not dates:
            raise ValueError("לא נמצאו תאריכים בשורת הכותרת (החל מעמודה B).")
            
        # Parse IDs and pad to 9 digits
        participants = []
        for row_idx in range(1, len(df)):
            id_val = df.iloc[row_idx, 0]
            if pd.isna(id_val):
                continue
                
            # Clean ID: remove non-digits
            id_str = str(id_val).split('.')[0] # in case it's parsed as float 12345678.0
            id_str = ''.join(filter(str.isdigit, id_str))
            if not id_str:
                continue
                
            if len(id_str) <= 9:
                id_str = id_str.zfill(9)
                
            matrix_data = {}
            for col_idx, date_str in dates:
                cell_val = df.iloc[row_idx, col_idx]
                if pd.isna(cell_val) or str(cell_val).strip() == '':
                    matrix_data[date_str] = "לא נוכח"
                else:
                    matrix_data[date_str] = "נוכח"
                    
            participants.append({
                'id_number': id_str,
                'attendance': matrix_data
            })
            
        return {
            'start_time': start_time_str,
            'end_time': end_time_str,
            'dates': [d[1] for d in dates],
            'participants': participants
        }
