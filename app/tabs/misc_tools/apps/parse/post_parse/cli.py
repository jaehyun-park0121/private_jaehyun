from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .validator import validate_output_root


def main() -> int:
    parser = argparse.ArgumentParser(
        description="파싱 결과 JSON의 Output 스키마를 검증합니다."
    )
    parser.add_argument(
        "--config",
        default="post_parse/post_parse_config.json",
        help="post_parse_config.json 경로",
    )
    parser.add_argument(
        "--output-root",
        required=True,
        help="파싱 결과물이 저장된 루트 디렉토리",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    try:
        raw = json.loads(Path(args.config).read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        logging.error("설정 파일 로드 실패: %s", exc)
        return 1

    field_validation_enabled = bool(
        raw.get("field_validation_enabled", raw.get("enabled", False))
    )
    tag_count_check = bool(raw.get("tag_count_check", False))
    if not field_validation_enabled and not tag_count_check:
        logging.info("[검증] 파싱 후 검사가 비활성화되어 있습니다.")
        return 0

    output_root = Path(args.output_root)
    if not output_root.exists():
        logging.error("[검증] output_root 경로가 존재하지 않습니다: %s", output_root)
        return 1

    field_states: dict[str, int] = {}
    if field_validation_enabled:
        field_states = {
            str(k): int(v) for k, v in raw.get("fields", {}).items()
        }

    return validate_output_root(
        output_root=output_root,
        field_states=field_states,
        field_validation_enabled=field_validation_enabled,
        tag_count_check=tag_count_check,
    )


if __name__ == "__main__":
    sys.exit(main())
