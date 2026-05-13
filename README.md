# HTML Table Merge Editor (PyQt5)

A desktop application for visually editing HTML tables stored in JSON files. Supports cell merging/splitting (colspan/rowspan), row/column insertion/deletion, and real-time HTML preview.

## Features

- Load JSON files containing HTML table data
- Visual table editing with QTableWidget
- Cell merging and splitting (colspan/rowspan support)
- Row and column insertion/deletion
- Real-time HTML preview (rendered and source views)
- Context menu for quick operations
- Save changes back to JSON files

## Installation

```bash
pip install -r requirements.txt
```

## Usage

```bash
python main.py
```

## Workflow

1. Click "Open" to load a JSON file from `1. spike/local_data/table_qa/`
2. Select a table from the left panel
3. Edit the table:
   - Click cells to edit text
   - Drag to select multiple cells
   - Right-click for context menu (merge, split, insert/delete rows/cols)
   - Use toolbar buttons for quick operations
4. Preview changes in the bottom panel (Rendered/HTML Source tabs)
5. Click "Save" to write changes back to the JSON file

## Data Format

- JSON path: `shapes[i].flags.text` where `shapes[i].label == "TABLE"`
- HTML format: Standard `<table>` with colspan/rowspan attributes
- Multiple TABLE shapes per JSON file supported

## Keyboard Shortcuts

- `Ctrl+O`: Open file
- `Ctrl+S`: Save file

## Project Structure

```
4. code/
  main.py                    # Application entry point
  models/
    table_model.py           # Internal grid data model (Cell, TableModel)
  parsers/
    html_parser.py           # HTML → TableModel parsing
    html_generator.py        # TableModel → HTML generation
    json_handler.py          # JSON file I/O
  widgets/
    main_window.py           # Main window layout
    table_editor.py          # QTableWidget-based table editor
    html_preview.py          # HTML rendering preview
    toolbar.py               # Editor toolbar
```

## Architecture

### Data Model (`models/table_model.py`)
- `Cell`: Represents a single cell with text, rowspan, colspan, merge status
- `TableModel`: 2D grid of cells with merge/split/insert/delete operations

### Parsers
- `html_parser.py`: Parses HTML table strings into TableModel using `html.parser.HTMLParser`
- `html_generator.py`: Generates HTML table strings from TableModel
- `json_handler.py`: Handles JSON file I/O and table shape management

### Widgets
- `table_editor.py`: Interactive table editor with merge/split/insert/delete support
- `html_preview.py`: Dual-view preview (rendered HTML + source code)
- `toolbar.py`: Toolbar with editing actions
- `main_window.py`: Main application window with file list and table list panels

## Testing

Test with complex merged tables from `1. spike/local_data/table_qa/` directory, especially files with multiple colspan/rowspan combinations.
