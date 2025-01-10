# Easy Google Drive Uploader

This script helps you upload files and folders to Google Drive. It's smart because it can use multiple Google accounts to store your files, so you don't run out of space as quickly. It output commands for a tool called `rclone` which is then used for uploading.

The idea for this 

## Features:

*   **Uses Many Accounts:** It spreads your uploads across different Google accounts, so you get more than the usual 15 GB of free storage.
*   **Picks the Best Account:** It automatically chooses the Google account with the most free space for each file.
*   **Shows Your Drive:** You can use it to see a simple list of all your files and folders on Google Drive.


## Prerequisites

1.  **Python 3.6 or higher:** Ensure you have Python 3 installed on your system.
2.  **rclone:** Install `rclone` by following the instructions for your operating system on the official `rclone` website: [https://rclone.org/install/](https://rclone.org/install/)
3.  **Google Cloud Service Accounts:**
    *   Create a Google Cloud project.
    *   Enable the Google Drive API for your project.
    *   Create multiple service accounts (as many as you need) within your project.
    *   For each service account, download the JSON key file and place it in the `accounts` directory.
    *   You might need to share your Google drive folder with each of created service accounts.

## Installation

1.  **Clone the Repository (or Download the Script):**

    ```bash
    git clone https://github.com/not-lucky/rcloneUnion.git
    cd rcloneUnion
    ```

2.  **Create the `accounts` Folder:**

    ```bash
    mkdir accounts
    ```

    Place your downloaded service account JSON key files inside this `accounts` folder.


## Usage

**Basic Syntax:**

```bash
python rclone_serv.py <source> <destination> [options]