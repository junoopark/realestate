"""DB 조회·저장 로직 (예정 — 아직 사용하지 않는다).

라우터(app/routers/)는 요청을 받고 응답만 다루고,
실제 DB 읽기·쓰기는 이 패키지의 함수가 맡는다. 화면(타일)별로 파일을 나눈다.
예) crud/indicators.py: list_points(db, key, start, end), upsert_points(db, key, rows)
"""
