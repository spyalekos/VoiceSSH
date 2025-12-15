# main.py
import sys
import io
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.popup import Popup
from kivy.uix.dropdown import DropDown
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.utils import platform
import paramiko

# Import database module
import database

# ---------- Android-specific imports ----------
# These are only loaded when running on Android to prevent build errors
if platform == 'android':
    from jnius import autoclass, PythonJavaClass, java_method
    from android.permissions import request_permissions, Permission
    
    # SpeechRecognizer classes
    SpeechRecognizer = autoclass('android.speech.SpeechRecognizer')
    Intent = autoclass('android.content.Intent')
    RecognizerIntent = autoclass('android.speech.RecognizerIntent')
    Context = autoclass('android.content.Context')
    PythonActivity = autoclass('org.kivy.android.PythonActivity')
    activity = PythonActivity.mActivity

# ---------- Constants ----------
# Χρήση localhost για testing, 192.168.0.12 για Android
HOST = '127.0.0.1'
if platform == 'android' : HOST = '192.168.0.8'
PORT = 22
USER = 'alekos'
PASS = '@lekos'          # <-- Μην το hard‑code σε production!


# ---------- Helpers ----------
def run_remote(cmd):
    """
    Εκτελεί εντολή σε Windows μέσω SSH (Paramiko).
    Returns stdout (string) ή σφάλμα (string).
    """
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        # Μικρότερα timeouts για να μην κολλάει η εφαρμογή
        client.connect(
            HOST, PORT, USER, PASS, 
            timeout=10,        # Connection timeout
            banner_timeout=10  # SSH banner timeout
        )

        # Ανίχνευση εντολών που ξεκινούν προγράμματα που μένουν ενεργά
        cmd_lower = cmd.lower().strip()
        is_background_cmd = (
            cmd_lower.startswith('start ') or 
            '.exe' in cmd_lower or
            'msconfig' in cmd_lower
        )

        if is_background_cmd:
            # Για GUI εφαρμογές, χρησιμοποιούμε το PsExec για να τρέξουν
            # στο interactive user session (Session 1).
            # Το -i 1 σημαίνει: εκτέλεση στο Session ID 1 (το πρώτο interactive session)
            # Το -d σημαίνει: don't wait for process termination
            # Το -accepteula σημαίνει: αποδοχή του EULA αυτόματα
            
            # Αφαιρούμε το 'start ' αν υπάρχει
            if cmd_lower.startswith('start '):
                cmd = cmd[6:].strip()
            
            # Αν η εντολή περιέχει κενά και δεν έχει ήδη εισαγωγικά, προσθέτουμε
            if ' ' in cmd and not (cmd.startswith('"') and cmd.endswith('"')):
                cmd_quoted = f'"{cmd}"'
            else:
                cmd_quoted = cmd
            
            # Δημιουργία της psexec εντολής
            # -i 1 = interactive session 1
            # -u username -p password = τρέχει με τα δικαιώματα του συγκεκριμένου χρήστη
            # -d = don't wait for termination
            # -accepteula = αυτόματη αποδοχή EULA
            psexec_cmd = f'psexec -i 1 -u {USER} -p {PASS} -d -accepteula {cmd_quoted}'
            
            try:
                stdin, stdout, stderr = client.exec_command(psexec_cmd, timeout=10)
                output = stdout.read().decode('utf-8', errors='ignore').strip()
                error = stderr.read().decode('utf-8', errors='ignore').strip()
                
                client.close()
                
                debug_info = f"📋 DEBUG INFO:\n"
                debug_info += f"Command sent: {psexec_cmd}\n"
                debug_info += f"Stdout: {output}\n"
                debug_info += f"Stderr: {error}\n"
                
                if error and ('ERROR' in error or 'denied' in error.lower()):
                    return f"⚠️ Σφάλμα psexec:\n{error}\n\n{debug_info}"
                
                return f"✓ Πρόγραμμα εκτελέστηκε με psexec\n{debug_info}"
                
            except Exception as psexec_err:
                client.close()
                return f"⚠️ Exception στο psexec: {psexec_err}"
        else:
            # Για κανονικές εντολές που τερματίζουν, περιμένουμε το αποτέλεσμα
            stdin, stdout, stderr = client.exec_command(cmd, timeout=25)

            output = stdout.read().decode('utf-8', errors='ignore').strip()
            error = stderr.read().decode('utf-8', errors='ignore').strip()

            client.close()

            if error:
                 return f"Error output:\n{error}\n\nStandard output:\n{output}"
            
            return output if output else "Εντολή εκτελέστηκε (χωρίς έξοδο)"
        
    except paramiko.AuthenticationException:
        return f'❌ SSH Error: Λάθος username ή password για {HOST}'
    except paramiko.SSHException as ssh_err:
        return f'❌ SSH Error: {ssh_err}'
    except TimeoutError:
        return f'❌ Timeout: Δεν απαντά το {HOST}:{PORT} (SSH server offline;)'
    except ConnectionRefusedError:
        return f'❌ Connection Refused: Το {HOST}:{PORT} αρνήθηκε τη σύνδεση'
    except OSError as os_err:
        # Socket errors, network unreachable, etc.
        return f'❌ Network Error: {os_err}'
    except Exception as e:
        return f'❌ Unexpected Error: {type(e).__name__}: {e}'


# ---------- Screens ----------

class MainScreen(Screen):
    """Κεντρική οθόνη με φωνητικές εντολές και μενού προσταγμάτων."""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.speech_recognizer = None
        self.build_ui()
    
    def build_ui(self):
        layout = BoxLayout(orientation='vertical', padding=20, spacing=15)
        
        # Τίτλος
        title = Label(text='🎤 VoiceSSH', font_size='28sp', 
                      size_hint_y=None, height=50, bold=True)
        layout.add_widget(title)
        
        # ----- Μενού Προσταγμάτων -----
        menu_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=50, spacing=10)
        
        # Dropdown για γρήγορη εκτέλεση
        self.dropdown = DropDown()
        self.main_btn = Button(text='⚡ Εκτέλεση Εντολής', size_hint_x=0.6, font_size='16sp')
        self.main_btn.bind(on_release=self.open_dropdown)
        menu_layout.add_widget(self.main_btn)
        
        # Κουμπί διαχείρισης
        manage_btn = Button(text='⚙️ Διαχείριση', size_hint_x=0.4, font_size='16sp')
        manage_btn.bind(on_release=self.go_to_commands_list)
        menu_layout.add_widget(manage_btn)
        
        layout.add_widget(menu_layout)
        
        # ----- Status & Output -----
        self.status_lbl = Label(text='Πάτησε για να ακούσω',
                                font_size='20sp', size_hint_y=0.3)
        layout.add_widget(self.status_lbl)

        self.output_lbl = Label(text='', halign='left',
                                valign='top', font_size='16sp', size_hint_y=0.5)
        self.output_lbl.bind(size=self._update_text_size)
        layout.add_widget(self.output_lbl)

        # ----- Κουμπί Φωνητικής Εντολής -----
        btn = Button(text='🎙️ Πάτησε για φωνητική εντολή',
                     size_hint_y=None, height=70, font_size='20sp')
        btn.bind(on_release=self.start_listening)
        layout.add_widget(btn)

        self.add_widget(layout)
    
    def _update_text_size(self, instance, value):
        instance.text_size = (instance.width - 20, None)
    
    def on_enter(self):
        """Κάθε φορά που μπαίνουμε στην οθόνη, ανανεώνουμε το dropdown."""
        self.refresh_dropdown()
    
    def open_dropdown(self, btn):
        self.refresh_dropdown()
        self.dropdown.open(btn)
    
    def refresh_dropdown(self):
        """Ανανέωση dropdown με τα τρέχοντα commands από τη βάση."""
        self.dropdown.clear_widgets()
        commands = database.get_all_commands()
        
        for cmd in commands:
            item = Button(text=f"▶ {cmd['name']}", size_hint_y=None, height=44)
            item.cmd_data = cmd
            item.bind(on_release=self.execute_from_dropdown)
            self.dropdown.add_widget(item)
        
        if not commands:
            no_cmd = Button(text="(Κανένα πρόσταγμα)", size_hint_y=None, height=44)
            self.dropdown.add_widget(no_cmd)
    
    def execute_from_dropdown(self, btn):
        """Εκτέλεση εντολής από το dropdown."""
        self.dropdown.dismiss()
        cmd = btn.cmd_data
        self.status_lbl.text = f'Εκτέλεση: {cmd["name"]}'
        self.output_lbl.text = f'⚙️ Εκτέλεση: {cmd["executable"]}\n\n'
        output = run_remote(cmd['executable'])
        self.output_lbl.text += f'Output:\n{output}'
    
    def go_to_commands_list(self, btn):
        """Μετάβαση στη λίστα προσταγμάτων."""
        self.manager.current = 'commands_list'
    
    def cleanup_recognizer(self):
        """Καθαρισμός του SpeechRecognizer στο UI thread"""
        if platform != 'android':
            return
            
        class CleanupRunnable(PythonJavaClass):
            __javainterfaces__ = ['java/lang/Runnable']
            
            def __init__(self, app_ref):
                super().__init__()
                self.app_ref = app_ref
            
            @java_method('()V')
            def run(self):
                if self.app_ref.speech_recognizer:
                    try:
                        self.app_ref.speech_recognizer.stopListening()
                        self.app_ref.speech_recognizer.destroy()
                    except:
                        pass
                    self.app_ref.speech_recognizer = None
        
        runnable = CleanupRunnable(self)
        activity.runOnUiThread(runnable)

    def start_listening(self, *args):
        if platform != 'android':
            # Testing mode - εκτέλεση δοκιμαστικής εντολής
            commands = database.get_commands_dict()
            if 'κείμενο' in commands:
                self.handle_command('κείμενο')
            self.status_lbl.text = 'Δοκίμασε στο Android!'
            return

        try:
            self.status_lbl.text = 'Ακούω...'
            
            # Δημιουργία Intent
            intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
            intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL,
                            RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE, 'el-GR')
            intent.putExtra(RecognizerIntent.EXTRA_PROMPT, 'Πες την εντολή σου')

            app_ref = self  # Αναφορά στο MainScreen instance

            # Σωστή υλοποίηση RecognitionListener με PythonJavaClass
            class RecognitionListener(PythonJavaClass):
                __javainterfaces__ = ['android/speech/RecognitionListener']

                @java_method('(Landroid/os/Bundle;)V')
                def onReadyForSpeech(self, params):
                    Clock.schedule_once(lambda dt: setattr(app_ref.status_lbl, 'text', 'Έτοιμος...'), 0)

                @java_method('()V')
                def onBeginningOfSpeech(self):
                    Clock.schedule_once(lambda dt: setattr(app_ref.status_lbl, 'text', 'Μιλάς...'), 0)

                @java_method('(F)V')
                def onRmsChanged(self, rmsdB):
                    pass

                @java_method('(Landroid/os/Bundle;)V')
                def onBufferReceived(self, buffer):
                    pass

                @java_method('()V')
                def onEndOfSpeech(self):
                    Clock.schedule_once(lambda dt: setattr(app_ref.status_lbl, 'text', 'Επεξεργάζομαι...'), 0)

                @java_method('(I)V')
                def onError(self, error):
                    error_msgs = {
                        SpeechRecognizer.ERROR_AUDIO: "Σφάλμα ήχου",
                        SpeechRecognizer.ERROR_CLIENT: "Σφάλμα client",
                        SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS: "Δεν έχω άδεια!",
                        SpeechRecognizer.ERROR_NETWORK: "Σφάλμα δικτύου",
                        SpeechRecognizer.ERROR_NO_MATCH: "Δεν βρέθηκε αντιστοίχιση",
                        SpeechRecognizer.ERROR_RECOGNIZER_BUSY: "Busy",
                        SpeechRecognizer.ERROR_SERVER: "Σφάλμα server",
                        SpeechRecognizer.ERROR_SPEECH_TIMEOUT: "Timeout"
                    }
                    error_msg = error_msgs.get(error, f"Σφάλμα {error}")
                    Clock.schedule_once(lambda dt: setattr(app_ref.status_lbl, 'text', f'❌ {error_msg}'), 0)
                    # Καθαρισμός του recognizer στο UI thread
                    app_ref.cleanup_recognizer()

                @java_method('(Landroid/os/Bundle;)V')
                def onResults(self, results):
                    matches = results.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                    if matches and matches.size() > 0:
                        text = str(matches.get(0))
                        Clock.schedule_once(lambda dt: app_ref.handle_command(text), 0)
                    else:
                        Clock.schedule_once(lambda dt: setattr(app_ref.status_lbl, 'text', 'Δε βρέθηκε κείμενο'), 0)
                    # Καθαρισμός του recognizer στο UI thread
                    app_ref.cleanup_recognizer()

                @java_method('(Landroid/os/Bundle;)V')
                def onPartialResults(self, partialResults):
                    pass

                @java_method('(I)V')
                def onEvent(self, eventType, params):
                    pass

            # Δημιουργία Runnable για εκτέλεση στο main thread
            Runnable = autoclass('java.lang.Runnable')
            
            class SpeechRunnable(PythonJavaClass):
                __javainterfaces__ = ['java/lang/Runnable']
                
                def __init__(self, listener, intent):
                    super().__init__()
                    self.listener = listener
                    self.intent = intent
                
                @java_method('()V')
                def run(self):
                    # Καθαρισμός παλιού recognizer αν υπάρχει
                    if app_ref.speech_recognizer:
                        try:
                            app_ref.speech_recognizer.stopListening()
                            app_ref.speech_recognizer.destroy()
                        except:
                            pass
                    
                    sr = SpeechRecognizer.createSpeechRecognizer(activity)
                    app_ref.speech_recognizer = sr  # Αποθήκευση αναφοράς
                    sr.setRecognitionListener(self.listener)
                    sr.startListening(self.intent)
            
            listener = RecognitionListener()
            runnable = SpeechRunnable(listener, intent)
            
            # Εκτέλεση στο Android UI thread
            activity.runOnUiThread(runnable)
            
        except Exception as e:
            self.status_lbl.text = f'Εξαίρεση: {str(e)}'
            self.output_lbl.text = f'Σφάλμα κατά την εκκίνηση: {str(e)}'

    def handle_command(self, recognized_text):
        self.status_lbl.text = f'Αναγνωρίστηκε: "{recognized_text}"'
        # Συνήθης προσαρμογή για ελληνική ορθογραφία
        recognized_text = recognized_text.strip().lower()
        
        # Χρήση βάσης δεδομένων
        commands = database.get_commands_dict()
        cmd = commands.get(recognized_text)
        
        if cmd is None:
            self.output_lbl.text = f'❌ Δεν αναγνωρίστηκε εντολή: "{recognized_text}"'
            return

        self.output_lbl.text = f'⚙️ Εκτέλεση: {cmd}\n\n'
        # Αποστολή SSH
        output = run_remote(cmd)
        self.output_lbl.text += f'Output:\n{output}'


class CommandsListScreen(Screen):
    """Οθόνη λίστας προσταγμάτων με CRUD."""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.build_ui()
    
    def build_ui(self):
        main_layout = BoxLayout(orientation='vertical', padding=15, spacing=10)
        
        # Header
        header = BoxLayout(orientation='horizontal', size_hint_y=None, height=50)
        back_btn = Button(text='← Πίσω', size_hint_x=0.3, font_size='16sp')
        back_btn.bind(on_release=self.go_back)
        header.add_widget(back_btn)
        
        title = Label(text='📋 Προστάγματα', font_size='22sp', size_hint_x=0.4)
        header.add_widget(title)
        
        add_btn = Button(text='+ Νέο', size_hint_x=0.3, font_size='16sp')
        add_btn.bind(on_release=self.add_command)
        header.add_widget(add_btn)
        
        main_layout.add_widget(header)
        
        # Scrollable list
        scroll = ScrollView(size_hint=(1, 1))
        self.list_layout = GridLayout(cols=1, spacing=8, size_hint_y=None)
        self.list_layout.bind(minimum_height=self.list_layout.setter('height'))
        scroll.add_widget(self.list_layout)
        main_layout.add_widget(scroll)
        
        self.add_widget(main_layout)
    
    def on_enter(self):
        """Ανανέωση λίστας κάθε φορά που μπαίνουμε."""
        self.refresh_list()
    
    def refresh_list(self):
        """Φόρτωση commands από βάση."""
        self.list_layout.clear_widgets()
        commands = database.get_all_commands()
        
        for cmd in commands:
            item = BoxLayout(orientation='horizontal', size_hint_y=None, height=60, spacing=5)
            
            # Info
            info_layout = BoxLayout(orientation='vertical', size_hint_x=0.5)
            name_lbl = Label(text=cmd['name'], font_size='18sp', halign='left')
            name_lbl.bind(size=lambda inst, val: setattr(inst, 'text_size', (inst.width, None)))
            exec_lbl = Label(text=cmd['executable'][:40] + '...' if len(cmd['executable']) > 40 else cmd['executable'],
                            font_size='12sp', halign='left', color=(0.7, 0.7, 0.7, 1))
            exec_lbl.bind(size=lambda inst, val: setattr(inst, 'text_size', (inst.width, None)))
            info_layout.add_widget(name_lbl)
            info_layout.add_widget(exec_lbl)
            item.add_widget(info_layout)
            
            # Κουμπιά
            edit_btn = Button(text='✏️', size_hint_x=0.15, font_size='20sp')
            edit_btn.cmd_id = cmd['id']
            edit_btn.bind(on_release=self.edit_command)
            item.add_widget(edit_btn)
            
            exec_btn = Button(text='▶', size_hint_x=0.15, font_size='20sp')
            exec_btn.cmd_data = cmd
            exec_btn.bind(on_release=self.execute_command)
            item.add_widget(exec_btn)
            
            del_btn = Button(text='🗑️', size_hint_x=0.2, font_size='20sp')
            del_btn.cmd_id = cmd['id']
            del_btn.cmd_name = cmd['name']
            del_btn.bind(on_release=self.confirm_delete)
            item.add_widget(del_btn)
            
            self.list_layout.add_widget(item)
        
        if not commands:
            no_cmd = Label(text='Δεν υπάρχουν προστάγματα.\nΠάτησε "+ Νέο" για να προσθέσεις.',
                          font_size='16sp', size_hint_y=None, height=100)
            self.list_layout.add_widget(no_cmd)
    
    def go_back(self, btn):
        self.manager.current = 'main'
    
    def add_command(self, btn):
        """Μετάβαση στη φόρμα προσθήκης."""
        edit_screen = self.manager.get_screen('command_edit')
        edit_screen.set_mode('add')
        self.manager.current = 'command_edit'
    
    def edit_command(self, btn):
        """Μετάβαση στη φόρμα επεξεργασίας."""
        edit_screen = self.manager.get_screen('command_edit')
        edit_screen.set_mode('edit', btn.cmd_id)
        self.manager.current = 'command_edit'
    
    def execute_command(self, btn):
        """Εκτέλεση εντολής."""
        cmd = btn.cmd_data
        # Popup με αποτέλεσμα
        content = BoxLayout(orientation='vertical', padding=10, spacing=10)
        result_lbl = Label(text=f'⚙️ Εκτέλεση: {cmd["executable"]}...', font_size='14sp')
        content.add_widget(result_lbl)
        
        close_btn = Button(text='Κλείσιμο', size_hint_y=None, height=50)
        content.add_widget(close_btn)
        
        popup = Popup(title=f'Εκτέλεση: {cmd["name"]}',
                     content=content, size_hint=(0.9, 0.5))
        close_btn.bind(on_release=popup.dismiss)
        popup.open()
        
        # Εκτέλεση
        def do_execute(dt):
            output = run_remote(cmd['executable'])
            result_lbl.text = f'Output:\n{output}'
        Clock.schedule_once(do_execute, 0.1)
    
    def confirm_delete(self, btn):
        """Επιβεβαίωση διαγραφής."""
        content = BoxLayout(orientation='vertical', padding=15, spacing=15)
        content.add_widget(Label(text=f'Διαγραφή του "{btn.cmd_name}";', font_size='18sp'))
        
        buttons = BoxLayout(orientation='horizontal', spacing=10, size_hint_y=None, height=50)
        cancel_btn = Button(text='Ακύρωση', font_size='16sp')
        delete_btn = Button(text='Διαγραφή', font_size='16sp', 
                           background_color=(1, 0.3, 0.3, 1))
        delete_btn.cmd_id = btn.cmd_id
        buttons.add_widget(cancel_btn)
        buttons.add_widget(delete_btn)
        content.add_widget(buttons)
        
        popup = Popup(title='Επιβεβαίωση', content=content, size_hint=(0.8, 0.4))
        cancel_btn.bind(on_release=popup.dismiss)
        
        def do_delete(btn_instance):
            database.delete_command(btn_instance.cmd_id)
            popup.dismiss()
            self.refresh_list()
        
        delete_btn.bind(on_release=do_delete)
        popup.open()


class CommandEditScreen(Screen):
    """Οθόνη επεξεργασίας/προσθήκης προστάγματος."""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.mode = 'add'
        self.command_id = None
        self.build_ui()
    
    def build_ui(self):
        main_layout = BoxLayout(orientation='vertical', padding=20, spacing=15)
        
        # Header
        header = BoxLayout(orientation='horizontal', size_hint_y=None, height=50)
        back_btn = Button(text='← Ακύρωση', size_hint_x=0.4, font_size='16sp')
        back_btn.bind(on_release=self.go_back)
        header.add_widget(back_btn)
        
        self.title_lbl = Label(text='Νέο Πρόσταγμα', font_size='20sp', size_hint_x=0.6)
        header.add_widget(self.title_lbl)
        main_layout.add_widget(header)
        
        # Form
        form = BoxLayout(orientation='vertical', spacing=15)
        
        form.add_widget(Label(text='Όνομα Προστάγματος:', font_size='16sp', 
                             size_hint_y=None, height=30, halign='left'))
        self.name_input = TextInput(hint_text='π.χ. μουσική', font_size='18sp',
                                   multiline=False, size_hint_y=None, height=50)
        form.add_widget(self.name_input)
        
        form.add_widget(Label(text='Εντολή/Εκτελέσιμο:', font_size='16sp',
                             size_hint_y=None, height=30, halign='left'))
        self.exec_input = TextInput(hint_text='π.χ. C:\\Program Files\\App.exe', 
                                   font_size='16sp', multiline=True, size_hint_y=None, height=100)
        form.add_widget(self.exec_input)
        
        main_layout.add_widget(form)
        
        # Error label
        self.error_lbl = Label(text='', font_size='14sp', color=(1, 0.3, 0.3, 1),
                              size_hint_y=None, height=30)
        main_layout.add_widget(self.error_lbl)
        
        # Spacer
        main_layout.add_widget(BoxLayout())
        
        # Save button
        save_btn = Button(text='💾 Αποθήκευση', size_hint_y=None, height=60, font_size='20sp')
        save_btn.bind(on_release=self.save_command)
        main_layout.add_widget(save_btn)
        
        self.add_widget(main_layout)
    
    def set_mode(self, mode, command_id=None):
        """Ρύθμιση τρόπου λειτουργίας (add/edit)."""
        self.mode = mode
        self.command_id = command_id
        self.error_lbl.text = ''
        
        if mode == 'edit' and command_id:
            cmd = database.get_command(command_id)
            if cmd:
                self.title_lbl.text = 'Επεξεργασία'
                self.name_input.text = cmd['name']
                self.exec_input.text = cmd['executable']
        else:
            self.title_lbl.text = 'Νέο Πρόσταγμα'
            self.name_input.text = ''
            self.exec_input.text = ''
    
    def go_back(self, btn):
        self.manager.current = 'commands_list'
    
    def save_command(self, btn):
        """Αποθήκευση στη βάση."""
        name = self.name_input.text.strip()
        executable = self.exec_input.text.strip()
        
        if not name:
            self.error_lbl.text = 'Το όνομα είναι υποχρεωτικό!'
            return
        if not executable:
            self.error_lbl.text = 'Η εντολή είναι υποχρεωτική!'
            return
        
        if self.mode == 'add':
            result = database.add_command(name, executable)
            if result is None:
                self.error_lbl.text = f'Το πρόσταγμα "{name}" υπάρχει ήδη!'
                return
        else:
            result = database.update_command(self.command_id, name, executable)
            if not result:
                self.error_lbl.text = 'Αποτυχία ενημέρωσης (ίσως υπάρχει ήδη αυτό το όνομα)'
                return
        
        self.manager.current = 'commands_list'


# ---------- Kivy App ----------
class VoiceSSHApp(App):
    def build(self):
        # Αίτηση αδειών για Android (API 23+)
        if platform == 'android':
            request_permissions([Permission.RECORD_AUDIO, Permission.INTERNET])
        
        # Αρχικοποίηση βάσης δεδομένων
        database.init_db()

        # Screen Manager
        sm = ScreenManager()
        sm.add_widget(MainScreen(name='main'))
        sm.add_widget(CommandsListScreen(name='commands_list'))
        sm.add_widget(CommandEditScreen(name='command_edit'))
        
        return sm


# ---------- Run ----------
if __name__ == '__main__':
    VoiceSSHApp().run()
