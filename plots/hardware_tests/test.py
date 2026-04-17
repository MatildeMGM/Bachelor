import pandas as pd

file = r"C:\Users\matil\OneDrive\Skrivebord\Studieportefølje\repos\Bachelor\data\hardware_tests\sensor40_current_3.3.xlsx"

xls = pd.ExcelFile(file)
print(xls.sheet_names)
