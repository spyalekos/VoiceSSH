# database.py
"""
SQLite database module για διαχείριση προσταγμάτων (commands).
"""
import sqlite3
import os
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


def get_connection():
    """Επιστρέφει σύνδεση στη βάση δεδομένων."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """
    Αρχικοποίηση της βάσης δεδομένων.
    Δημιουργεί τον πίνακα αν δεν υπάρχει και προσθέτει τα default commands.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    # Δημιουργία πίνακα
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS commands (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            executable TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Προσθήκη default commands αν ο πίνακας είναι κενός
    cursor.execute('SELECT COUNT(*) FROM commands')
    count = cursor.fetchone()[0]
    
    if count == 0:
        for name, executable in DEFAULT_COMMANDS.items():
            cursor.execute(
                'INSERT INTO commands (name, executable) VALUES (?, ?)',
                (name, executable)
            )
    
    conn.commit()
    conn.close()


def get_all_commands():
    """
    Επιστρέφει όλα τα προστάγματα ως λίστα dictionaries.
    Returns: [{'id': 1, 'name': 'σημειώσεις', 'executable': 'notepad.exe'}, ...]
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, executable FROM commands ORDER BY name')
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_commands_dict():
    """
    Επιστρέφει τα προστάγματα ως dictionary {name: executable}.
    Χρησιμοποιείται για backward compatibility με το handle_command.
    """
    commands = get_all_commands()
    return {cmd['name']: cmd['executable'] for cmd in commands}


def get_command(command_id):
    """Επιστρέφει ένα πρόσταγμα με βάση το ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, executable FROM commands WHERE id = ?', (command_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def add_command(name, executable):
    """
    Προσθέτει νέο πρόσταγμα.
    Returns: ID του νέου command ή None αν αποτύχει.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO commands (name, executable) VALUES (?, ?)',
            (name.strip().lower(), executable.strip())
        )
        conn.commit()
        new_id = cursor.lastrowid
        conn.close()
        return new_id
    except sqlite3.IntegrityError:
        return None  # Duplicate name


def update_command(command_id, name, executable):
    """
    Ενημερώνει υπάρχον πρόσταγμα.
    Returns: True αν επιτυχής, False αν αποτύχει.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE commands SET name = ?, executable = ? WHERE id = ?',
            (name.strip().lower(), executable.strip(), command_id)
        )
        conn.commit()
        affected = cursor.rowcount
        conn.close()
        return affected > 0
    except sqlite3.IntegrityError:
        return False  # Duplicate name


def delete_command(command_id):
    """
    Διαγράφει πρόσταγμα.
    Returns: True αν επιτυχής, False αν δεν βρέθηκε.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM commands WHERE id = ?', (command_id,))
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    return affected > 0
