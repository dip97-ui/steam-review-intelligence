"""Run the full data pipeline end to end: clean -> analyze."""
import subprocess
import sys

for script in ["scripts/clean_data.py", "scripts/analyze.py"]:
    print(f"\n=== {script} ===")
    result = subprocess.run([sys.executable, script])
    if result.returncode != 0:
        sys.exit(result.returncode)
print("\nPipeline done. Start the dashboard with: python app.py")
