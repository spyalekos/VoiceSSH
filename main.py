# main.py
import sys
import io
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.utils import platform
import paramiko

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
# ϛ. 2-3 lines
COMMANDS = {
    "σημειώσεις": "notepad.exe",
    "δίκτυο": "ipconfig.exe",
    "μουσική": r"C:\Program Files\Audacity\Audacity.exe",
    "κείμενο": r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE",
    "εξέταση": "explorer.exe",

}

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

# ---------- Kivy UI ----------
class VoiceSSHApp(App):
    def build(self):
        # Αίτηση αδειών για Android (API 23+)
        if platform == 'android':
            request_permissions([Permission.RECORD_AUDIO, Permission.INTERNET])

        # Αποθήκευση αναφοράς για το SpeechRecognizer
        self.speech_recognizer = None

        self.root = BoxLayout(orientation='vertical', padding=20, spacing=20)

        self.status_lbl = Label(text='Πάτησε για να ακούσω',
                                font_size='20sp', size_hint_y=1)
        self.root.add_widget(self.status_lbl)

        self.output_lbl = Label(text='', halign='left',
                                valign='top', font_size='18sp', size_hint_y=1)
        self.root.add_widget(self.output_lbl)

        btn = Button(text='Πάτησε για φωνητική εντολή',
                     size_hint_y=None, height=60, font_size='18sp')
        btn.bind(on_release=self.start_listening)
        self.root.add_widget(btn)

        return self.root

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
            #alexei
            self.handle_command("κείμενο")
            self.handle_command("μουσική")
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

            app_ref = self  # Αναφορά στο VoiceSSHApp instance

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
        cmd = COMMANDS.get(recognized_text)
        if cmd is None:
            self.output_lbl.text = f'❌ Δεν αναγνωρίστηκε εντολή: "{recognized_text}"'
            return

        self.output_lbl.text = f'⚙️ Εκτέλεση: {cmd}\n\n'
        # Αποστολή SSH
        output = run_remote(cmd)
        self.output_lbl.text += f'Output:\n{output}'

# ---------- Run ----------
if __name__ == '__main__':
    VoiceSSHApp().run()
