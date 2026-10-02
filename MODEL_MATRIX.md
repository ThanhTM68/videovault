# Codex Model Matrix

## Mặc định toàn repo

- Model: `gpt-6.1-sol`
- Reasoning: `medium`

## Theo phase

| Phase | Công việc | Model | Reasoning |
|---|---|---|---|
| 00 | Bootstrap/tooling | gpt-6-luna hoặc gpt-6.1-sol | medium |
| 01 | Backend foundation | gpt-6.1-sol | medium |
| 02 | Database/schema/migration | gpt-6.1-sol | high |
| 03 | Downloader abstraction | gpt-6.1-sol | high |
| 04 | Platform adapters | gpt-6.1-sol | high |
| 05 | Queue/worker/progress/recovery | gpt-6.1-sol | high |
| 06 | Frontend shell/pages/state | gpt-6.1-sol | medium |
| 07 | Library/history/dedup | gpt-6.1-sol | high |
| 08 | Storage/Google Drive | gpt-6.1-sol | high |
| 09 | Batch profile/channel | gpt-6.1-sol | high |
| 10 | FFmpeg editor/presets | gpt-6.1-sol | high |
| 11 | Hardening/release | gpt-6.1-sol | high |
| 12 | Discover/search | gpt-6.1-sol | high |
| 13 | Similarity/quality analysis | gpt-6.1-sol | high |
| 14 | Automation/watchlist | gpt-6.1-sol | high |

## Khi dùng Luna

Dùng `gpt-6-luna / medium` cho:
- README/docs
- rename/refactor cơ học nhỏ
- thêm test cases rõ ràng
- CRUD đơn giản theo pattern có sẵn
- CSS/UI polish
- lint/type fixes nhỏ

Không ưu tiên Luna cho:
- thiết kế schema
- migration phức tạp
- concurrency
- queue recovery
- downloader extractor abstraction
- OAuth
- FFmpeg graph phức tạp
- similarity algorithms

## Khi tăng lên xhigh

Chỉ tăng `gpt-6.1-sol` từ High lên XHigh nếu:
- agent đã thử 1–2 hướng và vẫn không tìm được root cause;
- bug có race condition;
- migration/data integrity đang nguy hiểm;
- thiết kế có nhiều tradeoff xung đột.

Sau khi xử lý xong, quay lại Medium/High.
