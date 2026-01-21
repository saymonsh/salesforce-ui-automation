import threading

import pyvisual as pv

from add_candidats import add_candidats_process
from settings_ui import create_ui as s_ui, create_window as s_window
from main_ui import create_ui as m_ui, create_window as m_window
from login import login_and_process
from attendance_filling import attendance_filling_process
import parameters as parm

uploaded_file_path = r"C:\Users\saymonsh\Downloads\run.xlsx"

def attach_events(ui, app):
    def on_setting_click(button=None):
        if hasattr(app, "settings_window"):
            app.settings_window.show()
        else:
            app.settings_window = s_window()
            settings_ui = s_ui(app.settings_window)
            attach_events_settings(settings_ui, app.settings_window, ui)  # פונקציה נפרדת לאירועי הגדרות
            app.settings_window.show()

    global uploaded_file_path

    def on_browse_button_click(file_path):
        global uploaded_file_path
        uploaded_file_path = file_path
        print(f"📂 File selected: {uploaded_file_path}")

    def on_run_click(button=None):
        if parm.TYPE == 1:
            print("Login in progress")
            thread = threading.Thread(target=login_and_process, args=(uploaded_file_path, ui))
            thread.start()
        elif parm.TYPE == 2:
            print("Adding candidates")
            thread = threading.Thread(target=add_candidats_process, args=(uploaded_file_path, ui))
            thread.start()
        elif parm.TYPE == 3:
            print("test")
            thread = threading.Thread(target=attendance_filling_process)
            thread.start()
        else:
            print(parm.TYPE)
        if uploaded_file_path is None and parm.TYPE != 3:
            ui["Text_uploadStatus"].text = "❌ File not selected"
        elif parm.TYPE in [1, 2]:
            ui["Button_run"].is_visible = False
            ui["Progressbar"].is_visible = True
            ui["Text_running"].is_visible = True
            ui["Rectangle"].is_visible = True
            ui["Progressbar"].value = 0

    ui["FileDialog_fileUpload"].on_file_selected = on_browse_button_click
    if uploaded_file_path == r"C:\Users\saymonsh\Downloads\run.xlsx":
        ui["FileDialog_fileUpload"].text = "run.xlsx"
    ui["Button_run"].on_click = on_run_click
    ui["Button_setting"].on_click = on_setting_click
    pass

    def attach_events_settings(ui, window, main_ui):
        def load_parameters():
            import importlib
            importlib.reload(parm)
        settings = {
            "USER_NAME": parm.USER_NAME,
            "PASSWORD": parm.PASSWORD,
            "SECRET_KEY": parm.SECRET_KEY,
            "ACT_description": parm.ACT_description,
            "ACT_NU": parm.ACT_NU,
            "URL": parm.URL,
            "TYPE": parm.TYPE,
            "UPLOADED_FILE_PATH": parm.UPLOADED_FILE_PATH
        }

        ui["USER_NAME"].text = settings.get("USER_NAME", "")
        ui["PASSWORD"].text = settings.get("PASSWORD", "")
        ui["SECRET_KEY"].text = settings.get("SECRET_KEY", "")
        ui["ACT_description"].text = settings.get("ACT_description", "")
        ui["ACT_NU"].text = settings.get("ACT_NU", "")
        ui["URL"].text = settings.get("URL", "")
        ui["TYPE"].text = str(settings.get("TYPE", ""))
        ui["UPLOADED_FILE_PATH"].text = settings.get("UPLOADED_FILE_PATH", "")

        def on_save_click(button=None):
            user_name = ui["USER_NAME"].text
            password = ui["PASSWORD"].text
            secret_key = ui["SECRET_KEY"].text
            act_description = ui["ACT_description"].text
            act_nu = ui["ACT_NU"].text
            URL = ui["URL"].text
            type_value = ui["TYPE"].text
            uploaded_file_path_value = ui["UPLOADED_FILE_PATH"].text

            import configparser
            config = configparser.ConfigParser(interpolation=None)
            config.read('config.ini', encoding='utf-8')

            config['Auth']['USERNAME'] = user_name
            config['Auth']['PASSWORD'] = password
            config['Auth']['SECRET_KEY'] = secret_key
            config['Activity']['DESCRIPTION'] = act_description
            config['Activity']['NUMBER'] = act_nu
            config['Salesforce']['URL'] = URL
            config['Salesforce']['TYPE'] = type_value
            # Ensure Paths section exists
            if 'Paths' not in config:
                config['Paths'] = {}
            config['Paths']['UPLOADED_FILE_PATH'] = uploaded_file_path_value

            with open('config.ini', 'w', encoding='utf-8') as configfile:
                config.write(configfile)
            window.close()
            load_parameters()
            main_ui["Text_uploadStatus"].text = "Saved"
        ui["SAVE"].on_click = on_save_click
        pass

def main():
    app = pv.PvApp()
    window = m_window()
    ui = m_ui(window)
    attach_events(ui, app)
    window.show()
    app.run()


if __name__ == '__main__':
    main()