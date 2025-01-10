import argparse
import json
import os
import shutil
import subprocess
import time
from datetime import datetime
import multiprocessing

# --- Configuration ---
ACCOUNTS_FOLDER = "accounts"
DATABASE_FILE = "drive_data.json"
DATABASE_BACKUP_FOLDER = "db_backups"

# --- Helper Functions ---

def file_already_processed(db, file_path):
    """Checks if a file has already been processed based on its name."""
    for account_id, data in db["accounts"].items():
        if file_path in data["files"]:
            print(f"Skipping (already uploaded): {file_path}")
            return True
    return False

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
        account_id = sa_file.replace(".json", "")
        if account_id not in db["accounts"]:
            db["accounts"][account_id] = {
                "used_space": 0,
                "remaining_space": 15 * 1024 ** 3,  # 15 GiB in bytes
                "files": {}
            }
    return db


def update_account_usage(db, account_id, file_size, file_path):
    """Updates the account usage in the database."""
    db["accounts"][account_id]["used_space"] += file_size
    db["accounts"][account_id]["remaining_space"] -= file_size
    db["accounts"][account_id]["files"][file_path] = {"size": file_size}
    return db


def find_suitable_account(db, file_size):
    """Finds a suitable service account for a file."""
    suitable_accounts = []
    for account_id, data in db["accounts"].items():
        if data["remaining_space"] >= file_size:
            suitable_accounts.append((account_id, data["used_space"]))

    if not suitable_accounts:
        return None
    # Sort by used space descending to maximize space utilization
    suitable_accounts.sort(key=lambda x: x[1], reverse=True)
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
        "--drive-batch-size", "1000",
        "--drive-batch-timeout", "1m",
        "--drive-use-trash=false",
        "--drive-disable-http2",
        "--ignore-existing",  # Prevents re-uploading if the file exists with same size and modified time
        "--no-check-dest",
        "--size-only",
        "--progress",
        f'"{source_path}"',
        f'"{remote_name}:{destination_path}"' # Added double quotes to handle paths with special characters
    ]

    # Create a string from the list for printing
    copy_command_str = " ".join(copy_command)

    return create_remote_command_str, copy_command


# --- File and Directory Handling ---

def scan_directory(db, source_dir, destination_base_path, upload_folder):
    """Scans the directory, generates rclone commands, and checks if files were already processed."""
    rclone_commands = []

    for root, dirs, files in os.walk(source_dir):
        # Determine relative path for destination
        relative_root = os.path.relpath(root, source_dir)
        
        if upload_folder:
            current_destination_base_path = os.path.join(destination_base_path, os.path.basename(source_dir), relative_root) if relative_root != "." else os.path.join(destination_base_path, os.path.basename(source_dir))
            # current_destination_base_path = os.path.join(destination_base_path, relative_root) 
        else:
            current_destination_base_path = destination_base_path

        for file in files:
            file_path = os.path.join(root, file)
            file_size = os.path.getsize(file_path)

            # Construct destination path correctly for both cases
            
            destination_path = os.path.join(current_destination_base_path, file)
          

            if not file_already_processed(db, destination_path):
                account_id = find_suitable_account(db, file_size)
                if account_id:
                    create_remote_command, copy_command = generate_rclone_command(account_id, file_path,
                                                                                destination_path)

                    rclone_commands.append(create_remote_command)
                    rclone_commands.append(copy_command)
                    db = update_account_usage(db, account_id, file_size, destination_path)
                    print(
                        f"Uploading (using {account_id}): {file_path} -> {destination_path}")
                else:
                    print(f"Error: No suitable account found for {file_path} (size: {file_size} bytes)")

    return rclone_commands, db

# --- Drive Structure ---

def print_drive_structure(db):
    """
    Prints the Google Drive structure in a tree-like format.
    """

    def _build_tree(account_files):
        """Builds a tree structure from the file paths."""
        tree = {}
        for account_id, files in account_files.items():
            for file_path, file_data in files.items():
                parts = file_path.split(os.sep)
                current_level = tree
                for part in parts:
                    if part not in current_level:
                        current_level[part] = {}
                    current_level = current_level[part]
                current_level["(file)"] = {
                    "size": file_data["size"]
                }
        return tree

    def _print_tree(tree, indent=""):
        """Recursively prints the tree structure."""
        for key, value in tree.items():
            if key == "(file)":
                print(f"{indent} - File (Size: {value['size']} bytes)")  # Only print size
            else:
                print(f"{indent}- {key}")
                _print_tree(value, indent + " ")

    account_files = {account_id: data["files"] for account_id, data in db["accounts"].items()}
    tree = _build_tree(account_files)
    _print_tree(tree)


# --- Main Program Logic ---

def handle_upload(db, source, destination, upload_folder):
    """Handles the file/directory upload process."""
    if os.path.isdir(source):
        rclone_commands, db = scan_directory(db, source, destination, upload_folder)
        if rclone_commands:
            print("\nGenerated rclone commands:")
            for command in rclone_commands:
                print(command)
        else:
            print("No files to upload.")

    elif os.path.isfile(source):
        file_size = os.path.getsize(source)
        
        #Correct destination for single file when upload_folder is True
        if upload_folder:
          destination_path = os.path.join(destination, os.path.basename(source))
        else:
          destination_path = destination

        if not file_already_processed(db, destination_path):
            account_id = find_suitable_account(db, file_size)
            if account_id:
                create_remote_command, copy_command = generate_rclone_command(account_id, source, destination_path)

                print("\nGenerated rclone commands:")
                print(create_remote_command)
                print(copy_command)

                db = update_account_usage(db, account_id, file_size, destination_path)
                print(f"Uploading (using {account_id}): {source} -> {destination_path}")
            else:
                print(f"Error: No suitable account found for {source} (size: {file_size} bytes)")
        else:
            print(f"Skipping already processed file: {source}")

    else:
        print(f"Error: Invalid source path: {source}")

    return db

def main():
    """Main function to handle CLI and program logic."""
    parser = argparse.ArgumentParser(description="Manage file uploads to Google Drive using multiple service accounts and rclone.")
    parser.add_argument("source", nargs='?', default=None, help="Path to the source directory or file to upload")
    parser.add_argument("destination", nargs='?', default=None, help="Destination path in Google Drive (e.g., 'my-uploads/')")
    parser.add_argument("-s", "--structure", action="store_true", help="Print the Google Drive structure")
    parser.add_argument("--upload-folder", action="store_true", help="Upload the source folder directly to the destination")

    args = parser.parse_args()

    db = load_database()
    db = initialize_database(db)



    if args.structure:
        print_drive_structure(db)
    else:
        # db = handle_upload(db, "test", "", True)
        # save_database(db)
        # exit()

        
        if args.source is None or args.destination is None: # Use is None for comparison
            parser.error("Source and destination arguments are required for upload.")
        db = handle_upload(db, args.source, args.destination, args.upload_folder)

        save_database(db)

if __name__ == "__main__":
    main()