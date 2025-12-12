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

# ---------- Android-specific imports ----------
# These are only loaded when running on Android to prevent build errors
if platform == 'android':
    from jnius import autoclass
    
    # JSch (SSH) classes
    JSch = autoclass('com.jcraft.jsch.JSch')
    Session = autoclass('com.jcraft.jsch.Session')
    ChannelExec = autoclass('com.jcraft.jsch.ChannelExec')
    ByteArrayInputStream = autoclass('java.io.ByteArrayInputStream')
    InputStreamReader = autoclass('java.io.InputStreamReader')
    BufferedReader = autoclass('java.io.BufferedReader')
    
    # SpeechRecognizer classes
    SpeechRecognizer = autoclass('android.speech.SpeechRecognizer')
    Intent = autoclass('android.content.Intent')
    RecognizerIntent = autoclass('android.speech.RecognizerIntent')
    Context = autoclass('android.content.Context')
    PythonActivity = autoclass('org.kivy.android.PythonActivity')
    activity = PythonActivity.mActivity

# ---------- Constants ----------
HOST = '192.168.0.12'      # Windows IP
PORT = 22
USER = 'alekos'
PASS = '@lekos'          # <-- Μην το hard‑code σε production!
# ϛ. 2-3 lines
COMMANDS = {
    "μουσική": "start C:\Program Files\Audacity\Audacity.exe",
    "σιωπή": "taskkill /IM ""C:\Program Files\Audacity\Audacity.exe"" /F",
    "εξέταση": "dir /s /p",
}

# ---------- Helpers ----------
def run_remote(cmd):
    """
    Εκτελεί εντολή σε Windows μέσω SSH (JSch).
    Returns stdout (string) ή σφάλμα (string).
    """
    try:
        jsch = JSch()
        session: Session = jsch.getSession(USER, HOST, PORT)
        session.setPassword(PASS)
        # Μη ζητάμε να αποδεχτούμε host key
        config = {'StrictHostKeyChecking': 'no'}
        session.setConfig(config)
        session.connect(30000)  # 30s timeout

        channel: ChannelExec = session.openChannel('exec')
        channel.setCommand(cmd)
        channel.setInputStream(None)
        stream = channel.getInputStream()
        channel.connect()

        # Διαβάζουμε output
        reader = BufferedReader(InputStreamReader(stream))
        out = io.StringIO()
        line = reader.readLine()
        while line is not None:
            out.write(line + '\n')
            line = reader.readLine()

        channel.disconnect()
        session.disconnect()

        return out.getvalue().strip()
    except Exception as e:
        return f'Error: {e}'

# ---------- Kivy UI ----------
class VoiceSSHApp(App):
    def build(self):
        self.root = BoxLayout(orientation='vertical', padding=20, spacing=20)

        self.status_lbl = Label(text='Πάτησε για να ακούσω',
                                font_size='20sp', size_hint_y=None, height=50)
        self.root.add_widget(self.status_lbl)

        self.output_lbl = Label(text='', halign='left',
                                valign='top', font_size='18sp', size_hint_y=1)
        self.root.add_widget(self.output_lbl)

        btn = Button(text='Πάτησε για φωνητική εντολή',
                     size_hint_y=None, height=60, font_size='18sp')
        btn.bind(on_release=self.start_listening)
        self.root.add_widget(btn)

        return self.root

    def start_listening(self, *args):
        if platform != 'android':
            self.status_lbl.text = 'Δοκίμασε στο Android!'
            return

        self.status_lbl.text = '...'
        self.status_lbl.text = 'ω...'
        self.status_lbl.text = 'φω...'
        self.status_lbl.text = 'άφω...'
        self.status_lbl.text = 'ράφω...'
        self.status_lbl.text = 'Γράφω...'
        self.status_lbl.text = 'Γράφω...'
        # Δημιουργία Intent
        intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
        intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL,
                        RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
        intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE, 'el-GR')
        intent.putExtra(RecognizerIntent.EXTRA_PROMPT, 'Πες την εντολή σου')

        # Ο listener (Python callback)
        class Listener:
            def onReadyForSpeech(self, params):
                self_ref = self
                Clock.schedule_once(lambda dt: setattr(self_ref, 'status_lbl',
                                                       'Παίρνω τη φωνή...'), 0)

            def onResults(self, bundle):
                self_ref = self
                results = bundle.getStringArrayList(
                    SpeechRecognizer.RESULTS_RECOGNITION)
                if results is None or len(results) == 0:
                    text = 'Δε βρέθηκε κείμενο'
                else:
                    text = results.get(0).decode('utf-8')
                Clock.schedule_once(lambda dt: self_ref.handle_command(text), 0)

            def onError(self, errorCode):
                error_msg = {SpeechRecognizer.ERROR_AUDIO: "Απόακοα",
                             SpeechRecognizer.ERROR_CLIENT: "Client error",
                             SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS: "Permission",
                             SpeechRecognizer.ERROR_NETWORK: "Δίκτυο",
                             SpeechRecognizer.ERROR_NO_MATCH: "No match",
                             SpeechRecognizer.ERROR_RECOGNIZER_BUSY: "Busy",
                             SpeechRecognizer.ERROR_SERVER: "Server",
                             SpeechRecognizer.ERROR_SPEECH_TIMEOUT: "Σφάλμα"} \
                    .get(errorCode, f"Error {errorCode}")
                Clock.schedule_once(lambda dt: setattr(self_ref, 'status_lbl',
                                                       f'Error: {error_msg}'), 0)

        listener = Listener()
        sr = SpeechRecognizer.createSpeechRecognizer(activity)
        sr.setRecognitionListener(listener)
        sr.startListening(intent)

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
