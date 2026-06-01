from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class PageContext:
    project_id: str
    book_id: str
    page_no: int
    json_data: Dict[str, Any] = field(default_factory=dict)
    image_path: str = ""
    ocr_text: str = ""
    config: Dict[str, Any] = field(default_factory=dict)
