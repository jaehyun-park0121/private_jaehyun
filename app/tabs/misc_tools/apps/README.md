# misc_tools/apps

기타 도구 탭에서 카드 하나로 노출되는 앱 폴더 모음입니다.

## 운영 방식

- 폴더 1개 = 앱 1개
- 실제 사용자용 앱은 `__init__.py`와 대표 `README.md`를 함께 두는 편을 권장합니다.
- `loader.py`는 `apps/` 직계 하위 폴더만 스캔합니다.
- `App` 클래스가 있어야 카드로 노출됩니다.

## 현재 앱 목록

- [parse/README.md](./parse/README.md): 페이지 JSON/PNG를 문서 단위 결과로 변환하는 실제 구현 앱
- [table_viewer/README.md](./table_viewer/README.md): TABLE BBOX, 렌더링 결과, HTML/Markdown 원본을 함께 검수하는 PyQt6 뷰어 앱
- `template/`: 새 misc app 작성용 템플릿 폴더. 사용 방법은 [misc_tools/README.md](../README.md)를 참고합니다.

## 앱 README에 적는 것

- 앱 목적과 현재 상태
- 주요 파일과 폴더 역할
- 실행 방식 또는 향후 연결 방향
- 구현 시 주의사항과 관련 상위 문서

## 관련 문서

- [misc_tools/README.md](../README.md)
