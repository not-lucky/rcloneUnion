# rcloneUnion

This project is designed to manage file uploads and transfers to Google Drive using multiple service accounts and the rclone tool. It provides a structured way to handle large file transfers, manage account usage, and maintain a database of uploaded files.

## Table of Contents

- [Features](#features)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
  - [Uploading Files/Directories](#uploading-filesdirectories)
  - [Removing Files/Directories](#removing-filesdirectories)
  - [Printing Drive Structure](#printing-drive-structure)
- [Backup Management](#backup-management)
- [Dependencies](#dependencies)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

## Features

- Upload files or directories to Google Drive.
- Manage multiple Google Drive service accounts.
- Track file uploads and account usage in a database.
- Generate rclone commands for file transfers.
- Backup input arguments, commands, and database changes.

## Prerequisites

- Python 3.8 or higher.
- Google Drive API credentials.
- rclone installed and configured on your system.

## Installation

1. **Clone the repository:**

   ```bash
   git clone https://github.com/not-lucky/rcloneUnion.git
   cd rcloneUnion
   ```

2. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```


3. **Set up Google API credentials:**

   - Download `credentials.json` from the Google Cloud Console and place it in the project directory.
   - Ensure you have service account files in the `accounts` directory.


## Usage

### Uploading Files/Directories

To upload a file or directory to Google Drive:

```bash
python main.py /path/to/source /path/in/drive [--upload-folder]
```

- Replace `/path/to/source` with the path to your local file or directory.
- Replace `/path/in/drive` with the destination path in Google Drive.
- Use `--upload-folder` to upload the source folder directly to the destination.

### Removing Files/Directories

To remove a file or directory from Google Drive:

```bash
python main.py -r /path/in/drive
```

- Replace `/path/in/drive` with the path to the file or directory in Google Drive.

### Printing Drive Structure

To print the structure of your Google Drive:

```bash
python main.py -s [optional_path]
```

- Omit `optional_path` to print the entire structure.
- Provide a path to filter the structure.

## Backup Management

- **Backups** are created automatically when changes are made.
- Backups include input arguments, generated commands, include files, and database snapshots.
- Backup files are stored in the `backups` directory with timestamps.

## Dependencies

- `google-auth`
- `google-auth-oauthlib`
- `google-api-python-client`
- `rclone` (installed separately)

## Troubleshooting

- **Error: No module named ...**

  Ensure all dependencies are installed.

- **Error: rclone not found**

  Make sure rclone is installed and added to your system's PATH.

- **API Errors:**

  Check your Google API credentials and permissions.
