-- src/db/schema_stage11.sql — F25b: 서버 전역 호출 차례표(api_rate_slots).
--
-- ## 왜 필요한가
--
-- 공급사 한도가 **계정 단위 초당 1회**인데, F25에서 건 직렬 게이트는 **프로세스 전역**이었다.
-- 실측: gunicorn `--workers 2`(scripts/start_render.sh:30 · gunicorn.conf.py:5) ·
-- `gthread` × `threads 4`(gunicorn.conf.py:6-7) = **워커 2 × 스레드 4**.
-- 워커가 둘이면 잠금도 둘이다 — 각자 「나는 하나씩 보낸다」고 믿으면서 **합쳐서 둘**이 나간다.
--
-- ## 차례표이지 잠금이 아니다
--
-- 행 하나에 「다음으로 비는 시각」만 둔다. 호출자는 **원자적 UPDATE 한 번**으로 자기 차례를
-- 예약받고 **연결을 놓은 뒤** 그 시각까지 기다린다.
--
-- 잠금을 쥔 채 공급사를 부르지 않는 이유: 한 장이 최대 30초(내려받기 10 + 호출 20)이고
-- 12장이면 그만큼 **DB 연결과 트랜잭션을 붙잡는다**. 트랜잭션 풀러(6543) 뒤에서 그건
-- idle-in-transaction이고, 이 레포는 이미 그 문제를 아는 코드다(`pg.get_conn`의 rollback 정리).
-- 차례표는 잠금을 **밀리초**만 잡는다.
--
-- 시각은 **서버(now())** 기준이다 — 워커마다 시계가 다를 수 있으므로 클라이언트 시계를 믿지 않는다.
-- PG가 없으면(개발·테스트) 프로세스 전역 게이트로 폴백한다. 그때는 워커가 하나뿐이라 그걸로 족하다.

CREATE TABLE IF NOT EXISTS api_rate_slots (
  key        text PRIMARY KEY,          -- 한도가 걸리는 단위(예: 'tencent:image-translate')
  next_at    timestamptz NOT NULL,      -- 이 시각부터 다음 호출을 보낼 수 있다
  updated_at timestamptz NOT NULL DEFAULT now()
);
