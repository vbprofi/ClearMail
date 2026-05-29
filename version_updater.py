import re


class VersionUpdater:
    def __init__(self, filepath):
        self.filepath = filepath
        self.file_content = ""
        self.filevers = (0, 0, 0, 0)
        self.prodvers = (0, 0, 0, 0)
        self.increment_filevers = True
        self.increment_prodvers = True
        self.increment_pattern = [3, 2, 1, 0]  # Standardmuster: Zähle die letzte Stelle hoch
        self.max_digits = [9, 9, 9, 9]  # Maximale Werte pro Stelle (standardmäßig einstellig)

    def load_file(self):
        """Liest die Datei und speichert den Inhalt."""
        with open(self.filepath, 'r', encoding='utf-8') as file:
            self.file_content = file.read()
        self._parse_versions()

    def _parse_versions(self):
        """Extrahiert die Versionsnummern aus dem Dateiinhalt."""
        filevers_match = re.search(r"filevers=\((\d+), (\d+), (\d+), (\d+)\)", self.file_content)
        prodvers_match = re.search(r"prodvers=\((\d+), (\d+), (\d+), (\d+)\)", self.file_content)

        if filevers_match:
            self.filevers = tuple(map(int, filevers_match.groups()))
        if prodvers_match:
            self.prodvers = tuple(map(int, prodvers_match.groups()))

    def _increment_version(self, version):
        """Erhöht die Versionsnummer gemäß dem benutzerdefinierten Muster und max_digits."""
        version = list(version)
        for pos in self.increment_pattern:
            version[pos] += 1
            if version[pos] > self.max_digits[pos]:
                version[pos] = 0
            else:
                break
        return tuple(version)

    def set_increment_flags(self, filevers_flag: bool, prodvers_flag: bool):
        """Setzt, ob filevers und prodvers inkrementiert werden sollen."""
        self.increment_filevers = filevers_flag
        self.increment_prodvers = prodvers_flag

    def set_increment_pattern(self, pattern: list[int]):
        """Legt das Zählmuster für die Versionsnummern fest."""
        if not all(0 <= p <= 3 for p in pattern):
            raise ValueError("Das Zählmuster darf nur Werte zwischen 0 und 3 enthalten.")
        self.increment_pattern = pattern

    def set_max_digits(self, max_digits: list[int]):
        """Legt die maximale Anzahl der Ziffern für jede Stelle fest."""
        if len(max_digits) != 4 or any(d <= 0 for d in max_digits):
            raise ValueError("max_digits muss eine Liste von 4 positiven Werten sein.")
        self.max_digits = max_digits

    def update_versions(self):
        """Aktualisiert die Versionsnummern je nach den gesetzten Flags und Muster."""
        if self.increment_filevers:
            self.filevers = self._increment_version(self.filevers)
        if self.increment_prodvers:
            self.prodvers = self._increment_version(self.prodvers)

        # Aktualisiere die Datei-Inhalte
        self.file_content = re.sub(
            r"filevers=\(\d+, \d+, \d+, \d+\)",
            f"filevers={self.filevers}",
            self.file_content
        )
        self.file_content = re.sub(
            r"prodvers=\(\d+, \d+, \d+, \d+\)",
            f"prodvers={self.prodvers}",
            self.file_content
        )
        self.file_content = re.sub(
            r"StringStruct\(u'FileVersion', u'\d+\.\d+\.\d+\.\d+'\)",
            f"StringStruct(u'FileVersion', u'{'.'.join(map(str, self.filevers))}')",
            self.file_content
        )
        self.file_content = re.sub(
            r"StringStruct\(u'ProductVersion', u'\d+\.\d+\.\d+\.\d+'\)",
            f"StringStruct(u'ProductVersion', u'{'.'.join(map(str, self.prodvers))}')",
            self.file_content
        )

    def save_file(self):
        """Speichert die aktualisierten Inhalte in die Datei."""
        with open(self.filepath, 'w', encoding='utf-8') as file:
            file.write(self.file_content)

    def display_versions(self):
        """Gibt die aktuellen Versionsnummern aus."""
        print(f"  FileVersion: {'.'.join(map(str, self.filevers))}")
        print(f"  ProductVersion: {'.'.join(map(str, self.prodvers))}")


if __name__ == "__main__":
    updater = VersionUpdater("version.txt")
    updater.load_file()
    print("Bisherige Version:")
    updater.display_versions()  # Zeige aktuelle Versionen an

    # Bestimme, welche Versionsnummern aktualisiert werden sollen
    updater.set_increment_flags(filevers_flag=True, prodvers_flag=True)

    # Lege das Muster fest: Zähle zuerst die dritte Stelle hoch, dann die zweite usw.
    updater.set_increment_pattern([3, 2, 1, 0])

    # Lege die Obergrenzen fest: 9 für die erste Stelle, 9 für die zweite, usw.
    updater.set_max_digits([9, 9, 99, 9])

    updater.update_versions()  # Aktualisiere die Versionen
    print("Neue Version:")
    updater.display_versions()  # Zeige neue Versionen an
    updater.save_file()  # Speichere die Änderungen
