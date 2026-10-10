# 정성 콘텐츠 저장소와 정책 수집

기초 자료와 검증한 정책 요약은 JSON을 원본으로 관리하고, FastAPI 시작 시 DB에 반영합니다. 자동 수집한 정책 후보는 별도 테이블에 누적합니다. 기존 ECOS·FRED 지표 API와 메모리 캐시는 그대로 사용합니다.

회원 좋아요는 별도 `member_space.indicator_likes` 테이블에 저장합니다. `(user_id, indicator_id)` 기본키로 사용자당 지표 한 표를 보장하며, 서버 시작 시 스키마·테이블·RLS·브라우저 역할 권한 회수를 하나의 트랜잭션에서 적용합니다. Supabase Data API의 Exposed schemas에 `member_space`를 추가하지 않습니다. Google 로그인, 환경변수, 연결 확인과 팀 프리뷰 절차는 [회원 기능 가이드](../docs/members-likes-guide.md)를 참고하세요.

## 구성

공식 RSS / 공개 보도자료 목록 → CLI 또는 관리자 수집 API → SQLite / PostgreSQL → FastAPI → 웹페이지

| 경로 | 기능 |
|---|---|
| GET /knowledge | 출처를 붙여 편집한 용어·거래·개발·투자 기초 자료 |
| GET /policies | 원문을 확인한 정책 요약과 자료 확인일 |
| GET /policies/monitor | 수집 후보, 기관별 성공 시각·오류, 저장소 상태 |
| GET /policies/history | 최근 10년 정책의 시기별 변화·발표일·맥락·공식 원문·확인일 |
| POST /policies/refresh | X-Admin-Token 인증 후 수집. POLICY_ADMIN_TOKEN 미설정이면 비활성화 |

GET 요청은 외부 수집과 DB 쓰기를 실행하지 않습니다.

## 로컬 실행과 실제 수집

저장소 루트에서:

~~~powershell
python -m pip install -r backend/requirements.txt
python -m uvicorn app.main:app --app-dir backend --port 8000
~~~

DATABASE_URL이 없으면 backend/local.db를 생성합니다. backend/.env 또는 서버 환경변수로 설정할 수 있습니다. 앱 시작 시 테이블 생성과 검증 JSON 반영만 수행하며 외부 수집은 실행하지 않습니다.

~~~powershell
python scripts/collect_policies.py
python scripts/collect_policies.py --export backend/data/policy-monitor.snapshot.json
~~~

Render Root Directory가 backend이면:

~~~bash
python -m app.collect_policies
python -m app.collect_policies --export data/policy-monitor.snapshot.json
~~~

실패한 기관이 있으면 CLI 종료 코드가 1입니다. 성공한 다른 기관의 결과와 과거 수집 자료는 유지합니다. JSON 내보내기에는 실제 확인 시각과 당시 결과가 담깁니다. 내보낸 파일은 새 수집 없이는 갱신되지 않습니다.

## Supabase 연결 시 팀원이 할 일

1. Supabase Connect → Session pooler의 PostgreSQL URL을 확인합니다.
2. Render 서버 환경변수 DATABASE_URL에 URL을 저장합니다. 예: postgresql+psycopg://postgres.PROJECT:PASSWORD@HOST.pooler.supabase.com:5432/postgres
3. 비밀번호의 @, /, # 등은 URL 인코딩합니다. URL·DB 비밀번호·관리자 토큰은 HTML·JS·GitHub에 넣지 않습니다.
4. 서비스를 재시작합니다. DB 소유자 권한으로 4개 테이블을 생성하고 backend/data/knowledge.json, policies.json, policy-history.json을 반영합니다. 먼저 수동 생성하려면 database/schema.sql을 Supabase SQL Editor에서 실행할 수 있습니다.
5. /policies, /policies/monitor, /policies/history의 storage.type=postgresql, storage.available=true를 확인합니다. CLI 또는 관리자 API를 한 번 실행해 실제 정책 후보를 저장합니다.

서버는 psycopg 3로 TLS 연결합니다. 브라우저에서 Supabase 익명 REST 테이블 접근을 사용하지 않고 RLS를 켭니다. FastAPI의 DB 소유자 연결로 읽고 씁니다. 별도 제한된 DB 역할을 쓰면 팀원이 테이블 권한과 RLS 정책을 설정해야 합니다.

검증한 JSON은 새 DB에 바로 반영됩니다. 기존 SQLite의 수집 이력은 연결 문자열만 바꾸면 자동으로 이동하지 않습니다. 필요한 이력은 기존 DB를 보관하고 별도 마이그레이션해야 합니다. 새 Supabase에서 수집기를 실행하면 현재 피드부터 축적합니다. Render 임시 디스크의 SQLite는 재배포·재시작 시 사라질 수 있으므로 지속적인 이력에는 Supabase를 사용합니다.

## 테이블과 콘텐츠 관리

| 테이블 | 저장 내용 | 갱신 |
|---|---|---|
| content_snapshots | 기초 자료, 검증 정책, 정책 히스토리 JSON 및 해시 | 시작 시 Git JSON과 동기화 |
| policy_source_states | 시도·성공 시각, 상태, 오류, 마지막 성공의 후보 수 | 기관별 수집 후 |
| policy_documents | URL별 최신 제목·발표일·RSS 발췌·키워드·관측 시각 | URL 중복 없이 최신 내용 |
| policy_document_versions | 수집 내용의 버전 및 해시 | 변경 시 이력 추가 |

관계: policy_documents 한 건에 policy_document_versions 여러 건이 연결됩니다(document_id 외래키). source_id는 코드에 정의한 기관 ID와 policy_source_states.id에 대응하며, 원문 URL은 유일합니다. content_snapshots는 knowledge/policies/policy-history 키별 독립된 검증 콘텐츠입니다.

ORM은 backend/app/db/models.py, 대응 SQL은 database/schema.sql입니다. 앱 시작 시 없는 테이블만 생성합니다. 이후 컬럼·제약을 바꾸면 별도 마이그레이션을 작성해야 합니다.

검증 콘텐츠 원본은 frontend/data/knowledge.json, policies.json, policy-history.json, Render 복사본은 backend/data/입니다. 수정할 때 함께 동기화합니다. DB에서 검증 JSON을 직접 고치면 다음 배포 시 Git 버전으로 덮어쓰므로 Git에서 리뷰하고 수정합니다. 수집 후보는 검증한 정책 요약이나 히스토리에 자동으로 합치지 않습니다.

정책 히스토리는 2016-10-05~2026-10-05의 주요 전환점을 공식 발표에서 선정한 연표입니다. `eras`는 흐름을 설명하는 편집상 구간이고 `events`는 발표일·변화 내용·당시 맥락·시행시점 유의사항·출처를 담습니다. 전체 정책의 완전한 목록이나 현재 적용 규정 목록은 아닙니다. 기존 content_snapshots의 JSON 필드를 사용하므로 새 테이블이나 별도 마이그레이션은 필요하지 않습니다. GET은 DB에서 읽기만 하며 장애 시 검토 파일을 반환하고 storage.available=false로 표시합니다.

~~~powershell
python scripts/check_history_data.py
python scripts/sync_qualitative_data.py
python scripts/sync_qualitative_data.py --check
~~~

## 실제 출처와 범위

| 기관 | 수집 방식 및 URL | 수집 항목 |
|---|---|---|
| 국토교통부 | RSS: https://www.molit.go.kr/dev/board/board_rss.jsp?rss_id=NEWS | 제목, 링크, 발표일, 제공되는 설명 |
| 행정안전부 | RSS: https://www.mois.go.kr/gpms/view/jsp/rss/rss.jsp?ctxCd=1012 | 제목, 링크, 발표일, RSS 본문 발췌 |
| 금융위원회 | HTML: https://www.fsc.go.kr/no010000 | 최신 목록 제목, 발표일, 원문 링크 |

2026-10-05 실제 HTTP 응답과 파싱을 확인했습니다. 금융위원회 RSS가 점검 중이므로 공개 목록을 이용합니다. 같은 날 https://www.fsc.go.kr/robots.txt 의 Allow: /를 확인했습니다. 운영 중 이용조건과 robots 변경을 확인하고 무리한 빈도로 요청하지 않습니다.

- 기관당 피드 또는 첫 목록만 요청합니다. 첨부파일과 과거 목록 전체는 수집하지 않습니다.
- 제목·RSS 본문에서 주택·임대차·세금·대출·정비 키워드를 검색합니다. 누락·오탐이 있을 수 있고 자료 수는 정책 개수나 위험 점수가 아닙니다.
- 원문이 설명·정정·지원 안내일 수도 있어 자동 결과는 모두 **미검토**입니다. 발표·시행예정·공포·실제 시행은 사람이 원문과 법령으로 확인합니다.
- 국토부 RSS 설명이 iframe뿐이거나 금융위 목록에 본문이 없으면 요약을 만들지 않습니다. 본문이 있으면 생성형 요약이 아닌 원문 발췌입니다.
- 제목·발표일·RSS 설명 해시로 수집 내용의 수정을 감지합니다. 상세 페이지·첨부파일 전체를 비교하지 않으므로 원문만 바뀌면 감지하지 못할 수 있습니다.
- URL은 고정 공식 기관 도메인만 허용합니다. 금융위 검색 쿼리는 문서 식별에서 제외합니다. XML 외부 엔터티와 HTML script·iframe은 처리하지 않습니다.
- 수집 실패 시 마지막 성공 시각과 기존 문서를 유지합니다. API는 DB 비밀번호와 내부 오류 문자열을 반환하지 않습니다.
- last_checked_at은 마지막 시도, last_success_at은 마지막 성공입니다. 결과가 0개인 성공과 실패를 구분합니다.

경기도 RSS·정책브리핑·국가법령정보센터 등 추가 출처는 검증 정책 JSON에서 안내합니다. 현재 자동 수집은 위 3개 기관입니다. 정책브리핑 RSS는 2026-07-01 종료되어 연동하지 않습니다.

## 주기적 운영과 확인

정책 수집 워크플로는 `.github/workflows/collect-policies.yml`에 있습니다. 기본 브랜치에서 6시간 간격(UTC 00/06/12/18시 17분) 또는 수동 `workflow_dispatch`로 실행됩니다.

GitHub Repository Secrets에 POLICY_API_BASE_URL(예: https://서비스.onrender.com)과 POLICY_ADMIN_TOKEN을 설정하고, 같은 POLICY_ADMIN_TOKEN을 Render에도 설정합니다. 둘 중 하나라도 없으면 사유를 로그에 남기고 정책 API 호출을 건너뜁니다. HTTP 409는 이미 실행 중으로 처리하며, 기관 일부 실패는 워크플로우 실패로 표시합니다. 웹브라우저에는 토큰이 전달되지 않습니다.

Supabase 연결 후 활성화해야 수집 이력이 계속 보존됩니다. 대안으로 Render Cron Job에서 python -m app.collect_policies를 실행할 수 있습니다. 실행환경의 요금과 예약 시각은 팀에서 정합니다. 독립 Cron의 SQLite는 웹서비스와 공유되지 않습니다.

~~~powershell
python -m pip install -r backend/requirements-dev.txt
python -m pytest tests/backend -q -p no:cacheprovider
~~~

파싱·한국시간·키워드 오탐, 빈 본문, 외부 도메인·XML 엔터티 차단, 재시작 후 중복 방지, 수정 버전, 실패 시 자료 보존, 토큰 보호, GET의 수집 비실행, DB 장애 시 비밀 없는 응답을 확인합니다. 테스트 입력은 테스트 전용이며 배포 자료에 들어가지 않습니다. 실제 Supabase 계정 연결은 팀원이 설정한 뒤 확인해야 합니다.
