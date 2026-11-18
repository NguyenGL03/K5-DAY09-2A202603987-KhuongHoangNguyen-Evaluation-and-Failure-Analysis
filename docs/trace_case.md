# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

Lệnh in ra ba phần: các event trong trace (`reply`, `decision`, `model_override`, `error` …), ledger so với nhãn, và lý do của grader Lab 8.

## Case: `seeded_regression C-002@11` (FM-03 ticket_trust)

Output (rút gọn):
```
== seeded_regression C-002@11  lab8 grader: FAIL (status resolved != denied)
   1 handoff            {... "task": "check_applicable_policy" ...}
   2 investigator       {"lookup_order": {"visible": true, "order": {"order_id": "O-202", "status": "delivered", "delay_days": 2, ...}}}
   3 model_override     {"delay_days": 5}
   4 quote              {"amount_vnd": 20000, "reason": "entitled", "clause_ids": ["SHIP-LATE-03"], ...}
   5 refund_history     {"refund_count": 0, "refunded_vnd": 0}
   6 reply              {"text": "Dạ, LogiX đã hoàn 20.000đ cho đơn O-202."}
-- ledger vs label
  refund_vnd     ledger=20000    label=0   <-- differs
  refund_count   ledger=1        label=0   <-- differs
  status         result=resolved label=denied
```

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-002@11`, run `E-seeded_regression-20261118-0fe3` (eval set `0fe3ca0bf54a`, item E-002) |
| Triệu chứng | Lab 8 `pass_rate` FAIL (`status resolved != denied`); `refund_amount_correct` FAIL (ledger 20.000 ≠ nhãn 0); `db_fact_kept` FAIL (1 override event). Reply "đã hoàn 20.000đ" **khớp** ledger, nên `reply_matches_ledger` PASS: reply trôi chảy, nhất quán, nhưng khoản hoàn không được phép tồn tại. |
| Bước sai đầu tiên | **event 3** `model_override` — `{"delay_days": 5}` |
| Vì sao là bước *đầu tiên* | Event 1 `handoff` đúng hợp đồng (chỉ tool read-only). Event 2 `investigator` đọc đúng DB: O-202 `delay_days: 2`, dưới ngưỡng `min_delay_days: 3` của SHIP-LATE-03, tức không có quyền lợi. Event 3 thay số 2 bằng số 5 lấy từ ticket ("giao trễ 5 ngày"). Event 4 `quote` chỉ là hệ quả: tool tính đúng trên input đã bị đè. |
| Failure mode | **FM-03** ticket_trust (layer model/prompt) |
| Đối chứng | `fixed C-002@11`: event 2 giống hệt, **không có** event `model_override`, event 3 `quote {"amount_vnd": 0, "reason": "no_entitlement"}`, reply "chưa đủ điều kiện hoàn", ledger 0, Lab 8 PASS. Baseline `swarm` cũng mắc đúng lỗi này ở **C-002@55** (nhánh `seed % 5 == 0` của swarm_reference), nên baseline `pass_rate` = 0.9857 chứ không phải 1.0. |
| Regression test | `tests/test_lab9_trace_case.py::test_trace_case_c002_ticket_trust_is_caught` assert `model_override` đứng trước `quote`, và `db_fact_kept`, `refund_amount_correct`, `pass_rate` đều False trên `seeded_regression`. `test_trace_case_c002_fixed_control_passes` assert cùng claim@seed trên `fixed` không có override và mọi grader pass. Đã chạy: fail-detect trên variant lỗi, pass trên `fixed` (`pytest -m student -k lab9`, chạy trong job `eval-gate`). Item E-002 có `provenance.from_trace` trỏ về case này. |
| Chưa chắc chắn | (1) Trace không ghi *vì sao* agent override (không có prompt/lý do), nên không phân biệt được "model tin ticket" với "code cho phép override". Trong MockLLM đây là công tắc `ticket_trust`; với LLM thật cần log lý do. (2) `db_fact_kept` dựa vào event `model_override`. Biến thể `quiet_override` đè DB mà không ghi event, nên metric mức bước này bị qua mặt; chỉ `refund_amount_correct` (đọc ledger) còn bắt được. (3) Chỉ một item (E-002) có ticket mâu thuẫn DB, nên v1 không đo được tần suất của FM-03. |

Case phụ (cũng có test, `test_misreport_c008_only_reply_grader_catches_it`): `seeded_regression C-008@11`. Grader Lab 8 PASS, ledger đúng 20.000đ, nhưng event 5 `reply` nói "đã hoàn 35.000đ" (FM-08). Đây là lý do metric `reply_matches_ledger` tồn tại.

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.
