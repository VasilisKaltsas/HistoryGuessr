cd /d "C:\Users\billy\OneDrive\Υπολογιστής\History Game\historyguessr"
start python -m uvicorn main:app --reload
timeout /t 2
start http://localhost:8000
