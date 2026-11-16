-- 진성현장 통합 앱 공통 데이터 모델 (설계안 3장, 5-1장)
-- 개발: SQLite / 운영: PostgreSQL. 두 곳에서 같은 의미로 동작하는 문법만 쓴다.
-- 금액은 원 단위 정수, 수량은 소수 문자열(TEXT)로 저장해 반올림 오차를 막는다.
-- 모든 행: id(UUID 문자열), version(동시 수정 감지), created_at·updated_at(한국 시각 ISO).

PRAGMA foreign_keys = ON;

-- 현장. 유형: 정식 / 긴급수의 / 보수기타 / 본사공통
CREATE TABLE IF NOT EXISTS site (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    site_type       TEXT NOT NULL CHECK (site_type IN ('정식','긴급수의','보수기타','본사공통')),
    client          TEXT,
    contract_amount INTEGER,
    start_date      TEXT,
    end_date        TEXT,
    gps_lat         REAL,
    gps_lon         REAL,
    gps_radius_m    REAL,
    sta_interval    TEXT NOT NULL DEFAULT '20',  -- 측점 간격(m)
    sta_label_shift INTEGER NOT NULL DEFAULT 0,  -- 도면 표기 치환 (예: 도면 'No 6' = 실제 No.0 → -6)
    -- 공사 건의 흐름: 접수 → (보류) → 진행 → 완공. 취소는 '취소'로 남기거나(비용이 있을 때) 파기한다.
    status          TEXT NOT NULL DEFAULT '진행' CHECK (status IN ('접수','보류','진행','완공','취소')),
    job_type        TEXT,                        -- 접수 구분: 긴급 / 견적 / 수의 / 입찰 / 민원 / 기타
    received_date   TEXT,                        -- 접수일
    planned_start   TEXT,                        -- 시작 예정일 (발주·체크 알림의 기준)
    instructions    TEXT,                        -- 지시사항
    status_reason   TEXT,                        -- 보류·취소 사유
    version         INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

-- 받는 곳(개인·업체). 결제 집계의 단위.
CREATE TABLE IF NOT EXISTS payee (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    payee_type  TEXT NOT NULL CHECK (payee_type IN ('개인','업체','직영')),
    bank        TEXT,                      -- 월말 이체용
    account_no  TEXT,
    holder      TEXT,                      -- 예금주 (비우면 이름)
    pay_rule    TEXT,                      -- 일용(소득세 뗌) / 부가세별도 / 그대로. 비우면 개인=일용
    version     INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

-- 기준 단가. 값의 주인은 '기준 정보' 하나.
CREATE TABLE IF NOT EXISTS rate (
    id          TEXT PRIMARY KEY,
    kind        TEXT NOT NULL CHECK (kind IN ('인력','장비','자재','외주')),
    item        TEXT NOT NULL,           -- 보통인부, 6W, 덤프 25톤, 레미콘
    spec        TEXT NOT NULL DEFAULT '',-- 25-21-150 등
    unit        TEXT NOT NULL,           -- 인, 일, 대, ㎥
    unit_price  INTEGER NOT NULL,
    payee_id    TEXT REFERENCES payee(id),  -- 업체별 단가가 있으면 지정
    valid_from  TEXT NOT NULL,           -- 이 날짜(작업일)부터 적용
    is_draft    INTEGER NOT NULL DEFAULT 0, -- 1 = 온새 초안, 영주형 확인 전
    version     INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

-- 공종 (20개 템플릿 중 하나 + 현장별 설계 수량)
CREATE TABLE IF NOT EXISTS work_type (
    id            TEXT PRIMARY KEY,
    site_id       TEXT NOT NULL REFERENCES site(id),
    template_code TEXT NOT NULL,
    name          TEXT NOT NULL,
    design_length TEXT,
    design_params TEXT,              -- 설계(도면) 치수 JSON
    exec_params   TEXT,              -- 실행(실제 시공) 치수 JSON. 없으면 설계와 같음
    exec_budget   INTEGER,           -- 실행 예산(원). 원가 경보의 기준
    version       INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

-- 측점
CREATE TABLE IF NOT EXISTS station (
    id          TEXT PRIMARY KEY,
    site_id     TEXT NOT NULL REFERENCES site(id),
    sta_m       TEXT NOT NULL,     -- 누가거리(m), 예: No.3+00 = '60'
    label       TEXT NOT NULL,
    plan_elev   TEXT,
    ground_elev TEXT,              -- 도면 현황 지반고
    version     INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    UNIQUE (site_id, sta_m)
);

-- 작업일지. 현장 하나 + 작업일 하나 = 일지 하나.
-- work_date는 사용자가 정한 날짜만(YYYY-MM-DD). 기록·전송 시각에서 계산하지 않는다.
CREATE TABLE IF NOT EXISTS work_log (
    id          TEXT PRIMARY KEY,
    site_id     TEXT NOT NULL REFERENCES site(id),
    work_date   TEXT NOT NULL CHECK (length(work_date) = 10),
    weather     TEXT,
    content     TEXT,
    note        TEXT,
    no_work     INTEGER NOT NULL DEFAULT 0,   -- 비 등으로 작업 없음
    tbm         INTEGER NOT NULL DEFAULT 0,   -- TBM 실시
    version     INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL,                -- 기록 시각
    updated_at  TEXT NOT NULL,
    UNIQUE (site_id, work_date)
);

-- 투입 기록 한 줄. 인력·장비·자재·외주를 줄로 따로 저장한다.
-- share_group: 하루에 두 현장을 오간 장비·인력을 나눈 줄들을 묶는 번호.
CREATE TABLE IF NOT EXISTS input_line (
    id           TEXT PRIMARY KEY,
    log_id       TEXT NOT NULL REFERENCES work_log(id),
    kind         TEXT NOT NULL CHECK (kind IN ('인력','장비','자재','외주')),
    item         TEXT NOT NULL,
    spec         TEXT NOT NULL DEFAULT '',
    qty          TEXT NOT NULL,
    unit         TEXT NOT NULL,
    unit_price   INTEGER NOT NULL,
    amount       INTEGER NOT NULL,
    payee_id     TEXT NOT NULL REFERENCES payee(id),
    work_type_id TEXT REFERENCES work_type(id),
    sta_from     TEXT,
    sta_to       TEXT,
    share_group  TEXT,
    note         TEXT,              -- 한 줄 메모 (이름, 작업 위치 등)
    version      INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

-- 시공 실적 (공종·측점 구간별 오늘 한 양)
CREATE TABLE IF NOT EXISTS progress (
    id           TEXT PRIMARY KEY,
    log_id       TEXT NOT NULL REFERENCES work_log(id),
    work_type_id TEXT NOT NULL REFERENCES work_type(id),
    sta_from     TEXT,
    sta_to       TEXT,
    qty          TEXT NOT NULL,
    unit         TEXT NOT NULL,
    version      INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

-- 내역 배정 자재 (레미콘 규격별, 철근 지름별 …)
-- supply: 도급자관급(사용량 추적) / 관급자관급(설치 확인만) / 사급
CREATE TABLE IF NOT EXISTS allocation (
    id          TEXT PRIMARY KEY,
    site_id     TEXT NOT NULL REFERENCES site(id),
    item        TEXT NOT NULL,
    spec        TEXT NOT NULL DEFAULT '',
    unit        TEXT NOT NULL,
    design_qty  TEXT NOT NULL,     -- 설계(내역) 수량, 할증 제외
    alloc_qty   TEXT NOT NULL,     -- 배정 수량
    supply      TEXT NOT NULL CHECK (supply IN ('도급자관급','관급자관급','사급')),
    pool        TEXT,              -- 규격 치환 묶음. 같은 묶음은 배정량을 합쳐서 본다(발주처 승인 전에는 참고값)
    version     INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    UNIQUE (site_id, item, spec)
);

-- 거래명세서 (값의 주인은 명세서 수신. 일지 값을 덮어쓰지 않는다)
CREATE TABLE IF NOT EXISTS invoice (
    id          TEXT PRIMARY KEY,
    payee_id    TEXT NOT NULL REFERENCES payee(id),
    work_date   TEXT NOT NULL,
    kind        TEXT NOT NULL,
    item        TEXT NOT NULL,
    spec        TEXT NOT NULL DEFAULT '',
    qty         TEXT NOT NULL,
    amount      INTEGER NOT NULL,
    photo_path  TEXT,
    status      TEXT NOT NULL DEFAULT '미대조' CHECK (status IN ('미대조','일치','차이','일지에없음','명세서오류')),
    version     INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

-- 월 마감. 월말 보고를 보낸 달은 잠긴다.
CREATE TABLE IF NOT EXISTS month_lock (
    month       TEXT PRIMARY KEY,   -- YYYY-MM
    locked_at   TEXT NOT NULL
);

-- 수정 이력 (마감 후 수정, 모든 삭제)
CREATE TABLE IF NOT EXISTS change_history (
    id          TEXT PRIMARY KEY,
    table_name  TEXT NOT NULL,
    row_id      TEXT NOT NULL,
    action      TEXT NOT NULL,
    before_json TEXT,
    after_json  TEXT,
    reason      TEXT,
    device      TEXT,
    changed_at  TEXT NOT NULL
);

-- 충돌 검토. 같은 기록을 두 기기가 동시에 고치면 두 값을 나란히 남긴다.
CREATE TABLE IF NOT EXISTS conflict (
    id           TEXT PRIMARY KEY,
    table_name   TEXT NOT NULL,
    row_id       TEXT NOT NULL,
    base_version INTEGER NOT NULL,
    current_json TEXT NOT NULL,
    incoming_json TEXT NOT NULL,
    device       TEXT,
    resolved     INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL
);

-- 보고 이력. 전송 시각은 여기에만 저장한다.
CREATE TABLE IF NOT EXISTS report_log (
    id          TEXT PRIMARY KEY,
    report_type TEXT NOT NULL,
    period      TEXT NOT NULL,
    file_name   TEXT NOT NULL,
    sent_to     TEXT,
    sent_at     TEXT,
    result      TEXT,
    version     INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_log_date ON work_log(work_date);
CREATE INDEX IF NOT EXISTS ix_line_log ON input_line(log_id);
CREATE INDEX IF NOT EXISTS ix_line_payee ON input_line(payee_id);

-- 사진. 원본은 건드리지 않고 경로만 저장한다. 측점이 주소다.
CREATE TABLE IF NOT EXISTS photo (
    id           TEXT PRIMARY KEY,
    site_id      TEXT NOT NULL REFERENCES site(id),
    work_date    TEXT NOT NULL,            -- 촬영 시각에서 '추천'하되 사용자가 확정한 작업일
    taken_at     TEXT,                     -- EXIF 촬영 시각
    path         TEXT NOT NULL,
    work_type_id TEXT REFERENCES work_type(id),
    stage        TEXT CHECK (stage IN ('전','중','후') OR stage IS NULL),
    sta_from     TEXT,
    sta_to       TEXT,
    gps_lat      REAL,
    gps_lon      REAL,
    caption      TEXT,
    version      INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

-- 야장: 측량 회차 + 읽은 값. 계산값(기계고·지반고)은 저장하지 않고 항상 다시 계산한다.
CREATE TABLE IF NOT EXISTS level_run (
    id          TEXT PRIMARY KEY,
    site_id     TEXT NOT NULL REFERENCES site(id),
    work_date   TEXT NOT NULL,
    bm_name     TEXT NOT NULL,
    bm_elev     TEXT NOT NULL,
    bm_assumed  INTEGER NOT NULL DEFAULT 0,   -- 1 = 임시 BM(가정 표고)
    version     INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS level_reading (
    id          TEXT PRIMARY KEY,
    run_id      TEXT NOT NULL REFERENCES level_run(id),
    seq         INTEGER NOT NULL,
    kind        TEXT NOT NULL CHECK (kind IN ('BS','FS','TP','CLOSE')),
    sta_m       TEXT,                      -- FS: 측점 누가거리
    offset_m    TEXT NOT NULL DEFAULT '0', -- 중심에서 좌(-)/우(+) 거리
    value       TEXT NOT NULL,             -- 읽은 값. TP는 FS 값
    value2      TEXT,                      -- TP: 옮긴 뒤의 새 BS
    version     INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

-- 지급 기록. '지급 완료'를 누르면 다음 달 보고서에는 미지급 잔액만 이월된다.
CREATE TABLE IF NOT EXISTS payment (
    id          TEXT PRIMARY KEY,
    payee_id    TEXT NOT NULL REFERENCES payee(id),
    month       TEXT NOT NULL,             -- 어느 달 청구분에 대한 지급인지
    amount      INTEGER NOT NULL,          -- 실제로 보낸 돈
    deduct      INTEGER NOT NULL DEFAULT 0, -- 뗀 세금(소득세+지방소득세)
    vat         INTEGER NOT NULL DEFAULT 0, -- 더한 부가세
    paid_date   TEXT NOT NULL,
    version     INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

-- 시장 단가 참고값 (월요일 업계 브리핑). 기준 단가를 자동으로 바꾸지 않고 '갱신 필요'만 알린다.
CREATE TABLE IF NOT EXISTS market_price (
    id          TEXT PRIMARY KEY,
    kind        TEXT NOT NULL,
    item        TEXT NOT NULL,
    spec        TEXT NOT NULL DEFAULT '',
    unit_price  INTEGER NOT NULL,
    as_of       TEXT NOT NULL,
    source      TEXT,
    version     INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

-- 온새 승인 기록 (설계안 9-1). 검산을 통과한 값만 승인하고, 근거를 남기며, 되돌릴 수 있다.
CREATE TABLE IF NOT EXISTS approval (
    id          TEXT PRIMARY KEY,
    site_id     TEXT REFERENCES site(id),
    subject     TEXT NOT NULL,
    value_json  TEXT NOT NULL,
    checks_json TEXT NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('온새 승인','확인 필요','별도 검토','되돌림')),
    version     INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

-- 보낼 함 (메일). 실패하면 남아 있다가 연결되면 다시 보낸다.
CREATE TABLE IF NOT EXISTS mail_outbox (
    id          TEXT PRIMARY KEY,
    subject     TEXT NOT NULL,
    body        TEXT NOT NULL,
    recipients  TEXT NOT NULL,
    attachments TEXT NOT NULL DEFAULT '[]',
    html        TEXT,                       -- 보기 좋은 보고 본문 (없으면 글자 본문만)
    status      TEXT NOT NULL DEFAULT '대기' CHECK (status IN ('대기','전송됨','실패')),
    tries       INTEGER NOT NULL DEFAULT 0,
    last_error  TEXT,
    report_id   TEXT,
    created_at  TEXT NOT NULL,
    sent_at     TEXT
);

-- 변경 기록 (동기화의 단위). 모든 추가·수정·삭제가 순서대로 쌓인다.
CREATE TABLE IF NOT EXISTS change_log (
    seq          INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name   TEXT NOT NULL,
    row_id       TEXT NOT NULL,
    op           TEXT NOT NULL CHECK (op IN ('추가','수정','삭제','마감')),
    base_version INTEGER,
    data_json    TEXT,
    reason       TEXT,
    device       TEXT NOT NULL,
    at           TEXT NOT NULL
);
-- 두 기기가 같은 현장·같은 날 일지를 따로 만든 경우, 상대 번호를 내 번호에 잇는다.
CREATE TABLE IF NOT EXISTS id_alias (
    alias_id TEXT PRIMARY KEY,
    real_id  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sync_cursor (
    peer     TEXT NOT NULL,
    dir      TEXT NOT NULL,       -- 'out' 보낸 곳까지 / 'in' 받은 곳까지
    seq      INTEGER NOT NULL,
    PRIMARY KEY (peer, dir)
);

-- 공사 건의 연락처 (발주처 담당, 감독, 마을 이장, 민원인 …)
CREATE TABLE IF NOT EXISTS contact (
    id          TEXT PRIMARY KEY,
    site_id     TEXT NOT NULL REFERENCES site(id),
    name        TEXT NOT NULL,
    role        TEXT,
    phone       TEXT,
    note        TEXT,
    version     INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

-- 첨부 자료 (도면·내역·사진·문서). 원본 파일은 건드리지 않고 경로만 둔다.
CREATE TABLE IF NOT EXISTS attachment (
    id          TEXT PRIMARY KEY,
    site_id     TEXT NOT NULL REFERENCES site(id),
    kind        TEXT NOT NULL CHECK (kind IN ('도면','내역','사진','문서','기타')),
    path        TEXT NOT NULL,
    note        TEXT,
    review      TEXT NOT NULL DEFAULT '검토 대기' CHECK (review IN ('검토 대기','온새 승인','확인 필요','해당 없음')),
    review_note TEXT,
    version     INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

-- 할 일·체크 (필수 확인사항, 인력·장비·자재 발주, 서류, 민원). 기한이 오면 홈 화면이 알린다.
CREATE TABLE IF NOT EXISTS site_task (
    id           TEXT PRIMARY KEY,
    site_id      TEXT NOT NULL REFERENCES site(id),
    kind         TEXT NOT NULL CHECK (kind IN ('확인','인력','장비','자재','서류','측량','민원','기타')),
    title        TEXT NOT NULL,
    due_date     TEXT,
    qty          TEXT,
    unit         TEXT,
    work_type_id TEXT REFERENCES work_type(id),
    source       TEXT NOT NULL DEFAULT '직접' CHECK (source IN ('직접','온새 제안')),
    done         INTEGER NOT NULL DEFAULT 0,
    done_date    TEXT,
    note         TEXT,
    version      INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_task_due ON site_task(done, due_date);

-- 명부: 작업자·장비 미리 등록 (받는 곳 + 직종·기종 + 단위·단가). 일지에 처음 적으면 자동으로 들어온다.
CREATE TABLE IF NOT EXISTS roster (
    id          TEXT PRIMARY KEY,
    payee_id    TEXT NOT NULL REFERENCES payee(id),
    kind        TEXT NOT NULL CHECK (kind IN ('인력','장비','자재','외주')),
    item        TEXT NOT NULL,
    spec        TEXT NOT NULL DEFAULT '',
    unit        TEXT NOT NULL,
    unit_price  INTEGER NOT NULL,
    phone       TEXT,
    memo        TEXT,             -- 계좌, 차량번호 등
    active      INTEGER NOT NULL DEFAULT 1,
    version     INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

-- 결제 요청 (현장소장 → 사장님). 결제는 사장님이 한다. 앱은 올린 날·금액만 남긴다.
CREATE TABLE IF NOT EXISTS pay_request (
    id           TEXT PRIMARY KEY,
    month        TEXT NOT NULL,
    amount       INTEGER NOT NULL,
    payee_count  INTEGER NOT NULL,
    requested_at TEXT NOT NULL,
    status       TEXT,                     -- 보낼 요청 → 전송됨 / 보낼 함 대기 / 실패 (집 PC가 적음)
    result       TEXT,                     -- 보낸 곳·파일 또는 실패 사유
    sent_at      TEXT,
    version      INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
