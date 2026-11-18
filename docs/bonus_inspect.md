# Bonus: port 3 grader sang Inspect AI và so khớp với pydantic-evals

```bash
cd src
pip install -r requirements-bonus.txt        # inspect-ai==0.3.291, chỉ cho bonus, CI không cài
python -m bonus.inspect_port                 # ghi reports/bonus_inspect_compare.json, exit 0 = khớp hết
```

## Cách port
| pydantic-evals (`lab9/eval.py`, `lab9/graders.py`) | Inspect AI (`src/bonus/inspect_port.py`) |
|---|---|
| `Case` = item@seed, `expected_output` = nhãn | `Sample(id="E-001@11")`, `target` = nhãn (JSON). Nhãn vẫn đọc từ `labels_v1.json`, không nằm trong item |
| task `run_one` chạy shape trên SQLite tạm | `@solver run_shape`: gọi cùng host Lab 8 (`make_task`), cất Trial vào `state.store` |
| `Evaluator` trả `EvaluationReason` | `@scorer` trả `Score` (1/0 + `explanation`) |
| `aggregate`: safety = đếm, capability = trung bình | metric `total()` tự viết cho `approval_bypass`; `mean()` cho hai metric còn lại |
| không cần model | `model="mockllm/model"` (không bao giờ được gọi; MockLLM của Lab 8 nằm trong shape) |

Ba scorer được **viết lại** trong Inspect, không import `lab9.graders`, nên phép so sánh kiểm được cả hai bản cài đặt:
`approval_bypass` (safety), `refund_amount_correct` (outcome, đọc ledger), `reply_matches_ledger` (FM-08, số tiền trong reply so với ledger).

## Kết quả (eval set v1 `0fe3ca0bf54a`, 14 item × 5 seed = 70 sample mỗi shape)
| Shape | Report pydantic-evals | approval_bypass | refund_amount_correct | reply_matches_ledger | Khớp từng sample |
|---|---|---|---|---|---|
| swarm | `E-swarm-20261118-0fe3` | 0 = 0 | 0.9857 = 0.9857 | 1.0 = 1.0 | 70/70 |
| fixed | `E-fixed-20261118-0fe3` | 0 = 0 | 1.0 = 1.0 | 1.0 = 1.0 | 70/70 |
| seeded_regression | `E-seeded_regression-20261118-0fe3` | 0 = 0 | 0.8571 = 0.8571 | 0.7857 = 0.7857 | 70/70 |
| bonus_all_fire | `E-bonus_all_fire-20261118-0fe3` (chạy trong tiến trình) | **20 = 20** | 0.7143 = 0.7143 | 0.8571 = 0.8571 | 70/70 |

`bonus_all_fire` = `fixed` + `sibling_refund` + `misreport` + `round_down`, chỉ đăng ký trong code bonus (không sửa `lab9/variants.py`). Shape này có mặt vì trên 3 shape công khai `approval_bypass` luôn = 0. Khớp 100% ở đó chỉ chứng minh hai bên cùng nói "không có lỗi". Ở `bonus_all_fire`, cả ba scorer đều fire (20 trial bypass), và hai harness vẫn đồng ý trên **từng** (item, seed), không chỉ trên trung bình.

## Nhận xét
- **Khớp 100% là kỳ vọng đúng**, vì cả hai grader đều là code tất định chấm cùng một Trial. Nếu lệch thì đó là bug port (ví dụ regex số tiền khác nhau), không phải nhiễu.
- Inspect cho thêm: log `.eval` có transcript từng sample (`explanation` của mỗi score), xem được bằng `inspect view`; dễ đổi sang model thật bằng `--model`. pydantic-evals nhẹ hơn và đã nằm trong CI.
- Inspect nạp `log.samples` lười từ file log, nên phải đọc điểm trước khi thư mục log tạm bị xoá.
- Giới hạn: chỉ port 3/7 grader; chỉ chạy eval set v1; không đưa vào CI (thêm dependency nặng cho một kiểm tra chéo).
