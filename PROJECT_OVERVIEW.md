# Project Overview - HTML Table Merge Editor

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                         main.py                             │
│                    (Application Entry)                      │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                   MainWindow                                │
│              (widgets/main_window.py)                       │
│                                                             │
│  ┌──────────────┐  ┌─────────────────────────────────┐    │
│  │  File List   │  │      TableEditor                │    │
│  │  Table List  │  │  (widgets/table_editor.py)      │    │
│  └──────────────┘  │  - QTableWidget                 │    │
│                    │  - Cell editing                  │    │
│  ┌──────────────┐  │  - Context menu                 │    │
│  │  Toolbar     │  └─────────────────────────────────┘    │
│  │  (widgets/   │  ┌─────────────────────────────────┐    │
│  │  toolbar.py) │  │     HTMLPreview                 │    │
│  └──────────────┘  │  (widgets/html_preview.py)      │    │
│                    │  - Rendered view                 │    │
│                    │  - Source view                   │    │
│                    └─────────────────────────────────┘    │
└───────────┬──────────────────────────┬─────────────────────┘
            │                          │
            ▼                          ▼
┌───────────────────────┐    ┌──────────────────────┐
│    JSONHandler        │    │    TableModel        │
│ (parsers/json_handler)│    │ (models/table_model) │
│                       │    │                      │
│ - load()              │    │ - Cell class         │
│ - save()              │    │ - merge_cells()      │
│ - get_table_html()    │    │ - split_cell()       │
│ - set_table_html()    │    │ - insert_row/col()   │
└───────────┬───────────┘    │ - delete_row/col()   │
            │                └──────────────────────┘
            │                          ▲
            │                          │
            ▼                          │
┌───────────────────────┐    ┌────────┴─────────────┐
│   HTML Parser         │    │   HTML Generator     │
│ (parsers/html_parser) │    │ (parsers/html_       │
│                       │    │       generator)     │
│ - parse_html_table()  │    │ - generate_html_     │
│   → TableModel        │    │   table()            │
└───────────────────────┘    └──────────────────────┘
```

## Data Flow

### Loading a Table
```
JSON File → JSONHandler.load()
          ↓
    Extract TABLE shapes
          ↓
    Get HTML string → parse_html_table()
          ↓
    TableModel → TableEditor.load_table_model()
          ↓
    Display in QTableWidget
```

### Editing a Table
```
User edits cell → QTableWidget.itemChanged
          ↓
    TableEditor.on_item_changed()
          ↓
    TableModel.set_text()
          ↓
    generate_html_table() → HTMLPreview.set_html()
          ↓
    Update preview
```

### Saving Changes
```
User clicks Save → MainWindow.save_json_file()
          ↓
    generate_html_table(TableModel)
          ↓
    JSONHandler.set_table_html()
          ↓
    JSONHandler.save()
          ↓
    Write to JSON file
```

## Class Responsibilities

### Models Layer
- **Cell**: Stores individual cell data (text, spans, merge status)
- **TableModel**: Manages 2D grid of cells with editing operations

### Parsers Layer
- **html_parser**: Converts HTML string to TableModel
- **html_generator**: Converts TableModel to HTML string
- **json_handler**: Reads/writes JSON files, extracts TABLE shapes

### Widgets Layer
- **MainWindow**: Orchestrates all components, handles file operations
- **TableEditor**: Interactive editing with QTableWidget, merge/split
- **HTMLPreview**: Shows rendered HTML and source code
- **EditorToolBar**: Action buttons with keyboard shortcuts

## Key Features

### Cell Merging System
```
Normal cells:          Merged cells:
┌───┬───┬───┐         ┌───────────┬───┐
│ A │ B │ C │         │     A     │ C │
├───┼───┼───┤   →     │ (colspan=2)   │
│ D │ E │ F │         ├───┬───┬───┤
└───┴───┴───┘         │ D │ E │ F │
                      └───┴───┴───┘

Internal representation:
[A(cs=2)] [REF→A] [C]
[D]       [E]     [F]
```

### Merge-Aware Row/Column Operations
When inserting/deleting rows or columns:
1. Find all cells affected by the operation
2. Adjust rowspan/colspan values
3. Update merge_parent references
4. Maintain grid consistency

## File Structure

```
4. code/
│
├── main.py                    # Entry point
│
├── models/
│   ├── __init__.py
│   └── table_model.py         # Data model (Cell, TableModel)
│
├── parsers/
│   ├── __init__.py
│   ├── html_parser.py         # HTML → TableModel
│   ├── html_generator.py      # TableModel → HTML
│   └── json_handler.py        # JSON I/O
│
├── widgets/
│   ├── __init__.py
│   ├── main_window.py         # Main UI
│   ├── table_editor.py        # Editor widget
│   ├── html_preview.py        # Preview widget
│   └── toolbar.py             # Toolbar widget
│
├── test_parser.py             # Unit test
├── requirements.txt           # Dependencies
├── run.bat                    # Windows launcher
│
└── Documentation/
    ├── README.md              # Project overview
    ├── QUICKSTART.md          # Quick start
    ├── USAGE_GUIDE.md         # Detailed guide
    ├── IMPLEMENTATION_SUMMARY.md
    └── PROJECT_OVERVIEW.md    # This file
```

## Technology Stack

- **Python 3.8+**: Core language
- **PyQt5**: GUI framework
- **html.parser**: Built-in HTML parsing
- **json**: Built-in JSON handling
- **dataclasses**: Cell data structure

## Design Patterns Used

1. **Model-View-Controller (MVC)**
   - Model: TableModel, Cell
   - View: QTableWidget, HTMLPreview
   - Controller: MainWindow, TableEditor

2. **Signal-Slot (Observer)**
   - PyQt signals for component communication
   - Loose coupling between widgets

3. **Strategy Pattern**
   - Separate parsers for HTML input/output
   - Swappable I/O handlers

## Performance Considerations

- **Lazy loading**: Tables loaded only when selected
- **Efficient merging**: O(n) where n = selected cells
- **Minimal redraws**: QTableWidget.blockSignals() during bulk updates

## Security Notes

- **No code execution**: Pure data manipulation
- **File validation**: JSON structure checked before loading
- **Safe HTML parsing**: Uses standard library parser

## Testing Strategy

1. **Unit tests**: Parser logic (test_parser.py)
2. **Integration tests**: Manual testing with sample files
3. **Edge cases**: Complex tables with multiple merges

## Maintenance

### Adding New Features

1. **New cell property**: Add to Cell dataclass
2. **New operation**: Add method to TableModel
3. **New UI action**: Add to toolbar and connect signal

### Debugging

- Enable debug prints in parser
- Check TableModel.grid structure
- Verify HTML output in preview

## Deployment

### Requirements
- Python 3.8+
- PyQt5 5.15+
- Windows/Linux/macOS

### Installation
```bash
pip install -r requirements.txt
```

### Running
```bash
python main.py
```

## Support

For issues or questions:
1. Check USAGE_GUIDE.md
2. Review test_parser.py for examples
3. Examine sample JSON files in `../1. spike/local_data/table_qa/`
