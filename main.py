# main.py
import sys
import io
from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from settings_screen import SettingsScreen, ConnectionEditScreen
from about_screen import AboutScreen
from kivymd.uix.gridlayout import MDGridLayout
from kivymd.uix.scrollview import MDScrollView
from kivymd.uix.button import MDRaisedButton, MDIconButton, MDRectangleFlatIconButton, MDFloatingActionButton
from kivymd.uix.label import MDLabel
from kivymd.uix.textfield import MDTextField
from kivymd.uix.list import MDList, TwoLineAvatarIconListItem, IconRightWidget, IconLeftWidget, ImageLeftWidget
from kivymd.uix.dialog import MDDialog
from kivymd.uix.menu import MDDropdownMenu
from kivymd.uix.toolbar import MDTopAppBar
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.utils import platform
from kivy.metrics import dp
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
    
    # Text-to-Speech classes
    TextToSpeech = autoclass('android.speech.tts.TextToSpeech')
    Locale = autoclass('java.util.Locale')

# ---------- Constants ----------

# ---------- Helpers ----------
def run_remote(cmd, alias='Primary'):
    """
    Εκτελεί εντολή σε Windows μέσω SSH (Paramiko) χρησιμοποιώντας το συγκεκριμένο alias.
    Returns stdout (string) ή σφάλμα (string).
    """
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        # Load settings for this alias
        conn_details = database.get_ssh_connection(alias)
        if not conn_details:
            return f'❌ Σφάλμα: Δεν βρέθηκαν ρυθμίσεις για το alias "{alias}"'
            
        HOST = conn_details['host']
        PORT = int(conn_details['port'])
        USER = conn_details['username']
        PASS = conn_details['password']

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
        # Καταργώ την Ανίχνευση εντολών που ξεκινούν προγράμματα που μένουν ενεργά
        is_background_cmd=True

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
                
                # Create masked version for return
                masked_debug = debug_info.replace(USER, "***").replace(PASS, "***")
                
                if error and ('ERROR' in error or 'denied' in error.lower()):
                    return f"⚠️ Σφάλμα psexec:\n{error}\n\n{masked_debug}"
                
                return f"✓ Πρόγραμμα εκτελέστηκε με psexec\n{masked_debug}"
                
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
        self.menu = None
        self.tts = None
        self.tts_initialized = False
        self.build_ui()
    
    def build_ui(self):
        layout = MDBoxLayout(orientation='vertical')
        
        # Toolbar
        self.toolbar = MDTopAppBar(title="Φωνητικές Εντολές", elevation=4)
        self.toolbar.md_bg_color=[0,0,1,1]
        self.toolbar.right_action_items = [["file", lambda x: self.go_to_commands_list(x)], ["cog", lambda x: self.go_to_settings(x)], ["information", lambda x: self.go_to_about(x)]]
        self.toolbar.icon_color=[0,0,0,1]
        layout.add_widget(self.toolbar)

        # Content Layout
        content = MDBoxLayout(orientation='vertical', padding=dp(20), spacing=dp(20))
        
        # Quick Commands Menu Button
        menu_layout = MDBoxLayout(orientation='horizontal', adaptive_height=True, spacing=dp(10))
        self.main_btn = MDRectangleFlatIconButton(
            text="Επιλογή Εντολής",
            icon="format-list-bulleted",
            size_hint_x=1,
            pos_hint={'center_x': 0.5}
        )
        self.main_btn.bind(on_release=self.open_menu)
        menu_layout.add_widget(self.main_btn)
        content.add_widget(menu_layout)
        
        # Status Label
        self.status_lbl = MDLabel(
            text='Πάτησε το μικρόφωνο για να ακούσω',
            halign='center',
            theme_text_color="Secondary",
            font_style="H6",
            size_hint_y=0.2
        )
        content.add_widget(self.status_lbl)

        # Output ScrollView
        scroll = MDScrollView(size_hint_y=0.5)
        self.output_lbl = MDLabel(
            text='Αναμονή για εντολή...',
            halign='left',
            valign='top',
            theme_text_color="Primary",
            size_hint_y=None
        )
        self.output_lbl.bind(texture_size=self.output_lbl.setter('size'))
        scroll.add_widget(self.output_lbl)
        content.add_widget(scroll)

        # Microphone FAB
        fab_layout = MDBoxLayout(orientation='vertical', adaptive_height=True, padding=[0, dp(20), 0, 0])
        self.mic_btn = MDFloatingActionButton(
            icon="microphone",
            type="large",
            pos_hint={'center_x': 0.5},
            md_bg_color=MDApp.get_running_app().theme_cls.primary_color
        )
        self.mic_btn.bind(on_release=self.start_listening)
        fab_layout.add_widget(self.mic_btn)
        content.add_widget(fab_layout)

        layout.add_widget(content)
        self.add_widget(layout)
    
    def on_enter(self):
        """Initialize TTS when entering the screen, with debugging."""
        # Initialize TTS on first entry, wrapped in try/except to avoid crashes
        if platform == 'android' and not self.tts_initialized:
            try:
                self.init_tts()
                print('TTS initialization attempted.')
            except Exception as e:
                print(f'TTS initialization failed with exception: {e}')
    
    def open_menu(self, btn):
        commands = database.get_all_commands()
        menu_items = []
        for cmd in commands:
            menu_items.append(
                {
                    "viewclass": "OneLineListItem",
                    "text": cmd['name'],
                    "on_release": lambda x=cmd: self.execute_from_menu(x),
                }
            )
        
        if not menu_items:
            menu_items.append({"viewclass": "OneLineListItem", "text": "(Κανένα πρόσταγμα)"})

        self.menu = MDDropdownMenu(
            caller=btn,
            items=menu_items,
            width_mult=4,
        )
        self.menu.open()
    
    def execute_from_menu(self, cmd_data):
        """Εκτέλεση εντολής από το dropdown."""
        self.menu.dismiss()
        self.status_lbl.text = f'Εκτέλεση: {cmd_data["name"]}'
        self.output_lbl.text = f'⚙️ Εκτέλεση: {cmd_data["executable"]} (@{cmd_data["alias"]})\n\n'
        
        # Run in thread or schedule logic if needed, simple call for now
        Clock.schedule_once(lambda dt: self._run_cmd(cmd_data['executable'], cmd_data['alias']), 0.1)

    def _run_cmd(self, executable, alias='Primary'):
        output = run_remote(executable, alias)
        self.output_lbl.text += f'Output:\n{output}'
        
        # Voice feedback based on command result
        if '❌' in output or 'σφάλμα' in output.lower() or 'error' in output.lower():
            self.speak_text('η εντολή απέτυχε')
        else:
            self.speak_text('η εντολή εκτελέστηκε με επιτυχία')
    
    def go_to_commands_list(self, btn):
        """Μετάβαση στη λίστα προσταγμάτων."""
        self.manager.current = 'commands_list'

    def go_to_settings(self, btn):
        """Μετάβαση στη σελίδα ρυθμίσεων."""
        self.manager.current = 'settings'

    def go_to_about(self, btn):
        """Μετάβαση στη σελίδα πληροφοριών."""
        self.manager.current = 'about'
    
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
        
        self.cleanup_runnable = CleanupRunnable(self)
        activity.runOnUiThread(self.cleanup_runnable)

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
            
            self.recognition_listener = RecognitionListener()
            self.speech_runnable = SpeechRunnable(self.recognition_listener, intent)
            
            # Εκτέλεση στο Android UI thread
            activity.runOnUiThread(self.speech_runnable)
            
        except Exception as e:
            self.status_lbl.text = f'Εξαίρεση: {str(e)}'
            self.output_lbl.text = f'Σφάλμα κατά την εκκίνηση: {str(e)}'
    
    def init_tts(self):
        """Initialize Android Text-to-Speech."""
        if platform != 'android':
            return
        
        try:
            app_ref = self
            
            def on_tts_ready(success):
                """Called on Kivy main thread when TTS is ready."""
                if success:
                    app_ref.tts_initialized = True
                    try:
                        # Set Greek language
                        locale = Locale('el', 'GR')
                        result = app_ref.tts.setLanguage(locale)
                        if result == TextToSpeech.LANG_MISSING_DATA or result == TextToSpeech.LANG_NOT_SUPPORTED:
                            print('Greek language not supported for TTS')
                    except Exception as e:
                        print(f'TTS setLanguage error: {e}')
                else:
                    print('TTS initialization failed')
            
            class TTSListener(PythonJavaClass):
                __javainterfaces__ = ['android/speech/tts/TextToSpeech$OnInitListener']
                
                @java_method('(I)V')
                def onInit(self, status):
                    # Use Clock.schedule_once to run on Kivy's main thread
                    try:
                        success = (status == TextToSpeech.SUCCESS)
                        Clock.schedule_once(lambda dt: on_tts_ready(success), 0)
                    except Exception as e:
                        print(f'TTS onInit exception: {e}')
            
            # Create a Runnable to initialize TTS on Android UI thread
            class TTSInitRunnable(PythonJavaClass):
                __javainterfaces__ = ['java/lang/Runnable']
                
                def __init__(self, app, listener):
                    super().__init__()
                    self.app = app
                    self.listener = listener
                
                @java_method('()V')
                def run(self):
                    try:
                        self.app.tts = TextToSpeech(activity, self.listener)
                    except Exception as e:
                        print(f'TTS creation error: {e}')
            
            # Keep reference to prevent garbage collection
            self._tts_listener = TTSListener()
            self.tts_init_runnable = TTSInitRunnable(self, self._tts_listener)
            activity.runOnUiThread(self.tts_init_runnable)
            
        except Exception as e:
            print(f'TTS initialization error: {e}')
    
    def speak_text(self, text):
        """Speak text using Android TTS."""
        if platform != 'android' or not self.tts or not self.tts_initialized:
            return
        
        try:
            self.tts.speak(text, TextToSpeech.QUEUE_FLUSH, None, None)
        except Exception as e:
            print(f'TTS speak error: {e}')

    def handle_command(self, recognized_text):
        self.status_lbl.text = f'Αναγνωρίστηκε: "{recognized_text}"'
        # Συνήθης προσαρμογή για ελληνική ορθογραφία
        recognized_text = recognized_text.strip().lower()
        
        # Χρήση βάσης δεδομένων
        # Χρήση βάσης δεδομένων
        cmd_details = database.get_command_details(recognized_text)
        
        if cmd_details is None:
            self.output_lbl.text = f'❌ Δεν αναγνωρίστηκε εντολή: "{recognized_text}"'
            return

        cmd_exec = cmd_details['executable']
        cmd_alias = cmd_details['alias']

        self.output_lbl.text = f'⚙️ Εκτέλεση: {cmd_exec} (@{cmd_alias})\n\n'
        # Αποστολή SSH
        Clock.schedule_once(lambda dt: self._run_cmd(cmd_exec, cmd_alias), 0.1)


class CommandsListScreen(Screen):
    """Οθόνη λίστας προσταγμάτων με CRUD."""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.build_ui()
    
    def build_ui(self):
        layout = MDBoxLayout(orientation='vertical')
        
        # Toolbar
        toolbar = MDTopAppBar(title="Διαχείριση", elevation=4)
        toolbar.left_action_items = [["arrow-left", lambda x: self.go_back()]]
        toolbar.right_action_items = [["plus", lambda x: self.add_command()]]
        layout.add_widget(toolbar)
        
        # List in ScrollView
        scroll = MDScrollView()
        self.list_layout = MDList()
        scroll.add_widget(self.list_layout)
        layout.add_widget(scroll)
        
        self.add_widget(layout)
    
    def on_enter(self):
        """Ανανέωση λίστας κάθε φορά που μπαίνουμε."""
        self.refresh_list()
    
    def refresh_list(self):
        """Φόρτωση commands από βάση."""
        self.list_layout.clear_widgets()
        commands = database.get_all_commands()
        
        for cmd in commands:
            # Custom item with icons
            item = TwoLineAvatarIconListItem(
                text=cmd['name'],
                secondary_text=f"{cmd['executable']} ({cmd['alias']})",
                on_release=lambda x, c=cmd: self.edit_command(c['id'])
            )
            
            # Icon Left (Command Icon)
            icon_left = IconLeftWidget(icon="console")
            item.add_widget(icon_left)
            
            # Icon Right (Delete)
            icon_right = IconRightWidget(icon="delete", on_release=lambda x, i=cmd['id'], n=cmd['name']: self.confirm_delete(i, n))
            item.add_widget(icon_right)
            
            self.list_layout.add_widget(item)
        
        if not commands:
            self.list_layout.add_widget(
                TwoLineAvatarIconListItem(
                    text="Δεν υπάρχουν προστάγματα", 
                    secondary_text="Πάτησε το + για προσθήκη"
                )
            )
    
    def go_back(self):
        self.manager.current = 'main'
    
    def add_command(self):
        """Μετάβαση στη φόρμα προσθήκης."""
        edit_screen = self.manager.get_screen('command_edit')
        edit_screen.set_mode('add')
        self.manager.current = 'command_edit'
    
    def edit_command(self, cmd_id):
        """Μετάβαση στη φόρμα επεξεργασίας."""
        edit_screen = self.manager.get_screen('command_edit')
        edit_screen.set_mode('edit', cmd_id)
        self.manager.current = 'command_edit'
    
    def confirm_delete(self, cmd_id, cmd_name):
        """Επιβεβαίωση διαγραφής."""
        self.dialog = MDDialog(
            text=f'Διαγραφή του "{cmd_name}";',
            buttons=[
                MDRaisedButton(
                    text="ΑΚΥΡΩΣΗ",
                    on_release=lambda x: self.dialog.dismiss()
                ),
                MDRaisedButton(
                    text="ΔΙΑΓΡΑΦΗ",
                    md_bg_color=(1, 0.3, 0.3, 1),
                    on_release=lambda x: self.do_delete(cmd_id)
                ),
            ],
        )
        self.dialog.open()
        
    def do_delete(self, cmd_id):
        database.delete_command(cmd_id)
        self.dialog.dismiss()
        self.refresh_list()


class CommandEditScreen(Screen):
    """Οθόνη επεξεργασίας/προσθήκης προστάγματος."""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.mode = 'add'
        self.command_id = None
        self.menu = None
        self.build_ui()
    
    def build_ui(self):
        layout = MDBoxLayout(orientation='vertical')
        
        # Toolbar
        self.toolbar = MDTopAppBar(title="Νέο Πρόσταγμα", elevation=4)
        self.toolbar.left_action_items = [["close", lambda x: self.go_back()]]
        self.toolbar.right_action_items = [["content-save", lambda x: self.save_command()]]
        layout.add_widget(self.toolbar)
        
        # Form
        form = MDBoxLayout(orientation='vertical', padding=dp(20), spacing=dp(20))
        
        self.name_input = MDTextField(
            hint_text="Όνομα Προστάγματος",
            helper_text="π.χ. μουσική",
            helper_text_mode="on_focus",
            mode="rectangle"
        )
        form.add_widget(self.name_input)
        
        self.exec_input = MDTextField(
            hint_text="Εντολή/Εκτελέσιμο",
            helper_text="π.χ. C:\\Program Files\\App.exe",
            helper_text_mode="on_focus",
            mode="rectangle",
            multiline=True
        )
        form.add_widget(self.exec_input)
        
        # Alias Selector
        self.alias_btn = MDRectangleFlatIconButton(
            text="Primary",
            icon="server",
            size_hint_x=1,
            pos_hint={'center_x': 0.5}
        )
        self.alias_btn.bind(on_release=self.open_alias_menu)
        form.add_widget(self.alias_btn)
        
        self.error_lbl = MDLabel(
            text='',
            theme_text_color="Error",
            halign="center"
        )
        form.add_widget(self.error_lbl)
        
        form.add_widget(MDBoxLayout()) # Spacer
        
        layout.add_widget(form)
        self.add_widget(layout)
    
    def open_alias_menu(self, btn):
        aliases = database.get_connection_aliases()
        menu_items = [
            {
                "viewclass": "OneLineListItem",
                "text": alias,
                "on_release": lambda x=alias: self.set_alias(x),
            } for alias in aliases
        ]
        self.menu = MDDropdownMenu(
            caller=btn,
            items=menu_items,
            width_mult=4,
        )
        self.menu.open()

    def set_alias(self, alias):
        self.alias_btn.text = alias
        self.menu.dismiss()

    def set_mode(self, mode, command_id=None):
        """Ρύθμιση τρόπου λειτουργίας (add/edit)."""
        self.mode = mode
        self.command_id = command_id
        self.error_lbl.text = ''
        self.name_input.error = False # Clear error state
        self.exec_input.error = False # Clear error state
        
        if mode == 'edit' and command_id:
            self.toolbar.title = 'Επεξεργασία'
            cmd = database.get_command(command_id)
            if cmd:
                self.name_input.text = cmd['name']
                self.exec_input.text = cmd['executable']
                self.alias_btn.text = cmd.get('alias', 'Primary')
        else:
            self.toolbar.title = 'Νέο Πρόσταγμα'
            self.name_input.text = ''
            self.exec_input.text = ''
            self.alias_btn.text = 'Primary'
    
    def go_back(self):
        self.manager.current = 'commands_list'
    
    def save_command(self):
        """Αποθήκευση στη βάση."""
        name = self.name_input.text.strip()
        executable = self.exec_input.text.strip()
        
        # Reset error states
        self.name_input.error = False
        self.exec_input.error = False
        self.error_lbl.text = ''

        if not name:
            self.name_input.error = True
            self.error_lbl.text = 'Το όνομα είναι υποχρεωτικό!'
            return
        if not executable:
            self.exec_input.error = True
            self.error_lbl.text = 'Η εντολή είναι υποχρεωτική!'
            return
        
        alias = self.alias_btn.text
        
        if self.mode == 'add':
            result = database.add_command(name, executable, alias)
            if result is None:
                self.error_lbl.text = f'Το πρόσταγμα "{name}" υπάρχει ήδη!'
                return
        else:
            result = database.update_command(self.command_id, name, executable, alias)
            if not result:
                self.error_lbl.text = 'Αποτυχία ενημέρωσης (ίσως υπάρχει ήδη αυτό το όνομα)'
                return
        
        self.manager.current = 'commands_list'


# ---------- KivyMD App ----------
class VoiceSSHApp(MDApp):
    def build(self):
        self.theme_cls.primary_palette = "Blue"  # Διάλεξε χρώμα: Teal, Blue, Red, κλπ.
        self.theme_cls.theme_style = "Light"    # ή "Dark"
        
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
        sm.add_widget(SettingsScreen(name='settings'))
        sm.add_widget(ConnectionEditScreen(name='connection_edit'))
        sm.add_widget(AboutScreen(name='about'))
        
        return sm


# ---------- Run ----------
if __name__ == '__main__':
    VoiceSSHApp().run()
