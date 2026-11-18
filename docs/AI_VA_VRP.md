# AI và tuyến thu gom: phương pháp, kết quả, giới hạn

## Dự báo mức đầy

Mục tiêu chính là **mức đầy sau 60 phút**, cấu hình bằng `train --horizon-minutes`. Không phải phân loại loại rác, không phải ETA còn bao lâu đầy. Không dùng AI để mở/đóng nắp, cắt nguồn hoặc hủy cảnh báo mức đo thực.

`backend/ml.py` dùng 9 đặc trưng có sẵn ở thời điểm dự báo: mức hiện tại, lag khoảng 15/30 phút, tốc độ tăng theo **thời gian thật**, số lệnh mở trong 30 phút cùng boot, sin/cos giờ và thứ trong tuần theo UTC+7. Tốc độ âm được đặt 0 cho baseline tuyến tính; không suy ra rằng mỗi lần mở nắp tương ứng thêm một lượng rác cố định. Không đưa seed, tốc độ sinh ngầm, nhãn anomaly hoặc giá trị fill thật ẩn của simulator vào feature.

Cần lịch sử khoảng 30 phút, lag lấy mẫu tại/trước mốc, sai lệch tối đa 300 giây; không có khoảng thiếu trên 900 giây trong cửa sổ. Không ghép lag qua hai boot. Inference chỉ lấy lịch sử đúng boot và không vượt seq của trạng thái hiện tại; nếu đồng hồ đảo thứ tự khiến mẫu hiện tại không đứng cuối thì trả unavailable. Bản tin mới nhất phải valid, biết giờ và không cũ hơn 360 giây. Khi latest state lỗi/offline/chưa biết giờ, worker trả unavailable dù lịch sử từng có số đo tốt. Thiếu model có thể dùng baseline tuyến tính có nhãn; thiếu lịch sử thì không sinh số dự báo giả.

RandomForestRegressor: 80 cây, min_samples_leaf=8, thử max_depth=8/14, random_state=42, n_jobs=1. Baseline persistence và tuyến tính cùng dự đoán, cùng tập mẫu, cùng metric. Chọn phương pháp MAE thấp nhất trên **validation**, bao gồm cả baseline. Không buộc ML phải thắng; test chỉ dùng báo kết quả. Artifact được nạp một lần mỗi lần backend khởi động, không fit trong request. Pipeline không cần chuẩn hóa/fit imputer vì chỉ nhận feature hợp lệ.

## Sinh dữ liệu và tái lập

47.171 bản tin mô phỏng gốc: 12 thùng, 14 ngày, bước 300 giây, seed 42, kết thúc `2026-11-17T14:43:20+00:00`. Có nhiều chu kỳ tăng/đổ, tốc độ đổi, nhiễu, spike, khoảng thiếu và sensor fault. `lid_open_count` độc lập lượng rác thêm. Metadata `anomaly_label` nằm ngoài message, chỉ dùng đánh giá/định nghĩa normal train anomaly.

```powershell
.venv\Scripts\python.exe -m simulator.generate --bins 12 --days 14 --seed 42 --end "2026-11-17T14:43:20+00:00" --output data\reproduce-seed42.jsonl
.venv\Scripts\python.exe -m backend.cli train data\reproduce-seed42.jsonl --output data\reproduce-model.joblib
```

Cần **cùng seed, end, số thùng, days, bước đo và dependency** để tái lập. Seed với end mặc định hiện tại không đảm bảo cùng feature giờ/ngày. Không tăng tốc đồng hồ trong dữ liệu huấn luyện; dashboard có lịch sử nạp nhanh nhưng các timestamp vẫn cách nhau 5 phút, không gọi demo vài giây là đánh giá dự báo theo giờ ngoài đời.

Nhãn tương lai lấy bản quan sát đầu tiên tại/sau `t+3600`, sai lệch ≤300 giây; nếu bản đó lỗi hoặc boot khác thì bỏ cặp. Không nội suy qua khoảng thiếu. Chia thời gian toàn cục 60/20/20: train phải có nhãn trước cut1; validation bắt đầu feature sau cut1+lookback+300 giây và nhãn trước cut2; test bắt đầu sau cut2+lookback+300. Vì vậy future label/cửa sổ không chạm ranh giới tập khác. Đã test tính nhân quả và khoảng purge/embargo.

Các tập cùng nhóm thùng; có thể một chu kỳ thu gom đi qua ranh giới sau embargo. Chưa có holdout theo thùng/chu kỳ độc lập, nên **không** tuyên bố khái quát sang địa điểm/thùng mới. Khi có dữ liệu thật, cần đánh giá bổ sung theo chu kỳ và bin-group, lịch vận hành, rác không đều, lắp đặt và mùa. Source real/simulated phải train/evaluate riêng; model simulated không được dùng như RF cho thùng real, chỉ fallback baseline có nhãn.

## Kết quả seed 42 đã chạy

Train 26.826 cặp, validation 8.804, test 8.751. Pipeline 1.0, scikit-learn 1.9.1, model `04740a949ede9057`. SHA-256 dữ liệu và toàn bộ metric nằm trong [JSON kết quả](results/ai-seed42.metrics.json).

| Phương pháp | MAE, điểm % | RMSE, điểm % | TP | FP | FN | TN |
|---|---:|---:|---:|---:|---:|---:|
| Giữ nguyên mức hiện tại | 9,007 | 20,230 | 1.170 | 478 | 453 | 6.650 |
| Ngoại suy tuyến tính | 8,537 | 21,394 | 1.457 | 668 | 166 | 6.460 |
| Random Forest depth 14 | **5,067** | **12,639** | 1.258 | 155 | 365 | 6.973 |

TP/FP/FN/TN tính **theo từng mẫu**, positive là dự đoán sau 60 phút ≥80%, actual là số đo nhãn tương lai ≥80%. Đây không phải đếm episode cảnh báo hoặc chứng minh gửi đúng thời gian tới người dùng. RF giảm MAE/FP nhưng bỏ sót nhiều mẫu positive hơn baseline tuyến tính; không thể dùng một MAE thấp để khẳng định mọi tiêu chí tốt hơn.

Cảnh báo sớm worker yêu cầu current state usable, mức hiện tại dưới ngưỡng nhưng dự đoán đạt ngưỡng và còn hiệu lực. Cooldown một giờ/thùng; nếu IF đánh dấu bất thường thì không dùng phần dự báo để tạo cảnh báo sớm/lập tuyến, còn cảnh báo mức đo thực vẫn độc lập. Message có nhãn DỰ ĐOÁN và tên phương pháp. Cảnh báo đo đầy là luồng riêng. Dự báo có `created_at`, `valid_until`, `source`, `model_version`, `horizon_seconds`, `reason`; UI không tái dùng dự báo quá hạn cho lập tuyến.

## Bất thường

IsolationForest: 100 cây, contamination=0,025, seed 42. Fit chỉ trên train normal theo nhãn có sẵn, không dùng test để fit. So với rule `abs(fill_now-fill_lag15)>25 điểm %` trên cùng test:

| Cách phát hiện | TP | FP | FN | TN | Tỷ lệ báo nhầm trên normal |
|---|---:|---:|---:|---:|---:|
| Isolation Forest | 50 | 336 | 48 | 8.317 | 3,883% |
| Rule nhảy 25 điểm % | 74 | 190 | 24 | 8.463 | 2,196% |

Trong bộ này rule tốt hơn IF ở các chỉ số trên. IF chỉ hiển thị **dữ liệu bất thường/cần kiểm tra**, không chẩn đoán ẩm, sensor hỏng hoặc kẹt servo; có thể coi đây là minh chứng không nên thêm ML mà thiếu baseline. Nhãn spike tổng hợp không đại diện đầy đủ anomaly thực tế; các lần đổ rác tự nhiên cũng có thể kích hoạt rule. Timeout/chất lượng vẫn xử lý rõ ràng ngoài mô hình.

Median/Trimmed Mean là xử lý tín hiệu; hysteresis là logic điều khiển; RF/IF là mô hình học từ dữ liệu. Không gọi bộ lọc là AI để tăng số lượng chức năng.

## CVRP

`backend/routing.py` dùng OR-Tools, cấu hình depot, số xe 1–20, sức chứa theo lít, threshold, source, include_predictions, uncertain_policy và time limit 1–10 giây. Tối đa 100 điểm trong demo. Nghiệm trả là tốt nhất tìm được trong thời gian, **không chứng minh tối ưu toàn cục**.

Chỉ chọn số đo usable đạt threshold (mặc định dùng ngưỡng từng thùng, cấu hình mẫu 80%); nếu bật AI, chỉ dùng prediction available, cùng source, còn hiệu lực và lấy mức lớn hơn để bảo thủ về tải. `review` mặc định tách offline/stale/FAULT/unknown sang manual_review, không coi bằng 0. `conservative` có thể đưa chúng vào với giả định đầy 100%, ghi lý do; không giả vờ đã đo được 100%.

Nhu cầu `ceil(capacity_l × fill_pct / 100)` lít **ước lượng**, giả định tiết diện đều, rác phân bố đều. Xe dùng cùng đơn vị lít; không đổi sang kg. Ma trận Haversine làm tròn mét, tuyến nối tọa độ địa lý, không có dữ liệu đường bộ. Không dùng để điều hướng xe ngoài thực tế. Điểm có demand vượt sức chứa một xe hoặc tổng không đủ được trả unserved cùng lý do, không im lặng bỏ điểm.

Baseline nearest-neighbor chạy cùng points/depot/xe/capacity, quay về depot. Báo cả số/tập bị bỏ; chỉ tính % giảm khoảng cách khi cùng **tập được phục vụ**, không chỉ cùng số lượng. Không chọn phục vụ ít điểm hơn rồi quảng cáo ngắn hơn. Có test rỗng/một điểm/nhiều xe/vượt capacity/stale/expiry và smoke 100 điểm.

Lần smoke ghi lại: 30 thùng, các điểm đạt ngưỡng được phục vụ đủ, khoảng cách 16.997 m so với baseline 17.907 m (~5,08%). Case riêng **100 thùng đều 90%**, 10 xe ×1500 lít, time limit 3 giây: 166.391 m so với baseline 178.409 m (~6,74%), không bỏ điểm. Đây là bài toán tổng hợp; thời gian solver/CPU có thể làm nghiệm đổi giữa các lần chạy. Xem `docs/results/smoke.json`, không dùng phần trăm này làm cam kết tiết kiệm đường thực tế.

Nguồn phương pháp: [scikit-learn về chia chuỗi thời gian và gap](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html), [OR-Tools capacity constraints](https://developers.google.com/optimization/routing/cvrp). Mã chia purge/embargo trong project được viết riêng cho target tương lai, không gọi TimeSeriesSplit mặc định rồi giả định đã hết leakage.
