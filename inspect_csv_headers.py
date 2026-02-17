import pandas as pd
import os

files = ['NSE.csv', 'BSE.csv', 'MCX.csv']
for f in files:
    if os.path.exists(f):
        df = pd.read_csv(f, nrows=0)
        print(f"File: {f}")
        print(f"Columns: {list(df.columns)}")
        print("-" * 20)
