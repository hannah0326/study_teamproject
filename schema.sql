-- 작성: 2026-10-25 23:22 KST
-- 팀 편성 앱이 쓰는 테이블, 열, 제약. 앱 코드와 항상 같게 유지함.
-- 모든 테이블 이름은 tf_ 로 시작함(같은 DB의 다른 테이블과 구분).

-- 학생과 관리자. 관리자는 주 역할이 없음(is_admin = true).
create table if not exists tf_students (
    id            bigint generated always as identity primary key,
    student_no    text    not null unique,
    name          text    not null,
    main_role     text    check (main_role in
                      ('기획자', '웹 프로그래머', '프론트엔드 디자이너', '테스터', '보고서 작성자', '발표자')),
    password_hash text    not null,
    is_admin      boolean not null default false,
    check (is_admin or main_role is not null)
);

-- 보조 역할. 학생 1명에 0~2행.
create table if not exists tf_student_sub_roles (
    student_id bigint not null references tf_students (id) on delete cascade,
    role       text   not null check (role in
                   ('기획자', '웹 프로그래머', '프론트엔드 디자이너', '테스터', '보고서 작성자', '발표자')),
    unique (student_id, role)
);

create table if not exists tf_teams (
    id   bigint generated always as identity primary key,
    name text not null unique
);

-- 팀원. (team_id, slot_no) 와 student_id 의 유일성이 "마지막 자리에 두 명이 동시에 들어감"과
-- "한 학생은 한 팀"을 DB에서 지켜 준다. slot_no 는 1~4 만 허용(다섯 번째 자리 차단).
create table if not exists tf_members (
    team_id    bigint  not null references tf_teams (id) on delete cascade,
    slot_no    integer not null check (slot_no between 1 and 4),
    student_id bigint  not null unique references tf_students (id) on delete cascade,
    primary key (team_id, slot_no)
);

create table if not exists tf_applications (
    id         bigint generated always as identity primary key,
    team_id    bigint not null references tf_teams (id) on delete cascade,
    student_id bigint not null references tf_students (id) on delete cascade,
    status     text   not null check (status in ('대기', '승인', '거절')),
    reason     text,
    created_at timestamptz not null default now(),
    decided_at timestamptz
);

-- 한 학생은 결과를 기다리는 지원을 동시에 둘 가질 수 없음.
create unique index if not exists tf_applications_one_pending
    on tf_applications (student_id) where status = '대기';

create table if not exists tf_votes (
    application_id bigint not null references tf_applications (id) on delete cascade,
    voter_id       bigint not null references tf_students (id) on delete cascade,
    vote           text   not null check (vote in ('찬성', '거부')),
    primary key (application_id, voter_id)
);

-- 마감 여부, 확정 여부, 배정안 등
create table if not exists tf_settings (
    key   text primary key,
    value text not null
);

-- AI 호출 기록(시작 시각, 차수, 모델, 결과, 실패 이유, 소요 시간). 키는 기록하지 않음.
-- created_at 은 기록을 저장한 때(한 번의 배정이 끝난 뒤 함께 저장), started_at 은 그 모델을 부르기 시작한 때.
create table if not exists tf_ai_logs (
    id         bigint generated always as identity primary key,
    created_at timestamptz not null default now(),
    started_at timestamptz,
    step       integer,
    model      text,
    result     text,
    detail     text,
    seconds    numeric
);
-- 앞서 만든 DB에도 새 열을 더함
alter table tf_ai_logs add column if not exists started_at timestamptz;
alter table tf_ai_logs add column if not exists detail text;
