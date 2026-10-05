# taobao_mtop 픽스처 (Z3 자동 경로)

- `x5_referer.txt` — 첫 줄과 `window.location.href = "https://h5api.m.taobao.com:443/h5/mtop.taobao.detail.getdetail/6.0/_____tmd__` 까지는 **실측 원문**(볼트 `srv_snap/apply_out/mtop_probe_1004.txt`, 오너 서버 2026-10-04 04:38 — 앞 100자만 기록됨). 그 뒤(`set_x5referer?rand=&uuid=&_lgt_=` + `x5referer` 이어 붙이기)는 오너가 설명한 모양으로 **재구성**.
- `rgv587_punish.json` — ret 문구는 실측 원문(같은 파일, getdesc 응답). `data.url`(punish)은 재구성.
- `getdetail_success.json`·`getdesc_success.json`·`token_empty.json` — mtop v6.0 응답 모양으로 만든 표본(값은 지어낸 것). 실측 성공 응답을 받으면 교체.
