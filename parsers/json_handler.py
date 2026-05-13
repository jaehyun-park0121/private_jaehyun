import json
from pathlib import Path
from typing import Optional


class JSONHandler:
    """Handle reading and writing JSON files with table data."""

    def __init__(self, file_path: Optional[str] = None):
        self.file_path = file_path
        self.data: dict = {}
        self.table_shapes: list[dict] = []

    def load(self, file_path: str) -> bool:
        """Load JSON file and extract table shapes."""
        try:
            self.file_path = file_path
            with open(file_path, 'r', encoding='utf-8') as f:
                self.data = json.load(f)

            self.table_shapes = [
                shape for shape in self.data.get('shapes', [])
                if shape.get('label') == 'TABLE'
            ]

            return True
        except Exception as e:
            print(f"Error loading JSON file: {e}")
            return False

    def get_table_count(self) -> int:
        """Get the number of table shapes in the file."""
        return len(self.table_shapes)

    def get_table_html(self, index: int) -> str:
        """Get HTML content of a specific table by index."""
        if 0 <= index < len(self.table_shapes):
            return self.table_shapes[index].get('flags', {}).get('text', '')
        return ''

    def set_table_html(self, index: int, html: str) -> bool:
        """Set HTML content of a specific table by index."""
        if 0 <= index < len(self.table_shapes):
            if 'flags' not in self.table_shapes[index]:
                self.table_shapes[index]['flags'] = {}
            self.table_shapes[index]['flags']['text'] = html
            return True
        return False

    def save(self, file_path: Optional[str] = None) -> bool:
        """Save modified data back to JSON file."""
        try:
            save_path = file_path or self.file_path
            if not save_path:
                return False

            for i, shape in enumerate(self.data.get('shapes', [])):
                if shape.get('label') == 'TABLE':
                    for table_shape in self.table_shapes:
                        if shape is table_shape:
                            break

            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)

            return True
        except Exception as e:
            print(f"Error saving JSON file: {e}")
            return False

    def get_table_info(self, index: int) -> dict:
        """Get metadata about a specific table."""
        if 0 <= index < len(self.table_shapes):
            shape = self.table_shapes[index]
            return {
                'index': index,
                'label': shape.get('label', ''),
                'shape_type': shape.get('shape_type', ''),
                'points': shape.get('points', []),
                'group_id': shape.get('group_id', None),
            }
        return {}
