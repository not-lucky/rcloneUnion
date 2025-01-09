import argparse
import hashlib
import json
import os
import shutil
import subprocess
import time
from datetime import datetime

# --- Configuration ---
ACCOUNTS_FOLDER = "accounts"
DATABASE_FILE = "drive_data.json"
DATABASE_BACKUP_FOLDER = "db_backups"

# --- Helper Functions ---

def calculate_md5(file_path):
    """Calculates the MD5 hash of a file."""
    hasher = hashlib.md5()
    with open(file_path, 'rb') as file:
        while True:
            chunk = file.read(4096)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()

def get_service_account_files():
    """Returns a list of service account JSON files in the accounts folder."""
    return [f for f in os.listdir(ACCOUNTS_FOLDER) if f.endswith('.json')]

def create_database_backup():
    """Creates a backup of the database file."""
    if not os.path.exists(DATABASE_BACKUP_FOLDER):
        os.makedirs(DATABASE_BACKUP_FOLDER)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(DATABASE_BACKUP_FOLDER, f"drive_data_backup_{timestamp}.json")
    shutil.copy2(DATABASE_FILE, backup_file)
    print(f"Database backup created: {backup_file}")

# --- Database Management ---

def load_database():
    """Loads the database from the JSON file."""
    try:
        with open(DATABASE_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {"accounts": {}}

def save_database(db):
    """Saves the database to the JSON file."""
    if not os.path.exists(DATABASE_FILE):
        # Create an empty database file if it doesn't exist
        with open(DATABASE_FILE, 'w') as f:
            json.dump({"accounts": {}}, f)  

    create_database_backup()
    with open(DATABASE_FILE, 'w') as f:
        json.dump(db, f, indent=4)

def initialize_database(db):
    """Initializes the database with service account information."""
    sa_files = get_service_account_files()
    for sa_file in sa_files:
        account_id = sa_file.replace(".json","")
        if account_id not in db["accounts"]:
            db["accounts"][account_id] = {
                "used_space": 0,
                "remaining_space": 15 * 1024**3,  # 15 GiB in bytes
                "files": {}
            }
    return db

def update_account_usage(db, account_id, file_size, file_path, md5):
    """Updates the account usage in the database."""
    db["accounts"][account_id]["used_space"] += file_size
    db["accounts"][account_id]["remaining_space"] -= file_size
    db["accounts"][account_id]["files"][file_path] = {"size": file_size, "md5": md5}
    return db

def find_suitable_account(db, file_size):
    """Finds a suitable service account for a file."""
    suitable_accounts = []
    for account_id, data in db["accounts"].items():
        if data["remaining_space"] >= file_size:
            suitable_accounts.append((account_id, data["used_space"]))

    if not suitable_accounts:
        return None
    
    # Sort by used space ascending to maximize space utilization
    suitable_accounts.sort(key=lambda x: x[1])
    return suitable_accounts[0][0]

# --- Rclone Command Generation ---

def generate_rclone_command(account_id, source_path, destination_path):
    """Generates an rclone copy command."""
    config_file = os.path.join(ACCOUNTS_FOLDER, f"{account_id}.json")
    remote_name = f"gdrive-{account_id}"  # Assuming you'll name remotes like this

    # Create the rclone config command
    create_remote_command = [
        "rclone", "config", "create", remote_name, "drive",
        "--drive-service-account-file", config_file,
        "--drive-scope", "drive",
        "--drive-allow-import-name-change",
        "--drive-acknowledge-abuse",
        "--drive-keep-revision-forever",
        "--drive-upload-cutoff", "5G",
        "--drive-chunk-size", "256M",
        "--drive-batch-size", "1000",
        "--drive-batch-timeout", "1m",
        "--drive-use-trash=false",
        "--drive-disable-http2"
    ]

    # Create a string from the list for printing
    create_remote_command_str = " ".join(create_remote_command)

    copy_command = [
        "rclone", "copy",
        "--config", "/dev/null",  # Use no config file, specify everything on command line
        "--drive-service-account-file", config_file,
        "--drive-scope", "drive",
        "--drive-allow-import-name-change",
        "--drive-acknowledge-abuse",
        "--drive-keep-revision-forever",
        "--drive-upload-cutoff", "5G",
        "--drive-chunk-size", "256M",
        "--drive-batch-size", "1000",
        "--drive-batch-timeout", "1m",
        "--drive-use-trash=false",
        "--drive-disable-http2",
        "--ignore-existing",  # Prevents re-uploading if the file exists with same size and modified time
        "--no-check-dest",
        "--ignore-checksum",
        "--size-only",
        "--progress",
        source_path,
        f"{remote_name}:{destination_path}"
    ]

    # Create a string from the list for printing
    copy_command_str = " ".join(copy_command)

    return create_remote_command_str, copy_command_str


# --- File and Directory Handling ---

def scan_directory(db, source_dir, destination_base_path):
    """Scans the directory and generates rclone commands."""
    rclone_commands = []
    for root, _, files in os.walk(source_dir):
        for file in files:
            file_path = os.path.join(root, file)
            file_size = os.path.getsize(file_path)
            md5 = calculate_md5(file_path)

            # Determine relative path for destination
            relative_path = os.path.relpath(file_path, source_dir)
            destination_path = os.path.join(destination_base_path, relative_path)

            # Check if file already exists in database (any account)
            file_exists = False
            for account_id, data in db["accounts"].items():
                if destination_path in data["files"] and data["files"][destination_path]["md5"] == md5:
                    print(f"Skipping (already uploaded): {file_path}")
                    file_exists = True
                    break

            if not file_exists:
                account_id = find_suitable_account(db, file_size)
                if account_id:
                    create_remote_command, copy_command = generate_rclone_command(account_id, file_path, destination_path)

                    rclone_commands.append(create_remote_command)
                    rclone_commands.append(copy_command)
                    
                    db = update_account_usage(db, account_id, file_size, destination_path, md5)
                    print(f"Uploading (using {account_id}): {file_path} -> {destination_path}")
                else:
                    print(f"Error: No suitable account found for {file_path} (size: {file_size} bytes)")

    return rclone_commands, db
# --- Drive Structure ---

def print_drive_structure(db):
    """Prints the Google Drive structure based on the database."""
    drive_structure = {}

    for account_id, account_data in db["accounts"].items():
        for file_path, file_data in account_data["files"].items():
            path_parts = file_path.split(os.sep)
            current_level = drive_structure

            for part in path_parts[:-1]:
                if part not in current_level:
                    current_level[part] = {}
                current_level = current_level[part]
            
            current_level[path_parts[-1]] = {
                "account": account_id,
                "size": file_data["size"],
                "md5": file_data["md5"]
            }

    print(json.dumps(drive_structure, indent=4))

# --- Main Program ---

def main():
    """Main function to handle CLI and program logic."""
    parser = argparse.ArgumentParser(description="Manage file uploads to Google Drive using multiple service accounts and rclone.")
    parser.add_argument("source", help="Path to the source directory or file to upload")
    parser.add_argument("destination", help="Destination path in Google Drive (e.g., 'my-uploads/')")
    parser.add_argument("-s", "--structure", action="store_true", help="Print the Google Drive structure")
    args = parser.parse_args()

    db = load_database()
    db = initialize_database(db)

    if args.structure:
        print_drive_structure(db)
        return

    if os.path.isdir(args.source):
        rclone_commands, db = scan_directory(db, args.source, args.destination)
        if rclone_commands:
            print("\nGenerated rclone commands:")
            for command in rclone_commands:
                print(command)
        else:
            print("No files to upload.")

    elif os.path.isfile(args.source):
        file_size = os.path.getsize(args.source)
        md5 = calculate_md5(args.source)

        # Check if file already exists in database (any account)
        file_exists = False
        for account_id, data in db["accounts"].items():
            if args.destination in data["files"] and data["files"][args.destination]["md5"] == md5:
                print(f"Skipping (already uploaded): {args.source}")
                file_exists = True
                break

        if not file_exists:
            account_id = find_suitable_account(db, file_size)
            if account_id:
                create_remote_command, copy_command = generate_rclone_command(account_id, args.source, args.destination)

                print("\nGenerated rclone commands:")
                print(create_remote_command)
                print(copy_command)

                db = update_account_usage(db, account_id, file_size, args.destination, md5)
                print(f"Uploading (using {account_id}): {args.source} -> {args.destination}")
            else:
                print(f"Error: No suitable account found for {args.source} (size: {file_size} bytes)")
    else:
        print(f"Error: Invalid source path: {args.source}")

    save_database(db)

if __name__ == "__main__":
    main()