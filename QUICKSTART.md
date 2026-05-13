# Quick Start Guide

## Setup (One-time)

```bash
# Navigate to project directory
cd "C:\Users\박재현\Documents\[프로젝트]26pj077_엘지씨엔에스\4. code"

# Install dependencies
pip install PyQt5
```

## Run

### Option 1: Double-click
Double-click `run.bat`

### Option 2: Command line
```bash
python main.py
```

## Basic Operations

### 1. Open File
- Click **Open** button
- Navigate to: `..\1. spike\local_data\table_qa\`
- Select any JSON file (e.g., `국가 정신건강현황 보고서_2022_0011.json`)

### 2. Edit Table
- **Edit text**: Click cell, type, press Enter
- **Merge cells**: Drag to select cells → Click **Merge** button
- **Split cell**: Click merged cell → Click **Split** button
- **Add row**: Click **+Row** button
- **Delete row**: Click **-Row** button
- **Add column**: Click **+Col** button
- **Delete column**: Click **-Col** button

### 3. Save
- Click **Save** button (or press `Ctrl+S`)

## Keyboard Shortcuts

- `Ctrl+O`: Open file
- `Ctrl+S`: Save file
- Right-click: Context menu with all operations

## Need Help?

See `USAGE_GUIDE.md` for detailed instructions.

## Test the Application

```bash
# Run parser test
python test_parser.py
```

Expected output: Shows HTML parsing, grid representation, and merge operation working correctly.

## Troubleshooting

**Problem**: `ModuleNotFoundError: No module named 'PyQt5'`
**Solution**: Run `pip install PyQt5`

**Problem**: Cannot find JSON files
**Solution**: Make sure you're in the correct directory. The table data is in `..\1. spike\local_data\table_qa\`

**Problem**: Application doesn't start
**Solution**: Check Python version with `python --version` (requires 3.8+)
