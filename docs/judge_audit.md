# Judge audit

Chạy: `python -m lab9.judge --csv <file> --audit 5` (backend replay, n = 100 mỗi tiêu chí, FAIL là lớp dương).

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | **Đạt** — tp 24, fp 4, fn 6, tn 66 | **dùng** (chỉ cho giọng điệu, không cho tiền) |
| helpful | 100 | 0.375 | 1.000 | 0.300 | **Không đạt** (κ và R dưới sàn) — tp 9, fp 0, fn 21, tn 70 | **loại** |

Tỉ lệ fail sau hiệu chỉnh Rogan-Gladen:
- tone_ok: quan sát 0.28 → hiệu chỉnh **0.30** (sens 0.8, spec 66/70 = 0.943).
- helpful: quan sát 0.09 → hiệu chỉnh 0.30. Hiệu chỉnh này khuếch đại ×3.3 vì sensitivity chỉ 0.3, nên con số rất nhạy với sai số ước lượng; không dùng nó để ra quyết định.

## Audit thủ công (10 bất đồng tone + 3 helpful)
| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú / sửa rubric |
|---|---|---|---|---|---|
| 1 | H-008 "Em đã hoàn tiền cho anh rồi nha…" | PASS | FAIL | Người | Xưng "em" + "nha" quá suồng sã. Rubric thêm: *xưng hô chuẩn "LogiX – anh/chị"; "em…nha", "bạn ơi" = FAIL*, kèm 2 ví dụ âm. |
| 2 | H-017 "Dạ, bạn ơi LogiX đã hoàn 25.000đ…" | PASS | FAIL | Người | Cùng lỗi xưng hô; judge nhầm "thân thiện" với "đúng mực". Dùng chung dòng rubric ở #1. |
| 3 | H-029 "Dạ, vui lòng chờ… không cần nhắn thêm." | PASS | FAIL | Người | Judge bám từ khoá lịch sự "Dạ, vui lòng". Rubric thêm: *câu ra lệnh/cấm khách ("không cần nhắn thêm") = FAIL dù có kính ngữ*. |
| 4 | H-042 "Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ." | FAIL | PASS | Người | Judge phạt vì thiếu xin lỗi. Rubric thêm: *không bắt buộc xin lỗi; ngắn mà đủ ý và lễ phép = PASS*. |
| 5 | H-051 "Dạ, LogiX đã refund 90.000đ…" | FAIL | PASS | Người | CS LogiX cho phép từ "refund". Rubric thêm danh sách từ tiếng Anh được phép (refund, ship, voucher). |
| 6 | H-063 "…đã hoàn 20.000đ và sẽ hoàn thêm…" | PASS | FAIL | Người | Hứa ngoài kết quả hệ thống là lỗi **nội dung**, không phải giọng. Hành động: chuyển sang code (mở rộng `ReplyMatchesLedger` bắt "hoàn thêm"/hứa hẹn), ghi rõ trong rubric tone là judge không chấm nội dung. |
| 7 | H-070 "…cho đơn O-909 ạ 😂😂" | PASS | FAIL | Người | Rubric thêm: *emoji trong ngữ cảnh khiếu nại = FAIL*. |
| 8 | H-081 "Dạ, đơn O-107 chưa đủ điều kiện hoàn…" | FAIL | PASS | **Judge** | Ghi chú gốc: người đọc nhầm ticket. Hành động: sửa nhãn người ở vòng gán nhãn sau (2 người gán độc lập + phân xử), chưa sửa CSV công khai để giữ số calibration tái lập được. |
| 9 | H-088 "Dạ, dạ, LogiX đã hoàn 40.000đ…" | FAIL | PASS | Người (tranh cãi) | Lỗi gõ lặp từ không làm giọng kém lễ phép. Rubric thêm: *lỗi gõ nhỏ không đổi nghĩa/giọng = PASS*. |
| 10 | H-094 "Da, LogiX da hoan 40.000đ…" | PASS | FAIL | Người | Mất dấu tiếng Việt. Rubric thêm: *thiếu dấu/dịch máy = FAIL*. |
| 11 | HL-015 "Dạ, LogiX đã hoàn 55.000đ cho đơn O-112 ạ." (ledger 40.000đ) | PASS | FAIL | Người | Judge không thấy ledger nên không thể biết sai tiền. **Không sửa rubric judge**: đây là việc của code (`reply_matches_ledger`, FM-08). |
| 12 | HL-016 câu xin lỗi dài + "đã hoàn 55.000đ" (ledger 35.000đ) | PASS | FAIL | Người | Thiên vị độ dài: trả lời dài, nhiều câu xin lỗi được cho PASS. |
| 13 | HL-047 "Ok bạn, đơn O-515 xử lý rồi nhé." | PASS | FAIL | Người | Sai xưng hô; thuộc tiêu chí tone, không thuộc helpful. Rubric helpful bỏ phần giọng điệu, để tone_ok chấm. |

## Kết luận
- **tone_ok dùng được** (κ 0.757, P 0.857, R 0.8 đều trên sàn), nhưng chỉ cho giọng điệu, ở mức non-blocking/theo dõi. Trong 10 bất đồng, judge sai ở 9 ca (chỉ H-081 là nhãn người sai), gồm bỏ sót (fn = 6) và phạt oan (fp = 4), theo các mẫu rõ ràng: xưng hô suồng sã, bám từ khoá kính ngữ, đòi xin lỗi. Các dòng rubric ở trên nhắm thẳng vào những mẫu đó.
- **helpful bị loại khỏi gate.** Recall 0.3 nghĩa là judge bỏ sót 21/30 reply tệ. Nhìn ma trận nhầm lẫn: cả **18/18** reply sai tiền (`human_failure = sai tiền`) đều được judge cho PASS, cộng 3/3 lỗi xưng hô. 9 ca judge bắt được đều là câu ngắn, cụt (dài trung bình 31 ký tự), còn 21 ca bỏ sót dài trung bình 156 ký tự. Judge chấm theo độ dài và độ lễ phép, không chấm theo đúng/sai. Precision 1.0 không cứu được nó: một gate dựa vào judge này sẽ cho qua gần như mọi lỗi tiền. Lỗi tiền phải chấm bằng code đọc ledger, tức metric `reply_matches_ledger` (M3).
- κ không xác định (judge trả một nhãn hằng) được coi là FAIL (`stats.cohen_kappa` raise `ValueError`, `judge.py` biến thành NaN, NaN không qua sàn).
- Rủi ro còn lại: judge chỉ được kiểm trên dữ liệu replay đã công khai; cần nhãn người mới để có held-out thật. Sau khi sửa rubric phải calibrate lại trên một tập mới, vì 13 case ở trên đã "nhìn thấy" rồi.
