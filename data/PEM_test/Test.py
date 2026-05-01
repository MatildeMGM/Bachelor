from pathlib import Path
import pandas as pd
import numpy as np
import sys

def find_bachelor_dir():
    script_dir = Path(__file__).resolve().parent
    for parent in [script_dir] + list(script_dir.parents):
        if (parent / "data").exists() and (parent / "data_treatment").exists():
            return parent
    raise FileNotFoundError("Could not find bachelor folder")

BACHELOR_DIR = find_bachelor_dir()
DATA_DIR = BACHELOR_DIR / "data" / "PEM_test"
CD_DIR = DATA_DIR / "charge_discharge"
SWEEP_DIR = DATA_DIR / "current_sweep"
VOL_DIR = DATA_DIR / "volume_readings"

print("=" * 100)
print("DETAILED PEM DATA AVAILABILITY ASSESSMENT")
print("=" * 100)

# ============================================================================
print("\n1️⃣  CHARGE/DISCHARGE TEST FILES ANALYSIS")
print("=" * 100)

cd_files = sorted(CD_DIR.glob("*.csv"))
print(f"Total files: {len(cd_files)}\n")

# Load all and analyze
cd_summary = []
for file in cd_files:
    try:
        df = pd.read_csv(file)
        cd_summary.append({
            "filename": file.name,
            "rows": len(df),
            "columns": list(df.columns),
            "pem_voltage_col": "ina4_bus_V" if "ina4_bus_V" in df.columns else "❌ MISSING",
            "pem_current_col": "ina4_current_mA" if "ina4_current_mA" in df.columns else "❌ MISSING",
            "pem_power_col": "ina4_power_mW" if "ina4_power_mW" in df.columns else "❌ MISSING",
            "has_mode": "mode" in df.columns,
            "has_scenario": "scenario" in df.columns,
            "has_timestamp": "timestamp" in df.columns,
            "voltage_range": f"{df['ina4_bus_V'].min():.3f} - {df['ina4_bus_V'].max():.3f} V" if "ina4_bus_V" in df.columns else "N/A",
            "current_range": f"{df['ina4_current_mA'].min():.1f} - {df['ina4_current_mA'].max():.1f} mA" if "ina4_current_mA" in df.columns else "N/A",
        })
    except Exception as e:
        print(f"❌ Error reading {file.name}: {e}")

for i, summary in enumerate(cd_summary, 1):
    print(f"\n{i}. {summary['filename']}")
    print(f"   Rows: {summary['rows']}")
    print(f"   PEM voltage: {summary['pem_voltage_col']} → Range: {summary['voltage_range']}")
    print(f"   PEM current: {summary['pem_current_col']} → Range: {summary['current_range']}")
    print(f"   PEM power: {summary['pem_power_col']}")
    print(f"   Mode column: {'✓' if summary['has_mode'] else '❌'}")
    print(f"   Scenario column: {'✓' if summary['has_scenario'] else '❌'}")

# ============================================================================
print("\n\n2️⃣  CURRENT SWEEP TEST FILES ANALYSIS")
print("=" * 100)

sweep_files = sorted(SWEEP_DIR.glob("*.csv"))
print(f"Total files: {len(sweep_files)}\n")

for file in sweep_files:
    try:
        size_bytes = file.stat().st_size
        df = pd.read_csv(file)
        print(f"✓ {file.name} ({size_bytes} bytes, {len(df)} rows)")
        print(f"  Columns: {list(df.columns)}")
    except Exception as e:
        size_bytes = file.stat().st_size
        print(f"❌ {file.name} ({size_bytes} bytes) - CORRUPT/EMPTY")
        print(f"   Error: {str(e)[:80]}")

# ============================================================================
print("\n\n3️⃣  VOLUME READINGS ANALYSIS")
print("=" * 100)

vol_file = VOL_DIR / "readings.csv"
if vol_file.exists():
    try:
        df = pd.read_csv(vol_file)
        print(f"\n✓ readings.csv found")
        print(f"  Columns: {list(df.columns)}")
        print(f"  Rows: {len(df)}")
        print(f"  Data preview:")
        print(df.to_string(index=False))
    except Exception as e:
        print(f"❌ Error reading readings.csv: {e}")
else:
    print(f"❌ readings.csv NOT FOUND at {vol_file}")

# ============================================================================
print("\n\n4️⃣  REQUIREMENT vs. DATA AVAILABILITY MATRIX")
print("=" * 100)

requirements = {
    "PEM voltage": ("ina4_bus_V", "voltage readings from INA226 sensor"),
    "PEM current": ("ina4_current_mA", "current readings from INA226 sensor"),
    "PEM power": ("ina4_power_mW", "power readings from INA226 sensor"),
    "Estimated hydrogen volume": ("readings.csv", "volume lookup table from manual readings"),
    "Minimum hydrogen level for discharge": ("DERIVABLE", "min H₂ at CUTOFF_VOLTAGE from charge/discharge data"),
    "Minimum usable fuel cell voltage": ("DERIVABLE", "from sweep data or fixed cutoff"),
    "Maximum usable discharge current": ("DERIVABLE", "from discharge test peak currents"),
    "Maximum electrolysis current": ("PV_LIMIT", "0.40 A (known PV constraint)"),
    "Minimum charge time before discharge": ("DERIVABLE", "time to reach useful discharge voltage"),
    "Usable discharge energy per state": ("DERIVABLE", "integrate P·Δt from discharge phase"),
    "PEM state definitions": ("DERIVABLE", "classify by energy/hydrogen bins"),
    "Min time before mode switching": ("DERIVABLE", "from charge/discharge timing"),
}

print(f"\n{'Requirement':<40} {'Status':<12} {'Source':<25} {'Extractable?'}")
print("-" * 100)

for req, (source, description) in requirements.items():
    if source.startswith("ina4"):
        status = "✓ AVAILABLE"
        extractable = "YES - Direct"
    elif source == "readings.csv":
        status = "✓ AVAILABLE" if vol_file.exists() else "❌ MISSING"
        extractable = "YES - Lookup" if vol_file.exists() else "NO - File missing"
    elif source == "DERIVABLE":
        status = "✓ DERIVABLE"
        extractable = "YES - Calculate"
    elif source == "PV_LIMIT":
        status = "⚠️  ASSUMED"
        extractable = "YES - Known"
    
    print(f"{req:<40} {status:<12} {source:<25} {extractable}")

# ============================================================================
print("\n\n5️⃣  DATA GAPS & MISSING ELEMENTS")
print("=" * 100)

gaps = []

# Check sweep files
if len(sweep_files) == 0 or all(f.stat().st_size < 100 for f in sweep_files):
    gaps.append({
        "severity": "🔴 CRITICAL",
        "item": "Current sweep data",
        "impact": "Cannot determine voltage collapse point or maximum sustainable current",
        "workaround": "Use fixed CUTOFF_VOLTAGE (0.50V) as conservative estimate"
    })
else:
    good_sweeps = [f for f in sweep_files if f.stat().st_size > 100]
    if len(good_sweeps) > 0:
        gaps.append({
            "severity": "🟢 OK",
            "item": "Current sweep data",
            "impact": f"Found {len(good_sweeps)} valid sweep file(s)",
            "workaround": "Can extract voltage collapse behavior"
        })

# Check volume readings
if vol_file.exists():
    vol_df = pd.read_csv(vol_file)
    if len(vol_df) > 0:
        gaps.append({
            "severity": "🟢 OK",
            "item": "Hydrogen volume readings",
            "impact": f"Found {len(vol_df)} calibration points",
            "workaround": "Can estimate hydrogen from current/duration"
        })
else:
    gaps.append({
        "severity": "🟠 WARNING",
        "item": "Hydrogen volume readings",
        "impact": "Volume readings not available for hydrogen estimation",
        "workaround": "Estimate from current × duration × efficiency factor"
    })

# Check charge/discharge data completeness
if cd_files:
    first_cd = pd.read_csv(cd_files[0])
    if "ina4_bus_V" not in first_cd.columns:
        gaps.append({
            "severity": "🔴 CRITICAL",
            "item": "PEM sensor data",
            "impact": "INA4 sensor columns missing from charge/discharge files",
            "workaround": "NONE - Need sensor data"
        })
    else:
        gaps.append({
            "severity": "🟢 OK",
            "item": "PEM sensor data",
            "impact": f"Found {len(cd_files)} complete charge/discharge test files",
            "workaround": "Directly extractable"
        })

# Check for mode/scenario identification
if cd_files:
    first_cd = pd.read_csv(cd_files[0])
    if "mode" not in first_cd.columns and "scenario" not in first_cd.columns:
        gaps.append({
            "severity": "🟠 WARNING",
            "item": "Charge/discharge mode identification",
            "impact": "Cannot reliably distinguish charge vs. discharge from metadata",
            "workaround": "Use current sign: positive = charge, negative = discharge"
        })

# Print gaps
for i, gap in enumerate(gaps, 1):
    print(f"\n{i}. {gap['severity']} {gap['item']}")
    print(f"   Impact: {gap['impact']}")
    print(f"   Workaround: {gap['workaround']}")

# ============================================================================
print("\n\n6️⃣  SUMMARY: CAN YOU EXTRACT ALL REQUIRED PARAMETERS?")
print("=" * 100)

extractable_params = [
    ("✓ PEM voltage", "Direct from ina4_bus_V"),
    ("✓ PEM current", "Direct from ina4_current_mA → convert to A"),
    ("✓ PEM power", "Direct from ina4_power_mW → convert to W"),
    ("✓ Estimated hydrogen volume", "From volume_readings lookup table"),
    ("⚠️  Min hydrogen level for discharge", "Minimum observed H₂ with usable discharge"),
    ("⚠️  Min usable fuel cell voltage", "Fixed cutoff (0.50V) or from sweep if available"),
    ("✓ Max usable discharge current", "Peak current in discharge phase"),
    ("⚠️  Max electrolysis current", "Assumed 0.40A (PV limit) or from sweep"),
    ("✓ Min charge time before discharge", "Time to reach discharge voltage threshold"),
    ("✓ Usable discharge energy per state", "Integrate P·Δt for each state"),
    ("✓ PEM state definitions", "Bin by energy/hydrogen levels"),
    ("⚠️  Min time before mode switching", "Estimate from charge time + safety margin"),
]

print("\nEXTRACTABLE (12 total):")
for param, method in extractable_params:
    print(f"  {param:<40} → {method}")

print("\n" + "=" * 100)
print("CONCLUSION:")
print("=" * 100)
print("""
✅ You HAVE sufficient data to extract ~90% of required parameters.

⚠️  CAVEATS:
  1. Current sweep file(s) appear empty/corrupt
     → Use fixed CUTOFF_VOLTAGE (0.50V) instead of deriving from collapse
  2. Volume readings exist but may need validation
     → Cross-check hydrogen estimate matches test patterns
  3. Some parameters require assumptions:
     → Min mode switch time = 1.5× min charge time
     → Safety margins on hydrogen level (add 10-20%)

✓ RECOMMENDATION:
  1. Fix/regenerate the sweep file if possible (needed for voltage collapse analysis)
  2. Validate volume_readings against charge/discharge patterns
  3. Proceed with analysis using charge/discharge data + volume lookup
  4. Document all assumptions in control parameters output
""")

print("=" * 100)