# HTML Table Merge Editor - Usage Guide

## Installation

1. Install Python 3.8 or higher
2. Install dependencies:
```bash
cd "C:\Users\박재현\Documents\[프로젝트]26pj077_엘지씨엔에스\4. code"
pip install -r requirements.txt
```

## Running the Application

```bash
python main.py
```

## Interface Overview

```
┌─────────────────────────────────────────────────────────┐
│ [Open] [Save] | [Merge] [Split] | [+Row][-Row][+Col][-Col]│
├──────────┬──────────────────────────────────────────────┤
│ Current  │                                              │
│ File:    │         Table Editor                         │
│ file.json│         (Edit cells, drag to select)         │
│          │                                              │
│ Tables:  │                                              │
│ □ Table 1├──────────────────────────────────────────────┤
│ ■ Table 2│  Preview                                     │
│ □ Table 3│  [Rendered] [HTML Source]                    │
└──────────┴──────────────────────────────────────────────┘
```

## Step-by-Step Workflow

### 1. Open a File

- Click **Open** button (or press `Ctrl+O`)
- Navigate to: `C:\Users\박재현\Documents\[프로젝트]26pj077_엘지씨엔에스\1. spike\local_data\table_qa\`
- Select a JSON file (e.g., `국가 정신건강현황 보고서_2022_0011.json`)

### 2. Select a Table

- The left panel shows all tables in the file
- Click on a table name (e.g., "Table 1") to load it into the editor

### 3. Edit Table Content

#### Edit Cell Text
- Click on any cell to select it
- Type to modify the text
- Press Enter or click elsewhere to confirm

#### Select Multiple Cells
- Click and drag to select a rectangular area
- Or click first cell, then Shift+click last cell

### 4. Merge Cells

**Method 1: Toolbar**
1. Select multiple cells by dragging
2. Click **Merge** button

**Method 2: Context Menu**
1. Select multiple cells
2. Right-click
3. Select "Merge Cells"

**Result:** Selected cells combine into one with colspan/rowspan

### 5. Split Cells

**Method 1: Toolbar**
1. Click on a merged cell
2. Click **Split** button

**Method 2: Context Menu**
1. Click on a merged cell
2. Right-click
3. Select "Split Cell"

**Result:** Merged cell splits back into individual cells

### 6. Insert/Delete Rows

**Insert Row:**
1. Click on a cell where you want to insert a row above
2. Click **+Row** button (or right-click → "Insert Row")

**Delete Row:**
1. Click on a cell in the row you want to delete
2. Click **-Row** button (or right-click → "Delete Row")

### 7. Insert/Delete Columns

**Insert Column:**
1. Click on a cell where you want to insert a column to the left
2. Click **+Col** button (or right-click → "Insert Column")

**Delete Column:**
1. Click on a cell in the column you want to delete
2. Click **-Col** button (or right-click → "Delete Column")

### 8. Preview Changes

The bottom panel shows two tabs:
- **Rendered:** Visual preview of the HTML table
- **HTML Source:** Raw HTML code

Changes update automatically as you edit.

### 9. Save Changes

- Click **Save** button (or press `Ctrl+S`)
- Changes are saved back to the original JSON file
- The HTML is stored in `shapes[i].flags.text`

## Tips and Tricks

### Keyboard Shortcuts
- `Ctrl+O`: Open file
- `Ctrl+S`: Save file
- Arrow keys: Navigate cells
- Tab: Move to next cell
- Shift+Tab: Move to previous cell

### Working with Complex Tables

1. **Large merged cells:** When selecting cells that span multiple rows/columns, click on the top-left cell of the merged area

2. **Nested merges:** You cannot merge cells that are already part of different merged areas. Split them first, then merge as needed.

3. **Row/column operations on merged cells:** When inserting/deleting rows or columns that intersect with merged cells, the span values are automatically adjusted.

### Best Practices

1. **Save frequently:** Click Save after major changes to avoid data loss

2. **Check preview:** Always verify the Rendered view before saving to ensure the table looks correct

3. **Test with HTML Source:** If you're familiar with HTML, check the source tab to verify colspan/rowspan attributes are correct

4. **Backup files:** Before making extensive edits, make a copy of your JSON files

## Troubleshooting

### Problem: Table looks wrong in preview
- Check the HTML Source tab for malformed HTML
- Try splitting and re-merging problematic cells
- Reload the file to start fresh

### Problem: Cannot merge cells
- Ensure you've selected at least 2 cells
- Make sure selected cells form a rectangular area
- Check that cells aren't already part of other merged areas

### Problem: Save fails
- Check that the JSON file isn't open in another program
- Verify you have write permissions to the file
- Check the file path is correct

### Problem: Application crashes
- Ensure PyQt5 is properly installed: `pip install --upgrade PyQt5`
- Check Python version is 3.8 or higher
- Try with a smaller/simpler table file first

## Example Workflow

Let's edit a table with merged headers:

1. Open `국가 정신건강현황 보고서_2022_0011.json`
2. Select "Table 1"
3. Click on the merged header cell (first row)
4. Edit the text to "Updated Header"
5. Select cells B2 and C2 (drag to select)
6. Click **Merge** to combine them
7. Check the Preview to verify it looks correct
8. Click **Save** to write changes to file

## Data Format Reference

The application reads/writes JSON files with this structure:

```json
{
  "shapes": [
    {
      "label": "TABLE",
      "flags": {
        "text": "<table><tr><td>...</td></tr></table>"
      }
    }
  ]
}
```

The HTML table format supports:
- `<th>` for header cells (displayed in bold)
- `<td>` for data cells
- `colspan="N"` for horizontal merging
- `rowspan="N"` for vertical merging

Example merged table:
```html
<table>
  <tr>
    <th colspan="3">Title</th>
  </tr>
  <tr>
    <td rowspan="2">A</td>
    <td>B</td>
    <td>C</td>
  </tr>
  <tr>
    <td colspan="2">D</td>
  </tr>
</table>
```
