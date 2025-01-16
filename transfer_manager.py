import os
import copy
from file_manager import FileManager


class TransferManager:
    def __init__(self, drive_manager, database_manager, rclone_manager):
        self.drive_manager = drive_manager
        self.database_manager = database_manager
        self.rclone_manager = rclone_manager

    def process_transfer(self, source, destination, upload_folder, db):
        """Processes the file/directory transfer."""
        rclone_commands = []
        files_to_transfer = []

        if source.startswith("id="):
            drive_id = source[3:]
            files_info = self.drive_manager.scan_drive_directory(
                drive_id, destination, upload_folder
            )
            if files_info is None:
                return db, rclone_commands
            files_to_transfer = files_info
        elif os.path.isdir(source):
            file_manager = FileManager()
            files_info = file_manager.scan_local_directory(
                source, destination, upload_folder
            )
            files_to_transfer = files_info
        elif os.path.isfile(source):
            file_manager = FileManager()
            files_info = file_manager.get_file_info(source, destination)
            files_to_transfer = [files_info]
        else:
            print(f"Error: Invalid source path: {source}")
            return db, rclone_commands

        account_files = {}
        for file_info in files_to_transfer:
            if not self.database_manager.file_already_processed(
                db, file_info["destination_path_with_name"]
            ):
                account_id = self.database_manager.find_suitable_account(
                    db, file_info["size"]
                )
                if account_id:
                    if account_id not in account_files:
                        account_files[account_id] = {
                            "file_paths": [],
                            "destination_paths": [],
                            # "source_paths": [],
                        }
                    account_files[account_id]["file_paths"].append(
                        file_info["relative_file_path"]
                    )
                    account_files[account_id]["destination_paths"].append(
                        file_info["destination_path"]
                    )
                    # account_files[account_id]["source_paths"].append(
                    #     file_info["full_file_path"]
                    # )

                    db = self.database_manager.update_account_usage(
                        db,
                        account_id,
                        file_info["size"],
                        file_info["destination_path_with_name"],
                    )
                    # print(
                    #     f"Preparing to upload (using {account_id}): {file_info['full_file_path']} -> {file_info['destination_path_with_name']}"
                    # )
                else:
                    print(
                        f"Error: No suitable account found for {file_info['full_file_path']} (size: {file_info['size']} bytes)"
                    )

        for account_id, data in account_files.items():
            include_file = self.rclone_manager.create_rclone_include_file(
                account_id, data["file_paths"]
            )
            source_path = (
                source
                # data["source_paths"][0] if data["source_paths"] else "."
            )  # Use current dir if no source

            # create_remote_command, copy_command = (
            copy_command = self.rclone_manager.generate_rclone_command(
                account_id,
                include_file,
                data["destination_paths"][0],
                source_path
                if not source.startswith("id=")
                else "god,root_folder_" + source_path + ":",
            )
            # rclone_commands.append(create_remote_command)
            rclone_commands.append(copy_command)

        return db, rclone_commands

    def process_removal(self, source, db):
        """Handles the removal of files/folders."""
        rclone_commands = []
        removal_map = self.find_account_and_path(db, source)
        db = self.remove_from_database(copy.deepcopy(db), removal_map)

        if not removal_map:
            print("Error: Nothing to remove.\nCheck if path is correct.")
            return db, rclone_commands

        for account_id, data in removal_map.items():
            include_file = self.rclone_manager.create_rclone_include_file(
                account_id, list(data.keys())
            )
            # _, delete_command = self.rclone_manager.generate_rclone_command(
            delete_command = self.rclone_manager.generate_rclone_command(
                account_id, include_file, source, ".", is_delete=True
            )
            rclone_commands.append(delete_command)

        print("\nGenerated rclone delete command:")
        print("\n".join(rclone_commands))
        return db, rclone_commands

    def find_account_and_path(self, db, path):
        """Finds accounts and files matching a given path in the database."""
        removal_map = {}
        for account_id, data in db["accounts"].items():
            for file_path, file_data in data["files"].items():
                if file_path.startswith(path):
                    if account_id not in removal_map:
                        removal_map[account_id] = {file_path: file_data["size"]}
                    else:
                        removal_map[account_id][file_path] = file_data["size"]
        return removal_map

    def remove_from_database(self, db, removal_map):
        """Removes entries from the database corresponding to the deleted path."""
        for account_id, data in removal_map.items():
            for file_path, file_size in data.items():
                db["accounts"][account_id]["used_space"] -= file_size
                db["accounts"][account_id]["remaining_space"] += file_size
                del db["accounts"][account_id]["files"][file_path]
                print(f"Removed from database: {file_path}")
        return db
