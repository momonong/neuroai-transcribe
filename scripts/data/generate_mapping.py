import os
import json
import csv

def anonymize():
    data_dir = "data"
    mapping_file = "data_anonymization_mapping.csv"
    
    # Get all directories in data/ except default_demo
    dirs = [d for d in os.listdir(data_dir) if os.path.isdir(os.path.join(data_dir, d)) and d != "default_demo"]
    dirs.sort() # Ensure consistent ordering
    
    mapping = []
    for i, original_name in enumerate(dirs, 1):
        anonymized_name = f"subject{i:02d}"
        mapping.append({"original": original_name, "anonymized": anonymized_name})
        
    # Write CSV mapping
    with open(mapping_file, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["original", "anonymized"])
        writer.writeheader()
        writer.writerows(mapping)
        
    print(f"Mapping saved to {mapping_file}")
    for item in mapping:
        print(f"{item['original']} -> {item['anonymized']}")

if __name__ == "__main__":
    anonymize()
