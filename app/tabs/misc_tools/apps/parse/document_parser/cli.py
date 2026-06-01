from __future__ import annotations

import argparse
import logging

from .document_parser import DocumentParser
from .errors import ParserError


def main() -> int:
    parser = argparse.ArgumentParser(description="Parse authoring-tool outputs into document-level JSON.")
    parser.add_argument(
        "--config",
        default="config/parser_config.json",
        help="Path to the parser config JSON file.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    try:
        DocumentParser.from_config_path(args.config).parse_all_documents()
    except ParserError as exc:
        logging.error("파서 실행 중 오류가 발생했습니다: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
