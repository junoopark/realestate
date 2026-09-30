# database/

앱 코드(`backend/`)와 **분리해서 관리하는 데이터베이스 설계·스크립트** 폴더입니다.
아직 DB는 구축하지 않았습니다. 처음에는 백엔드가 ECOS·FRED 등 외부 API를 직접 호출하고(메모리 캐시 12시간),
지표 수가 늘거나 API로 받을 수 없는 자료(엑셀 등)가 생기면 DB에 적재합니다.

## 계획

| 구분 | 로컬 | 배포 |
|---|---|---|
| DB | SQLite (`sqlite:///./local.db`, 설치 불필요) | Supabase(PostgreSQL) |
| 연결 방법 | 환경변수 `DATABASE_URL` | 환경변수 `DATABASE_URL` = Supabase **Session pooler** 문자열 |

- Render는 IPv6로 나가지 못하므로 Supabase는 **Session pooler** 연결 문자열을 씁니다.
- 연결 문자열에는 비밀번호가 들어 있으므로 **저장소에 커밋하지 않습니다.** (`.env`는 `.gitignore` 대상)

## CSV 인코딩

`seed/`의 CSV는 **UTF-8 BOM 포함**으로 저장합니다. 엑셀에서 **파일 → 다른 이름으로 저장 → "CSV UTF-8(쉼표로 분리)"** 을 고르면 됩니다. BOM이 없으면 Windows 엑셀에서 한글이 깨집니다.

## 폴더 구성

```
database/
├─ README.md           # 이 문서
├─ schema.sql          # 테이블 정의 (PostgreSQL 기준) — DB 를 붙일 때 만든다
├─ seed.sql            # 초기 데이터 (SQL)          — DB 를 붙일 때 만든다
├─ seed/               # 입력용 CSV
└─ migrations/         # 스키마 변경 이력 (0001_*.sql, 0002_*.sql …)
```

## 화면(타일)과 데이터

대시보드의 6개 타일이 데이터 단위와 대응합니다. 식별자는 프론트엔드의 `data-tile` 값, `js/i18n.js`의 `tile.<식별자>.*` 키와 같습니다. **타일 구성은 임시**이며, 지표가 정해지면 표를 채웁니다.

| 위치 | 식별자 | 한국어 | English | 필요한 데이터 (후보) |
|---|---|---|---|---|
| 좌상 | `prices` | 주택가격 동향 | Housing Prices | (미정) |
| 중상 | `transactions` | 거래 동향 | Transactions | (미정) |
| 우상 | `rent` | 전월세 시장 | Rental Market | (미정) |
| 좌하 | `supply` | 공급·분양 | Supply & Presales | (미정) |
| 중하 | `finance` | 금리·대출 | Rates & Lending | (미정) |
| 우하 | `sentiment` | 시장 심리 | Market Sentiment | (미정) |

## 앱 코드와의 관계

| 역할 | 위치 |
|---|---|
| 테이블 정의 (SQL, 사람이 읽는 기준본) | `database/schema.sql` |
| 테이블 정의 (Python ORM) | `backend/app/db/models.py` |
| DB 연결·세션 | `backend/app/db/session.py` |
| 조회·저장 로직 | `backend/app/crud/` |
| API 입출력 모양 (Pydantic) | `backend/app/schemas.py` |

## 진행 순서 (예정)

1. 6개 타일에 넣을 지표를 확정하고, 지표마다 출처·코드·주기를 표로 정리한다.
2. `schema.sql`에 테이블을 정의한다. (예: `indicator`(지표 정보) · `indicator_point`(날짜별 값))
3. `backend/requirements.txt`에 `sqlalchemy`, `psycopg2-binary`를 추가한다.
4. `db/session.py`, `db/models.py`, `crud/`, 라우터를 채운다.
5. 로컬(SQLite)에서 확인한 뒤 Supabase를 만들어 Render에 `DATABASE_URL`을 설정한다.
