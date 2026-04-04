import pyodbc
import os
from dotenv import load_dotenv

load_dotenv()
DB_SERVER = os.getenv('DB_SERVER')
DB_USER = os.getenv('DB_USER')
DB_PASS = os.getenv('DB_PASS')
DB_NAME = 'ForexBrainDB'

conn = pyodbc.connect(f'DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={DB_SERVER};DATABASE={DB_NAME};UID={DB_USER};PWD={DB_PASS}')
cursor = conn.cursor()

# Query to list columns
cursor.execute("""
SELECT COLUMN_NAME 
FROM INFORMATION_SCHEMA.COLUMNS 
WHERE TABLE_NAME = 'Dim_Strategy_Registry'
""")
columns = [row[0] for row in cursor.fetchall()]
print("Columns in Dim_Strategy_Registry:", columns)

cursor.close()
conn.close()