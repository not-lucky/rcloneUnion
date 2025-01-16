import os
import subprocess
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request


class DriveManager:
    def __init__(self, master_remote):
        self.master_remote = master_remote
        self.SCOPES = ["https://www.googleapis.com/auth/drive.metadata.readonly"]

    def get_folder_name(self, folder_id):
        """Fetches the name of a Google Drive folder."""
        creds = None
        if os.path.exists("token.json"):
            creds = Credentials.from_authorized_user_file("token.json", self.SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    "credentials.json", self.SCOPES
                )
                creds = flow.run_local_server(port=0)
            with open("token.json", "w") as token:
                token.write(creds.to_json())

        try:
            service = build("drive", "v3", credentials=creds)
            results = service.files().get(fileId=folder_id, fields="name").execute()
            folder_name = results.get("name", None)
            return folder_name
        except HttpError as error:
            # TODO Handle errors from drive API.
            print(f"An error occurred: {error}")
            return None

    def scan_drive_directory(self, drive_id, destination_base_path, upload_folder):
        """Scans a directory in Google Drive and returns file information."""

        ls_output = self.run_rclone_ls(drive_id)
        if ls_output is None:
            return None

        files_info = []
        drive_folder_name = None
        if upload_folder:
            drive_folder_name = self.get_folder_name(drive_id)
            if drive_folder_name is None:
                return None

        for item in ls_output:
            file_path = item["filename"]
            file_size = int(item["size"])
            if upload_folder:
                destination_path = os.path.join(
                    destination_base_path, drive_folder_name
                )
            else:
                destination_path = destination_base_path
            destination_path_with_name = os.path.join(destination_path, file_path)

            files_info.append(
                {
                    "filename": file_path,
                    "size": file_size,
                    "relative_file_path": file_path,  # for include files
                    "destination_path": destination_path,  # for destination foldername; only need it once sooooo will optimize it in future
                    "destination_path_with_name": destination_path_with_name,
                }
            )
        return files_info

    def run_rclone_ls(self, drive_id):
        """Runs rclone ls command and returns the JSON output."""
        command = [
            "rclone",
            "ls",
            "--fast-list",
            "--max-depth=15",  # temp fix for recursive shortcut problem
            f"{self.master_remote},root_folder_id={drive_id}:",
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Error running rclone ls: \n{result.stderr}")
            return None

        files = []
        for line in result.stdout.split("\n"):
            if line:
                temp = line.split()
                if len(temp) >= 2:  # Check if the line has at least size and filename
                    size, filename = temp[0], " ".join(temp[1:]).strip()
                    files.append({"filename": filename, "size": size})
                else:
                    print(f"Warning: Skipping malformed rclone ls output line: {line}")
        return files
