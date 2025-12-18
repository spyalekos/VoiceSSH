# settings_screen.py
"""
SettingsScreen provides a UI for managing multiple SSH connections (settings).
It lists available connections and allows adding/editing them via ConnectionEditScreen.
"""

from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.screen import Screen
from kivymd.uix.toolbar import MDTopAppBar
from kivymd.uix.textfield import MDTextField
from kivymd.uix.button import MDRaisedButton, MDIconButton
from kivy.utils import platform
from kivymd.uix.dialog import MDDialog
from kivymd.uix.label import MDLabel
from kivymd.uix.list import MDList, ThreeLineAvatarIconListItem, IconRightWidget, IconLeftWidget
from kivymd.uix.scrollview import MDScrollView
from kivy.metrics import dp
import database
import json
import os
from kivy.uix.filechooser import FileChooserIconView

class SettingsScreen(Screen):
    """Screen that lists all SSH connections."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.build_ui()

    def build_ui(self):
        layout = MDBoxLayout(orientation='vertical')

        # Toolbar
        self.toolbar = MDTopAppBar(title="Ρυθμίσεις SSH Servers", elevation=4)
        self.toolbar.md_bg_color = [1, 0, 0, 1]
        self.toolbar.left_action_items = [["arrow-left", lambda x: self.go_back()]]
        self.toolbar.right_action_items = [
            ["database-export", lambda x: self.export_db()],
            ["database-import", lambda x: self.import_db_dialog()],
            ["plus", lambda x: self.add_connection()]
        ]
        layout.add_widget(self.toolbar)

        # List
        scroll = MDScrollView()
        self.list_layout = MDList()
        scroll.add_widget(self.list_layout)
        layout.add_widget(scroll)

        self.add_widget(layout)

    def on_enter(self, *args):
        self.refresh_list()

    def refresh_list(self):
        self.list_layout.clear_widgets()
        connections = database.get_ssh_connections()

        for conn in connections:
            item = ThreeLineAvatarIconListItem(
                text=conn['alias'],
                secondary_text=f"{conn['host']}:{conn['port']}",
                tertiary_text=conn['username'],
                on_release=lambda x, a=conn['alias']: self.edit_connection(a)
            )
            
            icon_left = IconLeftWidget(icon="server")
            item.add_widget(icon_left)
            
            icon_right = IconRightWidget(
                icon="delete", 
                on_release=lambda x, a=conn['alias']: self.confirm_delete(a)
            )
            item.add_widget(icon_right)
            
            self.list_layout.add_widget(item)

    def go_back(self):
        self.manager.current = 'main'

    def add_connection(self):
        self.manager.get_screen('connection_edit').set_mode('add')
        self.manager.current = 'connection_edit'

    def edit_connection(self, alias):
        self.manager.get_screen('connection_edit').set_mode('edit', alias)
        self.manager.current = 'connection_edit'

    def confirm_delete(self, alias):
        self.dialog = MDDialog(
            text=f'Διαγραφή του server "{alias}";',
            buttons=[
                MDRaisedButton(text="ΑΚΥΡΩΣΗ", on_release=lambda x: self.dialog.dismiss()),
                MDRaisedButton(text="ΔΙΑΓΡΑΦΗ", md_bg_color=(1, 0.3, 0.3, 1), on_release=lambda x: self.do_delete(alias))
            ]
        )
        self.dialog.open()

    def do_delete(self, alias):
        database.delete_ssh_connection(alias)
        self.dialog.dismiss()
        self.refresh_list()

    def export_db(self):
        """Άνοιγμα διαλόγου για επιλογή φακέλου εξαγωγής."""
        # Προεπιλεγμένο όνομα αρχείου
        default_name = "commands_backup.json"
        
        path = "."
        if platform == 'android':
            from android.storage import primary_external_storage_path
            path = primary_external_storage_path()

        content = MDBoxLayout(orientation='vertical', spacing=dp(10), size_hint_y=None, height=dp(400))
        
        file_chooser = FileChooserIconView(
            path=path,
            filters=["*.json"],
            size_hint_y=1
        )
        content.add_widget(file_chooser)

        self.export_chooser_dialog = MDDialog(
            title="Επιλογή Φακέλου Εξαγωγής",
            type="custom",
            content_cls=content,
            buttons=[
                MDRaisedButton(
                    text="ΑΚΥΡΩΣΗ",
                    on_release=lambda x: self.export_chooser_dialog.dismiss()
                ),
                MDRaisedButton(
                    text="ΕΞΑΓΩΓΗ ΕΔΩ",
                    on_release=lambda x: self.do_export_to_path(file_chooser.path, default_name)
                ),
            ],
        )
        self.export_chooser_dialog.open()

    def do_export_to_path(self, directory, filename):
        """Εκτέλεση της εξαγωγής στο συγκεκριμένο path."""
        self.export_chooser_dialog.dismiss()
        try:
            full_path = os.path.join(directory, filename)
            data = database.export_db_data()
            with open(full_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            
            self.show_info_dialog(
                "Επιτυχία Export", 
                f"Η βάση αποθηκεύτηκε στο:\n{full_path}"
            )
        except Exception as e:
            self.show_info_dialog("Σφάλμα Export", str(e))

    def import_db_dialog(self):
        """Άνοιγμα διαλόγου για επιλογή αρχείου εισαγωγής."""
        path = "."
        if platform == 'android':
            from android.storage import primary_external_storage_path
            path = primary_external_storage_path()

        content = MDBoxLayout(orientation='vertical', spacing=dp(10), size_hint_y=None, height=dp(400))
        
        file_chooser = FileChooserIconView(
            path=path,
            filters=["*.json"],
            size_hint_y=1
        )
        content.add_widget(file_chooser)

        self.import_chooser_dialog = MDDialog(
            title="Επιλογή Αρχείου Backup (.json)",
            type="custom",
            content_cls=content,
            buttons=[
                MDRaisedButton(
                    text="ΑΚΥΡΩΣΗ",
                    on_release=lambda x: self.import_chooser_dialog.dismiss()
                ),
                MDRaisedButton(
                    text="ΕΠΙΛΟΓΗ",
                    on_release=lambda x: self.on_file_selected_for_import(file_chooser.selection)
                ),
            ],
        )
        self.import_chooser_dialog.open()

    def on_file_selected_for_import(self, selection):
        """Αφού επιλεγεί αρχείο, ρωτάμε για τον τρόπο εισαγωγής."""
        if not selection:
            return
        
        self.import_chooser_dialog.dismiss()
        selected_file = selection[0]
        
        self.import_mode_dialog = MDDialog(
            title="Τρόπος Εισαγωγής",
            text=f"Αρχείο: {os.path.basename(selected_file)}\n\nΠώς θέλετε να γίνει η εισαγωγή;",
            buttons=[
                MDRaisedButton(
                    text="MERGE (Συνένωση)",
                    on_release=lambda x: self.do_import(selected_file, 'merge')
                ),
                MDRaisedButton(
                    text="REPLACE ALL",
                    md_bg_color=(1, 0, 0, 1),
                    on_release=lambda x: self.do_import(selected_file, 'replace')
                ),
                MDRaisedButton(
                    text="ΑΚΥΡΩΣΗ",
                    on_release=lambda x: self.import_mode_dialog.dismiss()
                ),
            ],
        )
        self.import_mode_dialog.open()

    def do_import(self, file_path, mode):
        """Εκτέλεση της εισαγωγής από το επιλεγμένο αρχείο."""
        if hasattr(self, 'import_mode_dialog'):
            self.import_mode_dialog.dismiss()
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            success = database.import_db_data(data, mode)
            if success:
                self.show_info_dialog("Επιτυχία", "Η εισαγωγή ολοκληρώθηκε επιτυχώς!")
                self.refresh_list()
            else:
                self.show_info_dialog("Σφάλμα", "Αποτυχία κατά την εισαγωγή στη βάση.")
        except Exception as e:
            self.show_info_dialog("Σφάλμα Import", str(e))

    def show_info_dialog(self, title, text):
        """Βοηθητικό dialog για μηνύματα."""
        dialog = MDDialog(
            title=title,
            text=text,
            buttons=[MDRaisedButton(text="OK", on_release=lambda x: dialog.dismiss())]
        )
        dialog.open()


class ConnectionEditScreen(Screen):
    """Screen for adding/editing a specific SSH connection."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.mode = 'add'
        self.old_alias = None
        self.build_ui()

    def build_ui(self):
        layout = MDBoxLayout(orientation='vertical')

        self.toolbar = MDTopAppBar(title="Σύνδεση", elevation=4)
        self.toolbar.left_action_items = [["close", lambda x: self.go_back()]]
        self.toolbar.right_action_items = [["content-save", lambda x: self.save_connection()]]
        layout.add_widget(self.toolbar)

        form = MDBoxLayout(orientation='vertical', padding=dp(20), spacing=dp(20))

        self.alias_input = MDTextField(
            hint_text="Alias (Όνομα)",
            helper_text="π.χ. Σπίτι, Γραφείο",
            helper_text_mode="on_focus"
        )
        form.add_widget(self.alias_input)

        self.host_input = MDTextField(
            hint_text="Host",
            helper_text="π.χ. 192.168.1.5",
            helper_text_mode="on_focus"
        )
        form.add_widget(self.host_input)

        self.port_input = MDTextField(
            hint_text="Port",
            helper_text="Default: 22",
            helper_text_mode="on_focus",
            text="22"
        )
        form.add_widget(self.port_input)

        self.user_input = MDTextField(
            hint_text="Username",
            helper_text="π.χ. admin",
            helper_text_mode="on_focus"
        )
        form.add_widget(self.user_input)

        self.pass_input = MDTextField(
            hint_text="Password",
            helper_text="(Optional)",
            helper_text_mode="on_focus",
            password=True
        )
        form.add_widget(self.pass_input)

        self.error_lbl = MDLabel(text="", theme_text_color="Error", halign="center")
        form.add_widget(self.error_lbl)

        form.add_widget(MDBoxLayout()) # Spacer

        layout.add_widget(form)
        self.add_widget(layout)

    def set_mode(self, mode, alias=None):
        self.mode = mode
        self.old_alias = alias
        self.error_lbl.text = ""
        
        if mode == 'edit' and alias:
            self.toolbar.title = f"Επεξεργασία {alias}"
            data = database.get_ssh_connection(alias)
            if data:
                self.alias_input.text = data['alias']
                self.host_input.text = data['host']
                self.port_input.text = str(data['port'])
                self.user_input.text = data['username']
                self.pass_input.text = data['password'] or ""
        else:
            self.toolbar.title = "Νέα Σύνδεση"
            self.alias_input.text = ""
            self.host_input.text = ""
            self.port_input.text = "22"
            self.user_input.text = ""
            self.pass_input.text = ""

    def go_back(self):
        self.manager.current = 'settings'

    def save_connection(self):
        alias = self.alias_input.text.strip()
        host = self.host_input.text.strip()
        port = self.port_input.text.strip()
        user = self.user_input.text.strip()
        password = self.pass_input.text.strip()

        if not alias or not host or not user:
            self.error_lbl.text = "Συμπληρώστε Alias, Host και Username."
            return

        if not port.isdigit():
            self.error_lbl.text = "Το Port πρέπει να είναι αριθμός."
            return

        success = database.save_ssh_connection(alias, host, int(port), user, password, old_alias=self.old_alias)
        if success:
            self.manager.current = 'settings'
        else:
            self.error_lbl.text = "Σφάλμα: Πιθανώς το Alias υπάρχει ήδη."
