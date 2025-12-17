
from kivymd.app import MDApp
from kivy.uix.screenmanager import Screen
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.scrollview import MDScrollView
from kivymd.uix.label import MDLabel
from kivymd.uix.toolbar import MDTopAppBar
from kivy.metrics import dp

class AboutScreen(Screen):
    """Οθόνη 'About' με τεκμηρίωση για PsExec και SSH."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.build_ui()

    def build_ui(self):
        layout = MDBoxLayout(orientation='vertical')

        # Toolbar
        toolbar = MDTopAppBar(title="Πληροφορίες & Απαιτήσεις", elevation=4)
        toolbar.left_action_items = [["arrow-left", lambda x: self.go_back()]]
        layout.add_widget(toolbar)

        # Content in ScrollView
        scroll = MDScrollView()
        content_layout = MDBoxLayout(
            orientation='vertical',
            padding=dp(20),
            spacing=dp(20),
            size_hint_y=None
        )
        content_layout.bind(minimum_height=content_layout.setter('height'))

        # --- PsExec Section ---
        title1 = MDLabel(
            text="[b]1. Απαίτηση PsExec[/b]",
            markup=True,
            theme_text_color="Primary",
            font_style="H5",
            size_hint_y=None
        )
        title1.bind(texture_size=title1.setter('size'))
        content_layout.add_widget(title1)
        
        psexec_info = (
            "Για την σωστή εκτέλεση γραφικών εφαρμογών (GUI) απομακρυσμένα, η εφαρμογή χρησιμοποιεί το εργαλείο [b]PsExec[/b]. "
            "Αυτό επιτρέπει στις εντολές να τρέχουν στο ενεργό περιβάλλον του χρήστη και όχι στο παρασκήνιο.\n\n"
            "[b]Λήψη:[/b] Κατεβάστε το από την επίσημη σελίδα της Microsoft (Sysinternals).\n\n"
            "[b]Εγκατάσταση:[/b] Αντιγράψτε το αρχείο `psexec.exe` στο φάκελο `C:\\Windows\\System32` στον υπολογιστή Windows που ελέγχετε."
        )
        
        psexec_label = MDLabel(
            text=psexec_info,
            font_style="Body1",
            markup=True,
            theme_text_color="Secondary",
            size_hint_y=None
        )
        psexec_label.bind(
            width=lambda *x: psexec_label.setter('text_size')(psexec_label, (psexec_label.width, None)),
            texture_size=lambda *x: psexec_label.setter('height')(psexec_label, psexec_label.texture_size[1])
        )
        content_layout.add_widget(psexec_label)

        # Spacer
        content_layout.add_widget(MDLabel(text="", size_hint_y=None, height=dp(10)))

        # --- SSH Server Section ---
        title2 = MDLabel(
            text="[b]2. Εγκατάσταση Windows SSH Server[/b]",
            markup=True,
            theme_text_color="Primary",
            font_style="H5",
            size_hint_y=None
        )
        title2.bind(texture_size=title2.setter('size'))
        content_layout.add_widget(title2)

        ssh_info = (
            "Απαιτείται η εγκατάσταση του OpenSSH Server στον υπολογιστή.\n\n"
            "Ανοίξτε το [b]PowerShell ως Διαχειριστής[/b] και εκτελέστε τις παρακάτω εντολές μία προς μία:"
        )

        ssh_label = MDLabel(
            text=ssh_info,
            font_style="Body1",
            markup=True,
            theme_text_color="Secondary",
            size_hint_y=None
        )
        ssh_label.bind(
            width=lambda *x: ssh_label.setter('text_size')(ssh_label, (ssh_label.width, None)),
            texture_size=lambda *x: ssh_label.setter('height')(ssh_label, ssh_label.texture_size[1])
        )
        content_layout.add_widget(ssh_label)

        # Code block styling for commands
        commands = [
            "# 1. Εγκατάσταση OpenSSH Server",
            "Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0",
            "",
            "# 2. Εκκίνηση της υπηρεσίας (Service)",
            "Start-Service sshd",
            "",
            "# 3. Αυτόματη εκκίνηση με τα Windows",
            "Set-Service -Name sshd -StartupType 'Automatic'",
            "",
            "# 4. (Προαιρετικό) Άνοιγμα Firewall",
            "New-NetFirewallRule -Name sshd -DisplayName 'OpenSSH Server (sshd)' -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22"
        ]
        
        code_text = "\n".join(commands)

        code_label = MDLabel(
            text=code_text,
            font_style="Body1",
            theme_text_color="Primary",
            size_hint_y=None,
            font_name="RobotoMono-Regular"
        )
        code_label.bind(
            width=lambda *x: code_label.setter('text_size')(code_label, (code_label.width, None)),
            texture_size=lambda *x: code_label.setter('height')(code_label, code_label.texture_size[1])
        )
        content_layout.add_widget(code_label)

        # Bottom padding
        content_layout.add_widget(MDLabel(text="", size_hint_y=None, height=dp(20)))

        scroll.add_widget(content_layout)
        layout.add_widget(scroll)

        self.add_widget(layout)

    def go_back(self):
        """Επιστροφή στην κεντρική οθόνη."""
        self.manager.current = 'main'
