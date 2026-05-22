# REFLECTIONS.md

## 1) Multi-account: chạy `costctl` cho 100 AWS accounts thì cần đổi gì?

Để chạy `costctl` trên nhiều account, mình sẽ chuyển từ mô hình “1 bộ credentials cố định” sang mô hình **assume role cross-account**. Cụ thể, trong mỗi account cần có một IAM Role (ví dụ `CostCtlRole`) trust về account quản trị. CLI sẽ đọc danh sách account IDs (file CSV/JSON), rồi lặp qua từng account: gọi `sts.assume_role(RoleArn=..., RoleSessionName=...)`, tạo `boto3.Session` từ credentials tạm thời và chạy các lệnh `list/cost/terminate/tag` trong session đó. Output nên được gom về format chuẩn (CSV/JSON) và có cột `account_id`, `region` để dễ tổng hợp và audit.

Ngoài ra, mình sẽ thêm:
- Tùy chọn `--profile` (hoặc `--org-account-list`) để chọn nguồn danh sách account.
- Logging/audit: ghi lại mọi hành động thay đổi trạng thái (terminate/tag/clean) theo time/account/resource-id.
- Rate-limit + retry/backoff vì chạy 100 account sẽ dễ gặp throttling.

## 2) `idle` (24h CPU) vs Trusted Advisor (14 ngày): khi nào tin cái nào?

`idle` dùng cửa sổ 24h CPU average nên hợp để bắt các máy “đang thực sự idle gần đây”, ví dụ dev/test environment vốn thay đổi nhanh, bật/tắt theo ngày. Nó cho phản hồi nhanh hơn, phù hợp để tối ưu chi phí theo sprint hoặc theo lịch làm việc.

Trusted Advisor dùng 14 ngày nên hợp để kết luận “idle dài hạn” ổn định hơn, ít bị nhiễu do burst hoặc workload theo giờ/tuần. TA đáng tin khi quyết định các hành động mạnh (terminate/rightsizing) vì nhìn được xu hướng dài hơn và giảm rủi ro false-positive.

Kết luận: mình dùng `idle` để **cảnh báo nhanh + đề xuất**, còn dùng Trusted Advisor để **xác nhận trước khi hành động** (terminate/resize) hoặc làm policy định kỳ.

## 3) `clean --apply` blast radius: nếu lỡ chạy nhầm trong account dùng chung, cần gì để hạn chế thiệt hại?

Mình muốn có nhiều “lan can an toàn” (safety rails):
- **Dry-run mặc định** và output liệt kê rõ danh sách resource sẽ bị xóa trước khi apply.
- Khi `--apply`, yêu cầu confirm mạnh hơn: gõ lại đúng tag filter hoặc gõ `DELETE` (không chỉ y/N).
- Thêm **allowlist/denylist**: chỉ cho `clean` chạy trên tag `purpose=practice` hoặc `Environment=sandbox`, từ chối các tag nhạy cảm như `prod`.
- IAM policy giới hạn quyền: role chạy `clean` chỉ được terminate resource có tag nhất định (dùng điều kiện IAM `aws:ResourceTag/purpose`).
- Ghi log + rollback plan: CloudTrail + lưu lại danh sách ID đã terminate; với một số resource có thể snapshot/backup trước khi xóa.

Nhờ các bước này, kể cả chạy nhầm filter trong account shared, blast radius sẽ bị chặn ở cả tầng CLI lẫn IAM.