from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..document_parser import DocumentParser


LOGGER = logging.getLogger(__name__)


def run_all_documents(parser: "DocumentParser") -> None:
    document_dirs = parser.list_document_directories()
    if not document_dirs:
        LOGGER.warning("[DOC] 처리할 문서 폴더가 없습니다.")
        return

    execution = parser.config.execution
    if not execution.parallel_enabled or execution.max_workers <= 1 or len(document_dirs) <= 1:
        LOGGER.info("[DOC] 문서 순차 처리로 진행합니다: documents=%s", len(document_dirs))
        for document_dir in document_dirs:
            parser.parse_document(document_dir)
        return

    # 병렬화는 문서 단위로만 적용해 페이지 내부 로직과 충돌하지 않게 유지한다.
    parser.prepare_for_parallel()
    max_workers = min(execution.max_workers, len(document_dirs))
    LOGGER.info("[DOC] 문서 병렬 처리로 진행합니다: workers=%s, documents=%s", max_workers, len(document_dirs))

    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="document-parser") as executor:
        futures = {
            executor.submit(parser.parse_document, document_dir): document_dir
            for document_dir in document_dirs
        }
        for future in as_completed(futures):
            document_dir = futures[future]
            try:
                future.result()
            except Exception as exc:
                LOGGER.error("[DOC] 문서 '%s' 처리 중 치명적인 오류가 발생했습니다: %s", document_dir.name, exc)
                raise
