# database.py
"""
SQLite database module για διαχείριση προσταγμάτων (commands) και πολλαπλών SSH servers.
"""
import sqlite3
import os
import json
from kivy.utils import platform

# Ορισμός path για τη βάση δεδομένων
if platform == 'android':
    from android.storage import app_storage_path
    DB_PATH = os.path.join(app_storage_path(), 'commands.db')
else:
    DB_PATH = os.path.join(os.path.dirname(__file__), 'commands.db')

# Default commands - θα χρησιμοποιηθούν για αρχικοποίηση
DEFAULT_COMMANDS = {
    "σημειώσεις": "notepad.exe",
    "δίκτυο": "ipconfig.exe",
    "μουσική": r"C:\Program Files\Audacity\Audacity.exe",
    "κείμενο": r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE",
    "εξέταση": "explorer.exe",
}

DEFAULT_ALIAS = "Primary"

def get_connection():
    """Επιστρέφει σύνδεση στη βάση δεδομένων."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """
    Αρχικοποίηση της βάσης δεδομένων.
    Δημιουργεί τους πίνακες και κάνει migrations αν χρειαστεί.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    # 1. Πίνακας commands
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS commands (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            executable TEXT NOT NULL,
            alias TEXT DEFAULT 'Primary',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Check if 'alias' column exists in commands (Migration)
    cursor.execute("PRAGMA table_info(commands)")
    columns = [info[1] for info in cursor.fetchall()]
    if 'alias' not in columns:
        cursor.execute(f"ALTER TABLE commands ADD COLUMN alias TEXT DEFAULT '{DEFAULT_ALIAS}'")

    # 2. Πίνακας ssh_connections (Settings)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ssh_connections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alias TEXT UNIQUE NOT NULL,
            host TEXT NOT NULL,
            port INTEGER NOT NULL,
            username TEXT NOT NULL,
            password TEXT
        )
    ''')

    # 3. Migration από παλιά settings (key/value) αν υπάρχουν
    # Αν το table settings υπάρχει, βλέπουμε αν έχει data
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='settings'")
    if cursor.fetchone():
        # Διαβάζουμε τα παλιά settings
        old_settings = {}
        try:
            cursor.execute("SELECT key, value FROM settings")
            rows = cursor.fetchall()
            if rows:
                for row in rows:
                    old_settings[row['key']] = row['value']
                
                # Αν έχουμε host, τα μεταφέρουμε στο ssh_connections ως 'Primary'
                if 'host' in old_settings:
                    try:
                        cursor.execute(
                            '''INSERT INTO ssh_connections (alias, host, port, username, password) 
                               VALUES (?, ?, ?, ?, ?)''',
                            (
                                DEFAULT_ALIAS,
                                old_settings.get('host', ''),
                                int(old_settings.get('port', 22)),
                                old_settings.get('username', ''),
                                old_settings.get('password', '')
                            )
                        )
                    except sqlite3.IntegrityError:
                        pass # Ήδη υπάρχει
        except Exception as e:
            print(f"Migration error: {e}")

    # 4. Default commands αν ο πίνακας commands είναι κενός
    cursor.execute('SELECT COUNT(*) FROM commands')
    if cursor.fetchone()[0] == 0:
        for name, executable in DEFAULT_COMMANDS.items():
            cursor.execute(
                'INSERT INTO commands (name, executable, alias) VALUES (?, ?, ?)',
                (name, executable, DEFAULT_ALIAS)
            )

    # 5. Default SSH connection αν ο πίνακας είναι κενός
    cursor.execute('SELECT COUNT(*) FROM ssh_connections')
    if cursor.fetchone()[0] == 0:
        cursor.execute(
            '''INSERT INTO ssh_connections (alias, host, port, username, password) 
               VALUES (?, ?, ?, ?, ?)''',
            (DEFAULT_ALIAS, '192.168.0.8', 22, 'alekos', 'alekos')
        )
    
    conn.commit()
    conn.close()


def get_all_commands():
    """
    Επιστρέφει όλα τα προστάγματα.
    Returns: [{'id': 1, 'name': 'foo', 'executable': 'bar', 'alias': 'Primary'}, ...]
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, executable, alias FROM commands ORDER BY name')
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_command_details(name):
    """
    Επιστρέφει τις λεπτομέρειες ενός προστάγματος (μαζί με το executable και το alias).
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT name, executable, alias FROM commands WHERE name = ?', (name,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None
    
def get_commands_dict():
    """
    Διατήρηση συμβατότητας, αλλά τώρα επιστρέφει όλο το αντικείμενο αν χρειαστεί,
    ή αν θέλουμε απλά το exec:
    Αλλά για το main.py χρειάζεται και το alias.
    Οπότε καλύτερα να μην το χρησιμοποιούμε ή να το αναβαθμίσουμε.
    Για την ώρα επιστρέφει {name: executable} για απλότητα όπου χρειάζεται,
    αλλά το handle_command πρέπει να αλλάξει.
    """
    commands = get_all_commands()
    return {cmd['name']: cmd['executable'] for cmd in commands}


def get_command(command_id):
    """Επιστρέφει ένα πρόσταγμα με βάση το ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, executable, alias FROM commands WHERE id = ?', (command_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def add_command(name, executable, alias):
    """Προσθέτει νέο πρόσταγμα."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO commands (name, executable, alias) VALUES (?, ?, ?)',
            (name.strip().lower(), executable.strip(), alias.strip())
        )
        conn.commit()
        new_id = cursor.lastrowid
        conn.close()
        return new_id
    except sqlite3.IntegrityError:
        return None


def update_command(command_id, name, executable, alias):
    """Ενημερώνει υπάρχον πρόσταγμα."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE commands SET name = ?, executable = ?, alias = ? WHERE id = ?',
            (name.strip().lower(), executable.strip(), alias.strip(), command_id)
        )
        conn.commit()
        affected = cursor.rowcount
        conn.close()
        return affected > 0
    except sqlite3.IntegrityError:
        return False


def delete_command(command_id):
    """Διαγράφει πρόσταγμα."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM commands WHERE id = ?', (command_id,))
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    return affected > 0


# --- SSH Connection Managment ---

def get_ssh_connections():
    """Επιστρέφει όλες τις αποθηκευμένες συνδέσεις."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, alias, host, port, username, password FROM ssh_connections ORDER BY alias')
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_ssh_connection(alias):
    """Επιστρέφει μια σύνδεση με βάση το alias."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, alias, host, port, username, password FROM ssh_connections WHERE alias = ?', (alias,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def save_ssh_connection(alias, host, port, username, password, old_alias=None):
    """
    Αποθηκεύει (insert ή update) μια σύνδεση.
    Αν δοθεί old_alias, κάνουμε update το record που είχε αυτό το alias.
    Αλλιώς κάνουμε insert ή replace.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        if old_alias:
            cursor.execute(
                'UPDATE ssh_connections SET alias=?, host=?, port=?, username=?, password=? WHERE alias=?',
                (alias, host, port, username, password, old_alias)
            )
        else:
            cursor.execute(
                'INSERT INTO ssh_connections (alias, host, port, username, password) VALUES (?, ?, ?, ?, ?)',
                (alias, host, port, username, password)
            )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False  # Duplicate alias
    finally:
        conn.close()

def delete_ssh_connection(alias):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM ssh_connections WHERE alias = ?', (alias,))
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    return affected > 0

def get_connection_aliases():
    """Επιστρέφει λίστα με τα ονόματα των aliases."""
    conns = get_ssh_connections()
    return [c['alias'] for c in conns]

# Helper for database.get_setting compatibility if needed
def get_setting(key):
    # This is deprecated but main.py calls it.
    # We should map 'host', 'port', etc to the 'Primary' connection
    # or just return None to force main.py to use new logic.
    # But main.py lines 54-71 rely on this. 
    # Better to update main.py. But for now return defaults from Primary.
    conn = get_ssh_connection('Primary')
    if conn and key in conn:
        return conn[key]
    return None


def export_db_data():
    """Εξάγει όλα τα δεδομένα της βάσης σε λεξικό."""
    return {
        "commands": get_all_commands(),
        "ssh_connections": get_ssh_connections()
    }


def import_db_data(data, mode='merge'):
    """
    Εισάγει δεδομένα στη βάση.
    mode: 'merge' (προσθήκη/ενημέρωση) ή 'replace' (διαγραφή όλων πριν την εισαγωγή).
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        if mode == 'replace':
            cursor.execute("DELETE FROM commands")
            cursor.execute("DELETE FROM ssh_connections")
        
        if "commands" in data:
            for cmd in data["commands"]:
                cursor.execute(
                    "INSERT OR REPLACE INTO commands (name, executable, alias) VALUES (?, ?, ?)",
                    (cmd['name'], cmd['executable'], cmd.get('alias', DEFAULT_ALIAS))
                )
        
        if "ssh_connections" in data:
            for ssh in data["ssh_connections"]:
                cursor.execute(
                    "INSERT OR REPLACE INTO ssh_connections (alias, host, port, username, password) VALUES (?, ?, ?, ?, ?)",
                    (ssh['alias'], ssh['host'], ssh['port'], ssh['username'], ssh['password'])
                )
        
        conn.commit()
        return True
    except Exception as e:
        print(f"Import error: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()
