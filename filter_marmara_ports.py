import os
import pandas as pd

# Define absolute path based on user's terminal environment
folder_path = r"C:\Users\Lenovo\Desktop\BITIRME SON"
os.chdir(folder_path)

# Official IHO boundary limits for Sea of Marmara
lat_min, lat_max = 39.9989, 41.2330
lon_min, lon_max = 26.1742, 29.9422

# Find the file dynamically
target_file = None
all_files = os.listdir('.')

for file in all_files:
    if "wpi" in file.lower():
        target_file = file
        break

if not target_file:
    print("[-] Error: No file containing 'WPI' was found in this folder.")
    print("Files in directory:", all_files)
    exit()

print(f"[+] Found dataset: {target_file}")

# Load the file based on its extension
ext = os.path.splitext(target_file)[1].lower()
try:
    if ext == '.csv':
        df = pd.read_csv(target_file)
    elif ext == '.xls':
        df = pd.read_excel(target_file, engine='xlrd')
    elif ext == '.xlsx':
        df = pd.read_excel(target_file, engine='openpyxl')
    else:
        print(f"[-] Unsupported file extension: {ext}")
        exit()
except Exception as e:
    print(f"[-] Error reading the file: {e}")
    exit()

# Clean column headers
df.columns = df.columns.str.strip()

# Detect Latitude and Longitude columns
lat_col = [c for c in df.columns if c.lower() in ['latitude', 'lat', 'lat_deg', 'y']][0]
lon_col = [c for c in df.columns if c.lower() in ['longitude', 'long', 'lon', 'lon_deg', 'x']][0]

print(f"[+] Using columns -> Lat: '{lat_col}', Lon: '{lon_col}'")

# Filter data
marmara_ports = df[
    (df[lat_col] >= lat_min) & (df[lat_col] <= lat_max) &
    (df[lon_col] >= lon_min) & (df[lon_col] <= lon_max)
]

# Export
output_xlsx = "marmara_denizi_limanlari.xlsx"
output_csv = "marmara_denizi_limanlari.csv"

marmara_ports.to_excel(output_xlsx, index=False)
marmara_ports.to_csv(output_csv, index=False, encoding='utf-8-sig')

print(f"[+] Filtering successful! Found {len(marmara_ports)} ports.")
print(f"[+] Saved outputs to: {output_xlsx} and {output_csv}")
