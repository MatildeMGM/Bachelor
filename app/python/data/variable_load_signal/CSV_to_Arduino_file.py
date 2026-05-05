import pandas as pd

csv_path = "scaled_may_power_profile_15min.csv"
df = pd.read_csv(csv_path)

with open("profile_csv.h", "w") as f:
    f.write("#pragma once\n\n")
    f.write('const char PROFILE_CSV[] = R"CSV(\n')
    f.write("time_slot,time_of_day,power_mW\n")

    for _, row in df.iterrows():
        power = f"{row['power_mW']:.9f}".rstrip("0").rstrip(".")
        f.write(f"{int(row['time_slot'])},{row['time_of_day']},{power}\n")

    f.write(')CSV";\n')