import os
import zipfile
import json
from datetime import datetime
import shutil


class BackupManager:
    def __init__(self, backups_dir, rclone_include_files_dir):
        self.backups_dir = backups_dir
        self.rclone_include_files_dir = rclone_include_files_dir
        self.clear_include_files_directory()  # Clear on init for safety

    def create_backup(self, args, rclone_commands, db_before, db_after):
        """Creates a backup of inputs, commands, include files, and databases."""
        if not os.path.exists(self.backups_dir):
            os.makedirs(self.backups_dir)

        backup_dir = os.path.join(
            self.backups_dir, datetime.now().strftime("%Y%m%d_%H%M%S")
        )
        os.makedirs(backup_dir, exist_ok=True)

        with open(os.path.join(backup_dir, "input_arguments.txt"), "w") as f:
            f.write(str(args))

        with open(os.path.join(backup_dir, "generated_commands.txt"), "w") as f:
            for cmd in rclone_commands:
                f.write(f"{cmd}\n")

        include_files_path = os.path.join(backup_dir, "include_files.zip")
        with zipfile.ZipFile(include_files_path, "w") as zipf:
            for root, _, files in os.walk(self.rclone_include_files_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    zipf.write(
                        file_path,
                        os.path.relpath(file_path, self.rclone_include_files_dir),
                    )

        with open(os.path.join(backup_dir, "database_before.json"), "w") as f:
            json.dump(db_before, f, indent=4)
        with open(os.path.join(backup_dir, "database_after.json"), "w") as f:
            json.dump(db_after, f, indent=4)

        print(f"Backup created in: {backup_dir}")

    def clear_include_files_directory(self):
        """Clears all contents inside the include files directory."""
        if os.path.exists(self.rclone_include_files_dir):
            shutil.rmtree(self.rclone_include_files_dir)
        os.makedirs(self.rclone_include_files_dir)
        print(f"Include files directory cleared: {self.rclone_include_files_dir}")
