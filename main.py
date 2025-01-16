import argparse
import os
import copy

from drive_manager import DriveManager
from database_manager import DatabaseManager
from rclone_manager import RcloneManager
from transfer_manager import TransferManager
from backup_manager import BackupManager

ACCOUNTS_FOLDER = "accounts"
DATABASE_FILE = "drive_data.json"
DATABASE_BACKUP_FOLDER = "db_backups"
RCLONE_INCLUDE_FILES_DIR = "rclone_include_files"
MASTER_REMOTE = "god"
BACKUPS_DIR = "backups"


def print_drive_structure(db, path, drive_manager):
    """Prints the Google Drive structure."""

    def _build_tree(account_files, filter_path=None):
        tree = {}
        for account_id, files in account_files.items():
            for file_path, file_data in files.items():
                if filter_path is None or file_path.startswith(filter_path):
                    relative_file_path = (
                        os.path.relpath(file_path, filter_path)
                        if filter_path
                        else file_path
                    )
                    parts = relative_file_path.split(os.sep)
                    current_level = tree
                    for part in parts:
                        if part not in current_level:
                            current_level[part] = {}
                        current_level = current_level[part]
                    current_level["(file)"] = {
                        "size": file_data["size"],
                        "full_path": file_path,
                    }
        return tree

    def _print_tree(tree, indent=""):
        for key, value in tree.items():
            if key == "(file)":
                pass
            else:
                print(f"{indent}- {key}")
                _print_tree(value, indent + " ")

    account_files = {
        account_id: data["files"] for account_id, data in db["accounts"].items()
    }
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


def print_commands(rclone_commands):
    print("\nRclone Commands:\n\n")
    for command in rclone_commands:
        print(command)


def main():
    parser = argparse.ArgumentParser(
        description="Manage file uploads to Google Drive using multiple service accounts and rclone.",
        add_help=False,
    )
    parser.add_argument(
        "source",
        nargs="?",
        default=None,
        help="Path to the source directory or file to upload, or Google Drive ID (id=...)",
    )
    parser.add_argument(
        "destination",
        nargs="?",
        default=None,
        help="Destination path in Google Drive (e.g., 'my-uploads/')",
    )
    parser.add_argument(
        "-s",
        "--structure",
        nargs="?",
        const=None,
        metavar="PATH",
        help="Print the Google Drive structure, optionally filtered by a path",
    )
    parser.add_argument(
        "--upload-folder",
        action="store_true",
        help="Upload the source folder directly to the destination",
    )
    parser.add_argument(
        "-r",
        "--remove",
        nargs="?",
        const=None,
        metavar="SOURCE",
        help="Remove the specified file or folder from the remote",
    )
    parser.add_argument(
        "-h",
        "--help",
        action="help",
        default=argparse.SUPPRESS,
        help="Show this help message and exit",
    )

    args = parser.parse_args()

    drive_manager = DriveManager(MASTER_REMOTE)
    database_manager = DatabaseManager(DATABASE_FILE, DATABASE_BACKUP_FOLDER)
    rclone_manager = RcloneManager(RCLONE_INCLUDE_FILES_DIR)
    transfer_manager = TransferManager(drive_manager, database_manager, rclone_manager)
    backup_manager = BackupManager(BACKUPS_DIR, RCLONE_INCLUDE_FILES_DIR)

    db_before = database_manager.load_database()
    db_before = database_manager.initialize_database(db_before, ACCOUNTS_FOLDER)
    db = copy.deepcopy(db_before)
    rclone_commands = []

    if args.structure is not None:
        print_drive_structure(db, args.structure, drive_manager)
    elif args.remove is not None:
        db, rclone_commands = transfer_manager.process_removal(args.remove, db)
        database_manager.save_database(db)
    elif args.source is not None and args.destination is not None:
        db, rclone_commands = transfer_manager.process_transfer(
            args.source, args.destination, args.upload_folder, db
        )
        database_manager.save_database(db)
    else:
        parser.error("Please provide valid arguments. Use -h for help.")

    db_after = database_manager.load_database()

    if rclone_commands:
        backup_manager.create_backup(args, rclone_commands, db_before, db_after)

        print_commands(rclone_commands)
    else:
        print("NO CHANGES!!!")


if __name__ == "__main__":
    main()
