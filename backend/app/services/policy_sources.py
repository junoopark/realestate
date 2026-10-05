"""Official, public sources; no credentials or arbitrary caller supplied URLs."""

SOURCES = [
    {"id": "molit", "name": "국토교통부 보도자료 RSS", "organization": "국토교통부",
     "url": "https://www.molit.go.kr/USR/NEWS/m_71/lst.jsp",
     "feed_url": "https://www.molit.go.kr/dev/board/board_rss.jsp?rss_id=NEWS", "collection_method": "RSS",
     "fields": ["제목", "발표일", "원문 URL", "RSS 설명(제공되는 경우)"]},
    {"id": "mois", "name": "행정안전부 보도자료 RSS", "organization": "행정안전부",
     "url": "https://www.mois.go.kr/frt/bbs/type010/commonSelectBoardList.do?bbsId=BBSMSTR_000000000008",
     "feed_url": "https://www.mois.go.kr/gpms/view/jsp/rss/rss.jsp?ctxCd=1012", "collection_method": "RSS",
     "fields": ["제목", "발표일", "원문 URL", "RSS 본문 발췌"]},
    {"id": "fsc", "name": "금융위원회 보도자료 목록", "organization": "금융위원회",
     "url": "https://www.fsc.go.kr/no010000", "feed_url": "https://www.fsc.go.kr/no010000",
     "collection_method": "HTML 목록 수집", "fields": ["제목", "발표일", "원문 URL"]},
]

COVERAGE_NOTE = "국토교통부·행정안전부 RSS와 금융위원회 보도자료 첫 목록에서 부동산 키워드가 포함된 항목을 수집합니다. 전수 조사나 과거자료 소급 수집이 아니므로 누락될 수 있습니다. 자동 수집 항목은 미검토 자료이며 정책 확정·시행을 뜻하지 않습니다."
