# app

앱 실행 코드 전체를 모아두는 폴더입니다.

## 구성

- `main_window.py`: 메인 창, 탭 등록, 공통 상단/상태바 연결
- `common/`: 여러 탭에서 함께 쓰는 공통 코드
- `tabs/`: 메인 탭별 기능 코드
- `__init__.py`: 패키지 진입점

## 폴더 구분 기준

- 탭 전용 로직은 각 탭 폴더 안에 둡니다.
- 둘 이상의 탭이 함께 쓰는 코드만 `common/`으로 올립니다.
- 문서는 상위 README에서 하위 README로 내려가며 읽을 수 있게 유지합니다.

## 함께 볼 문서

- [app/common/README.md](./common/README.md)
- [app/tabs/README.md](./tabs/README.md)