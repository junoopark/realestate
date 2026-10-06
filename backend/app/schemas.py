"""API 입출력의 모양 (Pydantic). 저장 방식은 db/models.py 가 맡는다.

정량 지표 API(/indicators)는 frontend/data/indicators/*.json 과 같은 모양의 dict 를 그대로 돌려주므로
(routers/indicators.py 맨 위 설명 참고) 별도 Pydantic 모델을 두지 않는다.
"""
