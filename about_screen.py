
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
            spacing=dp(15),
            size_hint_y=None,
            adaptive_height=True
        )

        # --- PsExec Section ---
        content_layout.add_widget(
            MDLabel(
                text="[b]1. Απαίτηση PsExec[/b]",
                markup=True,
                theme_text_color="Primary",
                font_style="H6",
                size_hint_y=None,
                height=dp(30)
            )
        )
        
        psexec_info = (
            "Για την σωστή εκτέλεση γραφικών εφαρμογών (GUI) απομακρυσμένα, η εφαρμογή χρησιμοποιεί το εργαλείο [b]PsExec[/b]. "
            "Αυτό επιτρέπει στις εντολές να τρέχουν στο ενεργό περιβάλλον του χρήστη και όχι στο παρασκήνιο.\n\n"
            "[b]Λήψη:[/b] Κατεβάστε το από την επίσημη σελίδα της Microsoft (Sysinternals).\n"
            "[b]Εγκατάσταση:[/b] Αντιγράψτε το αρχείο `psexec.exe` στο φάκελο `C:\\Windows\\System32` στον υπολογιστή Windows που ελέγχετε."
        )
        
        content_layout.add_widget(
            MDLabel(
                text=psexec_info,
                font_style="Caption",
                markup=True,
                theme_text_color="Secondary",
                size_hint_y=None,
                height=dp(220)  # Estimated height
            )
        )

        # --- SSH Server Section ---
        content_layout.add_widget(
            MDLabel(
                text="[b]2. Εγκατάσταση Windows SSH Server[/b]",
                markup=True,
                theme_text_color="Primary",
                font_style="H6",
                size_hint_y=None,
                height=dp(30)
            )
        )

        ssh_info = (
            "Απαιτείται η εγκατάσταση του OpenSSH Server στον υπολογιστή.\n"
            "Ανοίξτε το [b]PowerShell ως Διαχειριστής[/b] και εκτελέστε τις παρακάτω εντολές μία προς μία:"
        )

        content_layout.add_widget(
            MDLabel(
                text=ssh_info,
                markup=True,
                theme_text_color="Secondary",
                size_hint_y=None,
                height=dp(60)
            )
        )

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

        # A "card-like" background for code could be nice, but a label with distinct font is simpler for now
        content_layout.add_widget(
            MDLabel(
                text=f"{code_text}",
                font_style="Caption",
                theme_text_color="Primary",
                size_hint_y=None,
                # padding=(dp(10), dp(10)),
                height=dp(250)  # Approx height for multiple lines
            )
        )

        scroll.add_widget(content_layout)
        layout.add_widget(scroll)

        self.add_widget(layout)

    def go_back(self):
        """Επιστροφή στην κεντρική οθόνη."""
        self.manager.current = 'main'
