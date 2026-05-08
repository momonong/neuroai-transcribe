import os
import json
import csv
import shutil

def anonymize_data():
    data_dir = "data"
    mapping_file = "data_anonymization_mapping.csv"
    
    if not os.path.exists(mapping_file):
        print(f"Error: {mapping_file} not found. Run generate_mapping.py first.")
        return

    mapping = []
    with open(mapping_file, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            mapping.append(row)

    for item in mapping:
        original_name = item["original"]
        anonymized_name = item["anonymized"]
        
        old_path = os.path.join(data_dir, original_name)
        new_path = os.path.join(data_dir, anonymized_name)
        
        if not os.path.exists(old_path):
            print(f"Skipping {old_path}, already renamed or does not exist.")
            continue
            
        print(f"Processing {original_name} -> {anonymized_name}")
        
        # First, rename everything INSIDE the folder that matches the original_name
        for root, dirs, files in os.walk(old_path, topdown=False):
            # Rename files
            for file in files:
                file_path = os.path.join(root, file)
                
                # Content replacement for text files
                if file.endswith((".json", ".srt", ".txt")):
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            content = f.read()
                        
                        if original_name in content:
                            new_content = content.replace(original_name, anonymized_name)
                            with open(file_path, "w", encoding="utf-8") as f:
                                f.write(new_content)
                            print(f"  Updated content in {file_path}")
                    except Exception as e:
                        print(f"  Error reading/writing {file_path}: {e}")
                
                # Rename file itself if it contains the original name
                if original_name in file:
                    new_file_name = file.replace(original_name, anonymized_name)
                    new_file_path = os.path.join(root, new_file_name)
                    os.rename(file_path, new_file_path)
                    print(f"  Renamed file {file} -> {new_file_name}")
            
            # Rename directories (not expected but for safety)
            for dir_name in dirs:
                if original_name in dir_name:
                    dir_path = os.path.join(root, dir_name)
                    new_dir_name = dir_name.replace(original_name, anonymized_name)
                    new_dir_path = os.path.join(root, new_dir_name)
                    os.rename(dir_path, new_dir_path)
                    print(f"  Renamed directory {dir_name} -> {new_dir_name}")

        # Finally, rename the subject directory itself
        os.rename(old_path, new_path)
        print(f"Renamed top directory {old_path} -> {new_path}")

if __name__ == "__main__":
    anonymize_data()
