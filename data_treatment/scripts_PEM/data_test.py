from pathlib import Path
import pandas as pd
import numpy as np

def find_bachelor_dir():
    script_dir = Path(__file__).resolve().parent
    for parent in [script_dir] + list(script_dir.parents):
        if (parent / "data").exists() and (parent / "data_treatment").exists():
            return parent
    raise FileNotFoundError("Could not find bachelor folder")

BACHELOR_DIR = find_bachelor_dir()
DATA_DIR = BACHELOR_DIR / "data" / "PEM_test"

print("=" * 80)
print("PEM TEST DATA FOLDER ASSESSMENT")
print("=" * 80)

# List all subdirectories
print("\n📁 FOLDER STRUCTURE:")
for item in sorted(DATA_DIR.iterdir()):
    if item.is_dir():
        file_count = len(list(item.glob("*.csv")))
        print(f"  └─ {item.name}/ ({file_count} CSV files)")
        for csv_file in sorted(item.glob("*.csv"))[:3]:  # Show first 3
            print(f"     ├─ {csv_file.name}")
        if file_count > 3:
            print(f"     └─ ... and {file_count - 3} more")
    elif item.is_file():
        print(f"  └─ {item.name} (file)")

# Analyze charge/discharge files
print("\n" + "=" * 80)
print("CHARGE/DISCHARGE TEST FILES:")
print("=" * 80)

cd_files = sorted((DATA_DIR / "charge_discharge").glob("*.csv"))
print(f"\nTotal files: {len(cd_files)}\n")

if len(cd_files) > 0:
    sample_file = cd_files[0]
    df = pd.read_csv(sample_file)
    print(f"Sample file: {sample_file.name}")
    print(f"Columns available: {list(df.columns)}")
    print(f"Shape: {df.shape}")
    print(f"\nFirst few rows:")
    print(df.head())

# Analyze sweep files
print("\n" + "=" * 80)
print("CURRENT SWEEP TEST FILES:")
print("=" * 80)

sweep_files = sorted((DATA_DIR / "current_sweep").glob("*.csv"))
print(f"\nTotal files: {len(sweep_files)}\n")

if len(sweep_files) > 0:
    sample_file = sweep_files[0]
    df = pd.read_csv(sample_file)
    print(f"Sample file: {sample_file.name}")
    print(f"Columns available: {list(df.columns)}")
    print(f"Shape: {df.shape}")
    print(f"\nFirst few rows:")
    print(df.head())

# Check volume readings
print("\n" + "=" * 80)
print("VOLUME READINGS:")
print("=" * 80)

vol_file = DATA_DIR / "volume_readings" / "readings.csv"
if vol_file.exists():
    df = pd.read_csv(vol_file)
    print(f"\nFile: {vol_file.name}")
    print(f"Columns: {list(df.columns)}")
    print(f"Shape: {df.shape}")
    print(f"\nData preview:")
    print(df)
else:
    print("❌ Volume readings file NOT FOUND")

print("\n" + "=" * 80)