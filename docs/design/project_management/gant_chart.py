import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime

# 1. Define the Tasks and Timeline
tasks = [
    ("Phase 1: Design (ERD/DFD)", "2026-01-15", "2026-02-01", 1.0), # 1.0 = Done
    ("Phase 2: Infra Setup (Docker/SQL)", "2026-02-02", "2026-02-05", 0.5), # 0.5 = In Progress
    ("Phase 3: Data Ingestion (Oanda)", "2026-02-06", "2026-02-12", 0.0),
    ("Phase 4: Regime Detection Logic", "2026-02-13", "2026-02-24", 0.0),
    ("Phase 5: Strategy & Signals", "2026-02-25", "2026-03-08", 0.0),
    ("Phase 6: Backtesting Loop", "2026-03-09", "2026-03-22", 0.0),
    ("Phase 7: Power BI & Reporting", "2026-03-23", "2026-04-08", 0.0),
]

# 2. Setup the Plot
fig, ax = plt.subplots(figsize=(12, 6))

# Colors for bars
colors = ['#2ecc71', '#f1c40f', '#3498db', '#3498db', '#3498db', '#9b59b6', '#e74c3c']

# 3. Draw the Bars
y_pos = range(len(tasks))
for i, (task, start, end, progress) in enumerate(tasks):
    start_date = datetime.strptime(start, "%Y-%m-%d")
    end_date = datetime.strptime(end, "%Y-%m-%d")
    duration = (end_date - start_date).days
    
    # Draw the main bar
    ax.barh(i, duration, left=start_date, height=0.5, align='center', color=colors[i], alpha=0.8, edgecolor='black')
    
    # Add text label
    ax.text(start_date, i, f"  {task}", va='center', ha='left', fontweight='bold', color='black')

# 4. Formatting
ax.set_yticks([]) # Hide y-axis numbers
ax.set_title('The Scalable Brain: Project Timeline', fontsize=16, fontweight='bold')
ax.xaxis_date()
ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
ax.xaxis.set_major_locator(mdates.DayLocator(interval=10))
plt.grid(axis='x', linestyle='--', alpha=0.5)

# Add "Today" Line
today = datetime.strptime("2026-02-02", "%Y-%m-%d")
plt.axvline(today, color='red', linestyle='--', linewidth=2, label="Today")
plt.legend()

# 5. Save
plt.tight_layout()
plt.savefig('Project_Gantt_Chart.png')
print("✅ Gantt Chart generated: Project_Gantt_Chart.png")