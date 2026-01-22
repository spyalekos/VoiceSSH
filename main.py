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
    Bundle = autoclass('android.os.Bundle')

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

        cmd_lower = cmd.lower().strip()
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
        self.is_listening = False
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
            md_bg_color=MDApp.get_running_app().theme_cls.primary_color,
            disabled=True if platform == 'android' else False  # Disable until TTS is ready
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
    
    def on_leave(self):
        """Clean up when leaving the screen."""
        self.cleanup_recognizer()
    
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
        
        aliases = cmd_data.get('aliases', ['Primary'])
        aliases_str = ', '.join(aliases)
        self.output_lbl.text = f'⛙️ Εκτέλεση: {cmd_data["executable"]} (@{aliases_str})\n\n'
        
        # Run in thread or schedule logic if needed, simple call for now
        Clock.schedule_once(lambda dt: self._run_cmd(cmd_data['executable'], aliases, cmd_data['name']), 0.1)

    def _run_cmd(self, executable, aliases, cmd_name=''):
        """
        Εκτελεί μια εντολή σε έναν ή περισσότερους SSH servers.
        aliases: λίστα από alias strings (π.χ. ['Primary', 'Secondary'])
        """
        import threading
        
        # Αν είναι string αντί για λίστα (backward compatibility)
        if isinstance(aliases, str):
            aliases = [aliases]
        
        results = {}
        threads = []
        
        def execute_on_server(alias):
            """Εκτέλεση σε έναν συγκεκριμένο server."""
            output = run_remote(executable, alias)
            results[alias] = output
        
        # Δημιουργία thread για κάθε server
        for alias in aliases:
            thread = threading.Thread(target=execute_on_server, args=(alias,))
            threads.append(thread)
            thread.start()
        
        # Αναμονή όλων των threads
        for thread in threads:
            thread.join()
        
        # Εμφάνιση αποτελεσμάτων
        output_text = ''
        all_success = True
        any_error= False
        
        for alias in aliases:
            output = results.get(alias, '❌ Κανένα αποτέλεσμα')
            if len(aliases) > 1:
                output_text += f'\n─── Server: {alias} ───\n{output}\n'
            else:
                output_text += f'{output}\n'
            
            # Έλεγχος για errors
            if ('❌' in output or '⚠️' in output or 
                'σφάλμα' in output.lower() or 'error' in output.lower() or
                'denied' in output.lower() or 'αποτυχία' in output.lower() or
                'exception' in output.lower()):
                any_error = True
                all_success = False
        
        self.output_lbl.text += f'Output:\n{output_text}'
        
        # Voice feedback based on command result
        if any_error:
            self.speak_text('υπάρχει πρόβλημα')
        else:
            self.speak_text(f'η εντολή {cmd_name} εκτελέστηκε επιτυχώς')
    
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
        self.is_listening = False
        self.mic_btn.icon = "microphone"
        self.mic_btn.md_bg_color = MDApp.get_running_app().theme_cls.primary_color

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
            if platform == 'android' and not self.tts_initialized:
                self.status_lbl.text = 'Το TTS δεν είναι έτοιμο...'
                return

            self.speak_text('σας ακούω')
            self.status_lbl.text = 'Προετοιμασία...'
            
            # Μικρή καθυστέρηση για να ακουστεί το "σας ακούω" πριν το beep του SpeechRecognizer
            Clock.schedule_once(lambda dt: self._actually_start_listening(), 0.8)

        except Exception as e:
            self.status_lbl.text = f'Εξαίρεση: {str(e)}'
            self.output_lbl.text = f'Σφάλμα κατά την εκκίνηση: {str(e)}'

    def _actually_start_listening(self):
        try:
            self.status_lbl.text = 'Ακούω...'
            self.is_listening = True
            self.mic_btn.icon = "microphone-off"
            self.mic_btn.md_bg_color = [1, 0, 0, 1] # Red when listening
            
            # Δημιουργία Intent
            intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
            intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL,
                            RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE, 'el-GR')
            intent.putExtra(RecognizerIntent.EXTRA_PROMPT, 'Πες την εντολή σου')
            
            # --- Ταχύτητα απόκρισης ---
            # EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS: 
            # Χρόνος σιωπής μετά το τέλος της ομιλίας για να θεωρηθεί ολοκληρωμένη.
            intent.putExtra('android.speech.extra.SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS', 3000)
            
            # EXTRA_SPEECH_INPUT_POSSIBLY_COMPLETE_SILENCE_LENGTH_MILLIS:
            # Χρόνος σιωπής που μπορεί να σημαίνει το τέλος (πιο επιθετικό).
            intent.putExtra('android.speech.extra.SPEECH_INPUT_POSSIBLY_COMPLETE_SILENCE_LENGTH_MILLIS', 2000)
            # --------------------------

            app_ref = self  # Αναφορά στο MainScreen instance

            # Σωστή υλοποίηση RecognitionListener με PythonJavaClass
            class RecognitionListener(PythonJavaClass):
                __javainterfaces__ = ['android/speech/RecognitionListener']

                def __init__(self, main_screen):
                    super().__init__()
                    self.main_screen = main_screen
                    self.silence_timer = None

                def reset_silence_timer(self):
                    """Επαναφορά του χρονομέτρου σιωπής."""
                    if self.silence_timer:
                        self.silence_timer.cancel()
                    self.silence_timer = Clock.schedule_once(self.force_stop, 5.0)

                def force_stop(self, dt):
                    """Αναγκαστική διακοπή αν περάσουν 5 δευτερόλεπτα σιωπής."""
                    if self.main_screen.speech_recognizer:
                        print("Force stopping recognition due to silence...")
                        # Καλούμε το stopListening στο UI thread
                        class StopRunnable(PythonJavaClass):
                            __javainterfaces__ = ['java/lang/Runnable']
                            def __init__(self, sr):
                                super().__init__()
                                self.sr = sr
                            @java_method('()V')
                            def run(self):
                                try:
                                    self.sr.stopListening()
                                except:
                                    pass
                        stop_runnable = StopRunnable(self.main_screen.speech_recognizer)
                        activity.runOnUiThread(stop_runnable)

                @java_method('(Landroid/os/Bundle;)V')
                def onReadyForSpeech(self, params):
                    Clock.schedule_once(lambda dt: setattr(app_ref.status_lbl, 'text', 'Έτοιμος...'), 0)
                    # Ξεκινάμε το χρονόμετρο μόλις είναι έτοιμο το mic (fallback αν δεν μιλήσει καθόλου)
                    Clock.schedule_once(lambda dt: self.reset_silence_timer(), 0)

                @java_method('()V')
                def onBeginningOfSpeech(self):
                    Clock.schedule_once(lambda dt: setattr(app_ref.status_lbl, 'text', 'Μιλάς...'), 0)
                    # Μίλησε, άρα επαναφέρουμε το χρονόμετρο
                    Clock.schedule_once(lambda dt: self.reset_silence_timer(), 0)

                @java_method('(Landroid/os/Bundle;)V')
                def onBufferReceived(self, buffer):
                    pass

                @java_method('()V')
                def onEndOfSpeech(self):
                    if self.silence_timer:
                        self.silence_timer.cancel()
                    Clock.schedule_once(lambda dt: setattr(app_ref.status_lbl, 'text', 'Επεξεργάζομαι...'), 0)

                @java_method('(I)V')
                def onError(self, error):
                    if self.silence_timer:
                        self.silence_timer.cancel()
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
                    if self.silence_timer:
                        self.silence_timer.cancel()
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
                    # Αν έχουμε μερικά αποτελέσματα, επαναφέρουμε το χρονόμετρο
                    Clock.schedule_once(lambda dt: self.reset_silence_timer(), 0)

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
            
            self.recognition_listener = RecognitionListener(self)
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
            
            def on_tts_ready(success, lang_result=None):
                """Called on Kivy main thread when TTS is ready."""
                if success:
                    print('✓ TTS initialized successfully')
                    app_ref.tts_initialized = True
                    
                    # Check language result
                    if lang_result is not None:
                        if lang_result == TextToSpeech.LANG_MISSING_DATA:
                            print('⚠️ Greek language data missing for TTS')
                            app_ref.status_lbl.text = 'Ελληνικά TTS: δεδομένα λείπουν'
                        elif lang_result == TextToSpeech.LANG_NOT_SUPPORTED:
                            print('⚠️ Greek language not supported for TTS')
                            app_ref.status_lbl.text = 'Ελληνικά TTS δεν υποστηρίζονται'
                        else:
                            print('✓ Greek language set successfully')
                            app_ref.status_lbl.text = 'TTS Έτοιμο - Πάτα το μικρόφωνο'
                            # Test TTS with a short phrase
                            Clock.schedule_once(lambda dt: app_ref.speak_text('έτοιμο'), 1.0)
                    
                    app_ref.mic_btn.disabled = False
                else:
                    print('❌ TTS initialization failed')
                    app_ref.status_lbl.text = 'Αποτυχία TTS'
            
            class TTSListener(PythonJavaClass):
                __javainterfaces__ = ['android/speech/tts/TextToSpeech$OnInitListener']
                
                @java_method('(I)V')
                def onInit(self, status):
                    try:
                        print(f'TTS onInit called with status: {status}')
                        success = (status == TextToSpeech.SUCCESS)
                        
                        if success:
                            # Set Greek language
                            locale = Locale('el', 'GR')
                            lang_result = app_ref.tts.setLanguage(locale)
                            print(f'TTS setLanguage result: {lang_result}')
                            
                            # Configure TTS settings
                            app_ref.tts.setPitch(1.0)  # Normal pitch
                            app_ref.tts.setSpeechRate(1.0)  # Normal speed
                            print('TTS pitch and rate configured')
                            
                            Clock.schedule_once(lambda dt: on_tts_ready(True, lang_result), 0)
                        else:
                            Clock.schedule_once(lambda dt: on_tts_ready(False), 0)
                    except Exception as e:
                        print(f'❌ TTS onInit exception: {e}')
                        import traceback
                        traceback.print_exc()
                        Clock.schedule_once(lambda dt: on_tts_ready(False), 0)
            
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
                        print('Creating TTS instance...')
                        self.app.tts = TextToSpeech(activity, self.listener)
                        print('TTS instance created')
                    except Exception as e:
                        print(f'❌ TTS creation error: {e}')
                        import traceback
                        traceback.print_exc()
            
            # Keep reference to prevent garbage collection
            self._tts_listener = TTSListener()
            self.tts_init_runnable = TTSInitRunnable(self, self._tts_listener)
            activity.runOnUiThread(self.tts_init_runnable)
            
        except Exception as e:
            print(f'❌ TTS initialization error: {e}')
            import traceback
            traceback.print_exc()
    
    def speak_text(self, text):
        """Speak text using Android TTS."""
        if platform != 'android':
            print(f'[DEBUG] Cannot speak on {platform} platform: "{text}"')
            return
        
        if not self.tts:
            print('❌ TTS object is None, cannot speak')
            return
            
        if not self.tts_initialized:
            print('❌ TTS not initialized yet, cannot speak')
            return
        
        try:
            print(f'🔊 Attempting to speak: "{text}"')
            
            # Create a Runnable to speak on Android UI thread
            class TTSSpeakRunnable(PythonJavaClass):
                __javainterfaces__ = ['java/lang/Runnable']
                
                def __init__(self, tts_obj, text_to_speak):
                    super().__init__()
                    self.tts_obj = tts_obj
                    self.text_to_speak = text_to_speak
                
                @java_method('()V')
                def run(self):
                    try:
                        print(f'In TTS runnable, about to call speak() for: "{self.text_to_speak}"')
                        
                        # Use HashMap instead of Bundle for parameters
                        HashMap = autoclass('java.util.HashMap')
                        params = HashMap()
                        
                        # Use the 3-parameter speak() method (deprecated but widely compatible)
                        # speak(String text, int queueMode, HashMap<String, String> params)
                        result = self.tts_obj.speak(
                            self.text_to_speak, 
                            TextToSpeech.QUEUE_FLUSH, 
                            params
                        )
                        
                        if result == TextToSpeech.SUCCESS:
                            print(f'✓ TTS speak() returned SUCCESS for: "{self.text_to_speak}"')
                        elif result == TextToSpeech.ERROR:
                            print(f'❌ TTS speak() returned ERROR for: "{self.text_to_speak}"')
                        else:
                            print(f'⚠️ TTS speak() returned unknown code {result} for: "{self.text_to_speak}"')
                            
                    except Exception as e:
                        print(f'❌ TTS speak error in runnable: {e}')
                        import traceback
                        traceback.print_exc()
            
            speak_runnable = TTSSpeakRunnable(self.tts, text)
            activity.runOnUiThread(speak_runnable)
            print(f'TTS speak runnable submitted to UI thread')
            
        except Exception as e:
            print(f'❌ TTS speak error: {e}')
            import traceback
            traceback.print_exc()
    def handle_command(self, recognized_text):
        self.status_lbl.text = f'Αναγνωρίστηκε: "{recognized_text}"'
        # Συνήθης προσαρμογή για ελληνική ορθογραφία
        recognized_text = recognized_text.strip().lower()
        
        # Χρήση βάσης δεδομένων
        cmd_details = database.get_command_details(recognized_text)
        
        if cmd_details is None:
            self.output_lbl.text = f'❌ Δεν αναγνωρίστηκε εντολή: "{recognized_text}"'
            return

        cmd_exec = cmd_details['executable']
        cmd_aliases = cmd_details.get('aliases', ['Primary'])
        cmd_name = cmd_details['name']
        
        aliases_str = ', '.join(cmd_aliases)
        self.output_lbl.text = f'⛙️ Εκτέλεση: {cmd_exec} (@{aliases_str})\n\n'
        
        # Αποστολή SSH
        Clock.schedule_once(lambda dt: self._run_cmd(cmd_exec, cmd_aliases, cmd_name), 0.1)


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
            aliases_str = ', '.join(cmd.get('aliases', ['Primary']))
            # Custom item with icons
            item = TwoLineAvatarIconListItem(
                text=cmd['name'],
                secondary_text=f"{cmd['executable']} (@{aliases_str})",
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
        self.server_checkboxes = {}  # Διεύθυνση {alias: checkbox_widget}
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
        
        # SSH Servers Selector (Αντικατάσταση του alias_btn)
        servers_label = MDLabel(
            text="Επιλέξτε SSH Servers:",
            size_hint_y=None,
            height=dp(30),
            theme_text_color="Secondary"
        )
        form.add_widget(servers_label)
        
        # ScrollView για τα checkboxes
        servers_scroll = MDScrollView(size_hint_y=None, height=dp(150))
        self.servers_list = MDList()
        servers_scroll.add_widget(self.servers_list)
        form.add_widget(servers_scroll)
        
        self.error_lbl = MDLabel(
            text='',
            theme_text_color="Error",
            halign="center"
        )
        form.add_widget(self.error_lbl)
        
        form.add_widget(MDBoxLayout()) # Spacer
        
        layout.add_widget(form)
        self.add_widget(layout)
        
        # Φόρτωση servers και δημιουργία checkbox (on_enter θα ανανεώνει)
        self.refresh_servers_list()
    
    
    def refresh_servers_list(self):
        """Φόρτωση των SSH servers και δημιουργία checkboxes."""
        from kivymd.uix.selectioncontrol import MDCheckbox
        from kivymd.uix.boxlayout import MDBoxLayout
        
        self.servers_list.clear_widgets()
        self.server_checkboxes.clear()
        
        servers = database.get_ssh_connections()
        
        for server in servers:
            alias = server['alias']
            
            # Container για checkbox + label
            item_box = MDBoxLayout(
                orientation='horizontal',
                adaptive_height=True,
                spacing=dp(10),
                padding=[dp(10), dp(5)]
            )
            
            checkbox = MDCheckbox(
                size_hint=(None, None),
                size=(dp(40), dp(40))
            )
            self.server_checkboxes[alias] = checkbox
            
            label = MDLabel(
                text=f"{alias} ({server['host']}:{server['port']})",
                size_hint_y=None,
                height=dp(40)
            )
            
            item_box.add_widget(checkbox)
            item_box.add_widget(label)
            self.servers_list.add_widget(item_box)
    
    def set_mode(self, mode, command_id=None):
        """Ρύθμιση τρόπου λειτουργίας (add/edit)."""
        self.mode = mode
        self.command_id = command_id
        self.error_lbl.text = ''
        self.name_input.error = False # Clear error state
        self.exec_input.error = False # Clear error state
        
        # Αποεπιλογή όλων των checkboxes
        for checkbox in self.server_checkboxes.values():
            checkbox.active = False
        
        if mode == 'edit' and command_id:
            self.toolbar.title = 'Επεξεργασία'
            cmd = database.get_command(command_id)
            if cmd:
                self.name_input.text = cmd['name']
                self.exec_input.text = cmd['executable']
                
                # Επιλογή των σωστών checkboxes
                selected_aliases = cmd.get('aliases', [])
                for alias in selected_aliases:
                    if alias in self.server_checkboxes:
                        self.server_checkboxes[alias].active = True
        else:
            self.toolbar.title = 'Νέο Πρόσταγμα'
            self.name_input.text = ''
            self.exec_input.text = ''
            # Επιλογή Primary by default
            if 'Primary' in self.server_checkboxes:
                self.server_checkboxes['Primary'].active = True
    
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
        
        # Συλλογή επιλεγμένων servers
        selected_aliases = [alias for alias, checkbox in self.server_checkboxes.items() if checkbox.active]
        
        if not selected_aliases:
            self.error_lbl.text = 'Πρέπει να επιλέξετε τουλάχιστον έναν server!'
            return
        
        if self.mode == 'add':
            result = database.add_command(name, executable, selected_aliases)
            if result is None:
                self.error_lbl.text = f'Το πρόσταγμα "{name}" υπάρχει ήδη!'
                return
        else:
            result = database.update_command(self.command_id, name, executable, selected_aliases)
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
            request_permissions([
                Permission.RECORD_AUDIO, 
                Permission.INTERNET,
                Permission.READ_EXTERNAL_STORAGE,
                Permission.WRITE_EXTERNAL_STORAGE
            ])
        
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
    
    def on_start(self):
        """Καλείται όταν ξεκινά η εφαρμογή."""
        # Δέσιμο του back button
        Window.bind(on_keyboard=self.on_keyboard)
        self.exit_dialog = None
    
    def on_keyboard(self, window, key, scancode, codepoint, modifier):
        """
        Χειρισμός του Android back button.
        Returns True αν το event χειρίστηκε (αποτρέπει το default behavior).
        """
        # Back button = key 27 (Escape)
        if key == 27:
            current_screen = self.root.current
            
            # Αν είμαστε στην κεντρική οθόνη, ρωτάμε για έξοδο
            if current_screen == 'main':
                self.show_exit_confirmation()
                return True  # Μην κάνεις το default (έξοδος)
            
            # Αν είμαστε σε άλλη οθόνη, πηγαίνουμε back
            elif current_screen in ['commands_list', 'settings', 'about']:
                self.root.current = 'main'
                return True
            
            elif current_screen == 'command_edit':
                self.root.current = 'commands_list'
                return True
            
            elif current_screen == 'connection_edit':
                self.root.current = 'settings'
                return True
        
        # Για άλλα πλήκτρα, επιτρέπουμε το default behavior
        return False
    
    def show_exit_confirmation(self):
        """Εμφάνιση διαλόγου επιβεβαίωσης εξόδου."""
        if not self.exit_dialog:
            self.exit_dialog = MDDialog(
                title="Έξοδος",
                text="Θέλετε να εγκαταλείψετε την εφαρμογή;",
                buttons=[
                    MDRaisedButton(
                        text="ΟΧΙ",
                        on_release=lambda x: self.exit_dialog.dismiss()
                    ),
                    MDRaisedButton(
                        text="ΝΑΙ",
                        md_bg_color=(1, 0, 0, 1),
                        on_release=lambda x: self.exit_app()
                    ),
                ],
            )
        self.exit_dialog.open()
    
    def exit_app(self):
        """Έξοδος από την εφαρμογή."""
        if self.exit_dialog:
            self.exit_dialog.dismiss()
        self.stop()


# ---------- Run ----------
if __name__ == '__main__':
    VoiceSSHApp().run()
