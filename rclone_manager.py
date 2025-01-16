import os
import re


class RcloneManager:
    def __init__(self, rclone_include_files_dir):
        self.rclone_include_files_dir = rclone_include_files_dir

    def generate_rclone_command(
        self, account_id, include_file, destination_path, source_path, is_delete=False
    ):
        """Generates an rclone copy/delete command using an include file."""
        # config_file = os.path.join("accounts", f"{account_id}.json")
        remote_name = f"g{account_id}"

        # create_remote_command = [
        #     "rclone",
        #     "config",
        #     "create",
        #     remote_name,
        #     "drive",
        #     "--drive-service-account-file",
        #     config_file,
        #     "--drive-scope",
        #     "drive",
        #     "--drive-allow-import-name-change",
        #     "--drive-acknowledge-abuse",
        #     "--drive-keep-revision-forever",
        #     "--drive-use-trash=false",
        #     "--drive-disable-http2",
        # ]
        # create_remote_command_str = " ".join(create_remote_command)

        if is_delete:
            command = [
                "rclone",
                "delete",
                "--include-from",
                include_file,
                f'"{remote_name}:{destination_path}"',
            ]
        else:
            command = [
                "rclone",
                "copy",
                "--ignore-existing",
                "--no-check-dest",
                "--size-only",
                "--progress",
                "-drive-copy-shortcut-content",
                "--include-from",
                include_file,
                f'"{source_path}"',  # Source is current directory, as include file contains paths
                f'"{remote_name}:{destination_path}"',
            ]
        command_str = " ".join(command)

        # return create_remote_command_str, command_str
        return command_str

    def create_rclone_include_file(self, account_id, file_paths):
        """Creates an include file for rclone with the given file paths."""
        os.makedirs(self.rclone_include_files_dir, exist_ok=True)
        include_file_name = f"include_{account_id}.txt"
        include_file = os.path.join(self.rclone_include_files_dir, include_file_name)
        with open(include_file, "w") as f:
            for file_path in file_paths:
                f.write(f"{re.escape(file_path)}\n")
        return include_file
