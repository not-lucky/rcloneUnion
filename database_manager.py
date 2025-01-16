import json
import os
import shutil
from datetime import datetime


class DatabaseManager:
    def __init__(self, database_file, database_backup_folder):
        self.database_file = database_file
        self.database_backup_folder = database_backup_folder

    def load_database(self):
        """Loads the database from the JSON file."""
        try:
            with open(self.database_file, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            return {"accounts": {}}  # Return empty database if file not found

    def save_database(self, db):
        """Saves the database to the JSON file."""
        if not os.path.exists(self.database_file):
            with open(self.database_file, "w") as f:
                json.dump(
                    {"accounts": {}}, f
                )  # create an empty database file if it doesn't exist

        self.create_database_backup()
        with open(self.database_file, "w") as f:
            json.dump(db, f, indent=4)

    def initialize_database(self, db, accounts_folder):
        """Initializes the database with service account information."""
        sa_files = [f for f in os.listdir(accounts_folder) if f.endswith(".json")]
        for sa_file in sa_files:
            account_id = sa_file.replace(".json", "")
            if account_id not in db["accounts"]:
                db["accounts"][account_id] = {
                    "used_space": 0,
                    "remaining_space": int(
                        14.95 * 1024**3
                    ),  # Not doing 15 fully for now
                    "files": {},
                }
        return db

    def update_account_usage(self, db, account_id, file_size, file_path):
        """Updates the account usage in the database."""
        if account_id not in db["accounts"]:
            print(f"Error: Account {account_id} not found in database.")
            return db  # Return db as it was if account_id is invalid

        db["accounts"][account_id]["used_space"] += file_size
        db["accounts"][account_id]["remaining_space"] -= file_size
        db["accounts"][account_id]["files"][file_path] = {"size": file_size}
        return db

    def find_suitable_account(self, db, file_size):
        """Finds a suitable service account for a file."""
        suitable_accounts = []
        for account_id, data in db["accounts"].items():
            if data["remaining_space"] >= file_size:
                suitable_accounts.append((account_id, data["used_space"]))

        if not suitable_accounts:
            return None

        suitable_accounts.sort(
            key=lambda x: x[1], reverse=True
        )  # Sort by most used to optimize space
        return suitable_accounts[0][0]

    def file_already_processed(self, db, file_path):
        """Checks if a file has already been processed based on its name."""
        for account_id, data in db["accounts"].items():
            if file_path in data["files"]:
                print(f"Skipping (already uploaded): {file_path}")
                return True
        return False

    def create_database_backup(self):
        """Creates a backup of the database file."""
        if not os.path.exists(self.database_backup_folder):
            os.makedirs(self.database_backup_folder)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = os.path.join(
            self.database_backup_folder, f"drive_data_backup_{timestamp}.json"
        )
        try:
            shutil.copy2(self.database_file, backup_file)
            print(f"Database backup created: {backup_file}")
        except FileNotFoundError:
            print("Warning: Database file not found. No backup created.")
        except Exception as e:
            print(f"Error creating database backup: {e}")
