import os


class FileManager:
    def scan_local_directory(self, source_dir, destination_base_path, upload_folder):
        """Scans a local directory and returns file information."""

        files_info = []

        for root, dirs, files in os.walk(source_dir):
            relative_root = os.path.relpath(root, source_dir)

            if upload_folder:
                current_destination_path = (
                    os.path.join(
                        destination_base_path,
                        os.path.basename(source_dir),
                        relative_root,
                    )
                    if relative_root != "."
                    else os.path.join(
                        destination_base_path, os.path.basename(source_dir)
                    )
                )
            else:
                current_destination_path = (
                    os.path.join(destination_base_path, relative_root)
                    if relative_root != "."
                    else destination_base_path
                )

            for file in files:
                file_path = os.path.join(root, file)
                file_size = os.path.getsize(file_path)

                destination_path = current_destination_path
                destination_path_with_name = os.path.join(
                    current_destination_path, file
                )
                relative_file_path = os.path.relpath(file_path, source_dir)

                files_info.append(
                    {
                        "filename": file,
                        "relative_file_path": relative_file_path,
                        "size": file_size,
                        "destination_path": destination_path,
                        "destination_path_with_name": destination_path_with_name,
                        # "full_file_path": file_path,
                    }
                )
        return files_info

    def get_file_info(self, source, destination):
        """Gets info for a single file"""
        file_size = os.path.getsize(source)
        destination_with_filename = (
            f"{destination}/{os.path.basename(source)}"
            if destination
            else os.path.basename(source)
        )
        destination_path = destination
        return {
            "filename": os.path.basename(source),
            "relative_file_path": os.path.basename(source),
            "size": file_size,
            "destination_path": destination_path,
            "destination_path_with_name": destination_with_filename,
            # "full_file_path": source,
        }
