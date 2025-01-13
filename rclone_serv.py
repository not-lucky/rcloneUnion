import argparse
import json
import os
import shutil
from datetime import datetime
import re
import subprocess
import zipfile

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import os.path

import copy


# --- Configuration ---

ACCOUNTS_FOLDER = "accounts"
DATABASE_FILE = "drive_data.json"
DATABASE_BACKUP_FOLDER = "db_backups"
RCLONE_INCLUDE_FILES_DIR = "rclone_include_files"  # Directory to store rclone include files
MASTER_REMOTE = 'god'   # gdrive remote used to get files in a folder

# --- Helper Functions ---

def clear_include_files_directory():
    """Clears all contents inside the include files directory."""
    if os.path.exists(RCLONE_INCLUDE_FILES_DIR):
        shutil.rmtree(RCLONE_INCLUDE_FILES_DIR)
    os.makedirs(RCLONE_INCLUDE_FILES_DIR)
    print(f"Include files directory cleared: {RCLONE_INCLUDE_FILES_DIR}")


def run_rclone_ls(drive_id):
    """Runs rclone ls command and returns the JSON output."""

    command = [
        "rclone",
        "ls",
        "--fast-list",
        f"{MASTER_REMOTE},root_folder_id={drive_id}:"
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error running rclone ls: \n{result.stderr}")
        return None

    files = []
    for line in result.stdout.split('\n'):
      if line:
        temp = line.split()
        size, filename = temp[0], " ".join(temp[1:]).strip()
        files.append({
          'filename': filename,
          'size': size
        })

    return files

def parse_gdrive_source(source_string):
    """Parses the Google Drive source string (e.g., "id=12345")."""
    drive_id = source_string[3:]
    
    if not drive_id:
        raise ValueError("Invalid Google Drive source format. Use 'id=...' or 'root_folder_id=...'")
    
    return drive_id


def gdrive_get_folder_name(folder_id):
    """Shows basic usage of the Drive v3 API.
    Prints the names and ids of the first 10 files the user has access to.
    """

    SCOPES = ['https://www.googleapis.com/auth/drive.metadata.readonly']

    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    try:
        service = build('drive', 'v3', credentials=creds)

        # Call the Drive v3 API
        results = service.files().get(fileId=folder_id, fields='name').execute()
        folder_name = results.get('name', [])

        if not folder_name:
            print('No folder found.')
            return None
        return folder_name

    except HttpError as error:
        # TODO Handle errors from drive API.
        print(f'An error occurred: {error}')
        return None


def scan_gdrive_directory(db, drive_id, destination_base_path, upload_folder, rclone_commands):
    """
    Scans a Google Drive directory, generates rclone commands, and checks for already processed files.
    """
    account_files = {}  # Dictionary to store file paths for each account

    ls_output = run_rclone_ls(drive_id)

    if ls_output is None:
        return db

    if upload_folder:
        drive_folder_name = gdrive_get_folder_name(drive_id)

    for item in ls_output:
        file_path = item["filename"]
        file_size = int(item["size"])
        
        # Construct destination path based on settings
        if upload_folder:
            if drive_folder_name is None:
                return db
            
            # destination for rclone command, without filename
            destination_path = os.path.join(destination_base_path, drive_folder_name)
            
            # destination with filename for database
            destination_path_with_name = os.path.join(destination_path, file_path)
        
        else:
            # destination for rclone command, without filename
            destination_path = destination_base_path
            
            # destination with filename for database
            destination_path_with_name = os.path.join(destination_path, file_path)

        if not file_already_processed(db, destination_path_with_name):
            account_id = find_suitable_account(db, file_size)
            if account_id:
                # Add file to the account's list
                if account_id not in account_files:
                    account_files[account_id] = {"file_paths": [], "destination_paths": []}
                account_files[account_id]["file_paths"].append(file_path)
                account_files[account_id]["destination_paths"].append(destination_path)

                db = update_account_usage(db, account_id, file_size, destination_path_with_name)
                print(f"Preparing to upload (using {account_id}): {file_path} -> {destination_path_with_name}")
            else:
                print(f"Error: No suitable account found for {file_path} (size: {file_size} bytes)")

    # Create rclone commands for each account
    for account_id, data in account_files.items():
        include_file = create_rclone_include_file(account_id, data["file_paths"])
        create_remote_command, copy_command = generate_rclone_command(account_id, include_file, destination_path, f"{MASTER_REMOTE},root_folder_id={drive_id}:")
        rclone_commands.append(create_remote_command)
        rclone_commands.append(copy_command)

    return db


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


def create_database_backup(backup_dir, db_backup_folder=DATABASE_BACKUP_FOLDER):
    """Creates a backup of the database file."""
    if not os.path.exists(db_backup_folder):
        os.makedirs(db_backup_folder)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(db_backup_folder, f"drive_data_backup_{timestamp}.json")
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

    create_database_backup(backup_dir=None)
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
                "remaining_space": int(14.95 * 1024 ** 3),  # Not doing 15 fully for now
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

# --- Rclone Command Generation & Include File Handling ---

def generate_rclone_command(account_id, include_file, destination_path, source_path):
    """
    Generates an rclone copy command using an include file.

    Args:
        account_id (str): The ID of the service account.
        include_file (str): Path to the include file containing file/folder names to copy.
        destination_path (str): The destination path on Google Drive.

    Returns:
        tuple: A tuple containing the rclone config command and the rclone copy command.
    """
    config_file = os.path.join(ACCOUNTS_FOLDER, f"{account_id}.json")
    remote_name = f"gdrive-{account_id}"

    # Create the rclone config command
    create_remote_command = [
        "rclone", "config", "create", remote_name, "drive",
        "--drive-service-account-file", config_file,
        "--drive-scope", "drive",
        "--drive-allow-import-name-change",
        "--drive-acknowledge-abuse",
        "--drive-keep-revision-forever",
        "--drive-use-trash=false",
        "--drive-disable-http2"
    ]

    # Create a string from the list for printing
    create_remote_command_str = " ".join(create_remote_command)

    copy_command = [
        "rclone", "copy",
        # "--config", "/dev/null", # Use no config file, specify everything on command line
        # "--drive-service-account-file", config_file,
        "--drive-scope", "drive",
        "--drive-allow-import-name-change",
        "--drive-acknowledge-abuse",
        "--drive-keep-revision-forever",
        "--drive-use-trash=false",
        "--drive-disable-http2",
        "--ignore-existing",  # Prevents re-uploading if the file exists with same size and modified time
        "--no-check-dest",
        "--size-only",
        "--progress",
        "--include-from", include_file,  # Use include file to specify what to copy
        f'"{source_path}"',  # Source is current directory, as include file contains paths
        f'"{remote_name}:{destination_path}"'  # Added double quotes to handle paths with special characters
    ]

    # Create a string from the list for printing
    copy_command_str = " ".join(copy_command)

    return create_remote_command_str, copy_command_str

def create_rclone_include_file(account_id, file_paths):
    """
    Creates an include file for rclone with the given file paths.

    Args:
        account_id (str): The ID of the service account, used to name the include file.
        file_paths (list): A list of file paths to include.
        include_files_dir (str): Directory to store the include file.

    Returns:
        str: The path to the created include file.
    """
    os.makedirs(RCLONE_INCLUDE_FILES_DIR, exist_ok=True)
    include_file_name = f"include_{account_id}.txt"
    include_file = os.path.join(RCLONE_INCLUDE_FILES_DIR, include_file_name)
    with open(include_file, "w") as f:
        for file_path in file_paths:
            f.write(f"{re.escape(file_path)}\n")
    return include_file

# --- File and Directory Handling ---

def scan_directory(db, source_dir, destination_base_path, upload_folder, rclone_commands):
    """
    Scans the directory, generates rclone commands using include files, and checks if files were already processed.
    """
    account_files = {}  # Dictionary to store file paths for each account

    for root, dirs, files in os.walk(source_dir):
        # Determine relative path for destination
        relative_root = os.path.relpath(root, source_dir)

        if upload_folder:
            current_destination_path = os.path.join(destination_base_path, os.path.basename(source_dir),
                                                    relative_root) if relative_root != "." else os.path.join(
                destination_base_path, os.path.basename(source_dir))
        else:
            current_destination_path = os.path.join(destination_base_path,
                                                    relative_root) if relative_root != "." else destination_base_path

        for file in files:
            file_path = os.path.join(root, file)
            file_size = os.path.getsize(file_path)

            # destination for rclone command, without filename
            destination_path = current_destination_path

            # destination with filename for database
            destination_path_with_name = os.path.join(current_destination_path, file)

            # relative path for include file
            relative_file_path = os.path.relpath(file_path, source_dir)

            if not file_already_processed(db, destination_path_with_name):
                account_id = find_suitable_account(db, file_size)
                if account_id:
                    # Add file to the account's list
                    if account_id not in account_files:
                        account_files[account_id] = {"file_paths": [], "destination_paths": []}
                    account_files[account_id]["file_paths"].append(relative_file_path)
                    account_files[account_id]["destination_paths"].append(destination_path)

                    db = update_account_usage(db, account_id, file_size, destination_path_with_name)
                    print(
                        f"Preparing to upload (using {account_id}): {file_path} -> {destination_path_with_name}")
                else:
                    print(f"Error: No suitable account found for {file_path} (size: {file_size} bytes)")

    # Create rclone commands for each account
    for account_id, data in account_files.items():
        include_file = create_rclone_include_file(account_id, data["file_paths"])
        create_remote_command, copy_command = generate_rclone_command(account_id, include_file, destination_base_path,
                                                                     source_dir)  # Pass base destination path
        rclone_commands.append(create_remote_command)
        rclone_commands.append(copy_command)

    return db

# --- Drive Structure ---

def print_drive_structure(db, path=None):
    """Prints the Google Drive structure in a tree-like format, filtering by a given path.

    Args:
        db (dict): The database containing the Google Drive structure.
        path (str, optional): The path to filter the structure by. Defaults to None (entire structure).
    """

    def _build_tree(account_files, filter_path=None):
        """Builds a tree structure from the file paths, optionally filtering by a given path."""
        tree = {}
        for account_id, files in account_files.items():
            for file_path, file_data in files.items():
                if filter_path is None or file_path.startswith(filter_path):
                    # Adjust file path to be relative to the filter path if a filter path is given
                    relative_file_path = os.path.relpath(file_path, filter_path) if filter_path else file_path
                    parts = relative_file_path.split(os.sep)
                    current_level = tree
                    for part in parts:
                        if part not in current_level:
                            current_level[part] = {}
                        current_level = current_level[part]
                    current_level["(file)"] = {
                        "size": file_data["size"],
                        "full_path": file_path  # Store the full path for printing or further processing
                    }
        return tree

    def _print_tree(tree, indent=""):
        """Recursively prints the tree structure."""
        for key, value in tree.items():
            if key == "(file)":
                # print(f"{indent} - File: {value['full_path']} (Size: {value['size']} bytes)")
                pass
            else:
                print(f"{indent}- {key}")
                _print_tree(value, indent + " ")

    account_files = {account_id: data["files"] for account_id, data in db["accounts"].items()}
    tree = _build_tree(account_files, path)

    if not tree:
        if path:
            print(f"No files found under the path '{path}'.")
        else:
            print("The Google Drive structure is empty.")
    else:
        if path:
            print(f"Google Drive structure under '{path}':")
        else:
            print("Google Drive structure:")
        _print_tree(tree)

# --- Main Program Logic ---

def handle_upload(db, source, destination, upload_folder, rclone_commands):
    """Handles the file/directory upload process."""
    if source.startswith("id="):
        try:
            drive_id = parse_gdrive_source(source)
            db = scan_gdrive_directory(db, drive_id, destination, upload_folder, rclone_commands)
            
            if rclone_commands:
                print("\nGenerated rclone commands:")
                for command in rclone_commands:
                    print(command)
            else:
                print("No files to upload.")
        except ValueError as e:
            print(f"Error: {e}")

    elif os.path.isdir(source):
        db = scan_directory(db, source, destination, upload_folder, rclone_commands)
        if rclone_commands:
            print("\nGenerated rclone commands:")
            for command in rclone_commands:
                print(command)
        else:
            print("No files to upload.")

    elif os.path.isfile(source):
        file_size = os.path.getsize(source)

        # removed upload folder check since in uploading file case, it doesn't matter
        destination_with_filename = f"{destination}/{source}" if destination else source
        destination_path = destination

        if not file_already_processed(db, destination_with_filename):
            account_id = find_suitable_account(db, file_size)
            if account_id:
                # Create an include file for the single file
                include_file = create_rclone_include_file(account_id, [os.path.basename(source)])  # Add base destination path for single file
                create_remote_command, copy_command = generate_rclone_command(account_id, include_file,
                                                                             destination_path, source)

                print("\nGenerated rclone commands:")
                print(create_remote_command)
                print(copy_command)

                db = update_account_usage(db, account_id, file_size, destination_with_filename)
                print(f"Uploading (using {account_id}): {source} -> {destination_with_filename}")
            else:
                print(f"Error: No suitable account found for {source} (size: {file_size} bytes)")
        else:
            print(f"Skipping already processed file: {source}")

    else:
        print(f"Error: Invalid source path: {source}")

    return db

# --- Removal Handle ---

def handle_remove(db, source, rclone_commands):
    """Handles the removal of files/folders from the remote and updates the database."""
    # Check if source is a Google Drive ID or a local file/folder path
    if source:

        removalMap = find_account_and_path(db, source) 

        # Update database to remove all files under this folder
        db = remove_from_database(copy.deepcopy(db), removalMap)

        if not removalMap:
            print("Error: Nothing to remove.\nCheck if path is correct.")
        else:

            # Generate rclone command to delete the folder
            for account_id, data in removalMap.items():
                include_file = create_rclone_include_file(account_id, data.keys())
                rclone_commands.append(
                    f"rclone delete --include-from {include_file} g{account_id}:"
                )

            print("\nGenerated rclone delete command:")
            print("\n".join(rclone_commands))
    else:
        print(f"Error: Invalid source for removal: {source}")
    return db


def find_account_and_path(db, path):
    removalMap = {}

    for account_id, data in db['accounts'].items():
        for file_path, file_data in data["files"].items():
            if file_path.startswith(path):
                if account_id not in removalMap:
                    removalMap[account_id] = {file_path: file_data['size']}
                else:
                    removalMap[account_id][file_path] = file_data['size']

    return removalMap


def remove_from_database(db, removalMap):
    """Removes entries from the database corresponding to the deleted path."""
    # Iterate through accounts and remove files/folders matching the path
    for account_id, data in removalMap.items():
        for file_path, file_size in data.items():
            db["accounts"][account_id]["used_space"] -= file_size
            db["accounts"][account_id]["remaining_space"] += file_size
            del db["accounts"][account_id]["files"][file_path]
            print(f"Removed from database: {file_path}")
    return db

# --- Backup Utility ---

def create_backup(backup_dir, args, rclone_commands, db_before, db_after):
    """Creates a backup of inputs, commands, include files, and databases."""
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)

    # Backup input arguments
    with open(os.path.join(backup_dir, "input_arguments.txt"), "w") as f:
        f.write(str(args))

    # Backup rclone commands
    with open(os.path.join(backup_dir, "generated_commands.txt"), "w") as f:
        for cmd in rclone_commands:
            f.write(f"{cmd}\n")

    # Backup include files
    include_files_path = os.path.join(backup_dir, "include_files.zip")
    with zipfile.ZipFile(include_files_path, 'w') as zipf:
        for root, dirs, files in os.walk(RCLONE_INCLUDE_FILES_DIR):
            for file in files:
                file_path = os.path.join(root, file)
                zipf.write(file_path, os.path.relpath(file_path, RCLONE_INCLUDE_FILES_DIR))

    # Backup database before and after execution
    with open(os.path.join(backup_dir, "database_before.json"), "w") as f:
        json.dump(db_before, f, indent=4)
    with open(os.path.join(backup_dir, "database_after.json"), "w") as f:
        json.dump(db_after, f, indent=4)

    print(f"Backup created in: {backup_dir}")

# --- Main Program Logic ---

def main():
    """Main function to handle CLI and program logic."""
    parser = argparse.ArgumentParser(description="Manage file uploads to Google Drive using multiple service accounts and rclone.", add_help=False)
    parser.add_argument("source", nargs='?', default=None,
                        help="Path to the source directory or file to upload, or Google Drive ID (id=...)")
    parser.add_argument("destination", nargs='?', default=None,
                        help="Destination path in Google Drive (e.g., 'my-uploads/')")
    parser.add_argument("-s", "--structure", nargs='?', const=None, metavar="PATH",
                        help="Print the Google Drive structure, optionally filtered by a path")
    parser.add_argument("--upload-folder", action="store_true",
                        help="Upload the source folder directly to the destination")
    parser.add_argument("-r", "--remove", nargs='?', const=None, metavar="SOURCE",
                        help="Remove the specified file or folder from the remote")
    parser.add_argument("-h", "--help", action="help", default=argparse.SUPPRESS,
                        help="Show this help message and exit")

    args = parser.parse_args()

    # Create backup directory
    backup_dir = os.path.join("backups", datetime.now().strftime("%Y%m%d_%H%M%S"))
    os.makedirs(backup_dir, exist_ok=True)

    db_before = load_database()
    db_before = initialize_database(db_before)
    db = copy.deepcopy(db_before)
    rclone_commands = []

    clear_include_files_directory()

    if args.structure is not None:  # Check if -s was used (with or without a path)
        print_drive_structure(db, args.structure)
    elif args.remove is not None:  # Check if -r was used
        db = handle_remove(db, args.remove, rclone_commands)
        save_database(db)
    elif args.source is not None and args.destination is not None:
        db = handle_upload(db, args.source, args.destination, args.upload_folder, rclone_commands)
        save_database(db)
    else:
        parser.error("Please provide valid arguments. Use -h for help.")

    db_after = load_database()

    # Collect rclone_commands from the functions
    # (Assuming rclone_commands are collected during handle_upload and handle_remove)

    # Create backup
    create_backup(backup_dir, args, rclone_commands, db_before, db_after)

if __name__ == "__main__":
    main()