# VideoVault — Codex Starter Pack

Bộ file này dùng để phát triển VideoVault theo từng phase bằng Codex, tránh yêu cầu agent làm toàn bộ dự án trong một lần.

## Mục tiêu sản phẩm

VideoVault là local-first web app để:

- Thu thập metadata video short từ nhiều nền tảng.
- Tải video công khai khi người dùng có quyền lưu.
- Batch theo URL/channel/profile khi nguồn hỗ trợ.
- Quản lý queue, history, library và chống tải trùng.
- Lưu local hoặc Google Drive.
- Xử lý media bằng FFmpeg.
- Về sau: discover, similarity, reupload grouping, quality analysis.

Nền tảng ưu tiên:

1. YouTube / Shorts
2. TikTok
3. Douyin
4. Instagram / Reels
5. Facebook / Reels

## Stack V1

Frontend:
- Vue 3
- TypeScript
- Vite
- Pinia
- Vue Router

Backend:
- Python 3.12+
- FastAPI
- SQLAlchemy 2
- Alembic
- Pydantic v2
- SQLite

Media:
- yt-dlp
- FFmpeg / ffprobe

Testing:
- pytest
- Vitest

## Thứ tự sử dụng

Nếu bạn dùng Windows, đọc `WINDOWS_SETUP.md` trước. GitHub workflow nằm trong `GITHUB_SETUP.md` và quy trình chạy phase nằm ở `PHASE_RUNBOOK.md`.


1. Copy toàn bộ bộ file này vào repo mới.
2. Đọc `CODEX_SETUP.md`.
3. Cài tool bằng `scripts/verify-tools.ps1`.
4. Mở Codex ở root repo và Trust project.
5. Chạy từng prompt trong `prompts/`, đúng thứ tự.
6. Mỗi phase dùng branch riêng.
7. Chỉ merge khi checklist phase đạt hết.
8. Không bảo Codex "làm toàn bộ project".

## Thứ tự phase

- Phase 00 — Repository bootstrap
- Phase 01 — Backend foundation
- Phase 02 — Database + migrations
- Phase 03 — Download engine core
- Phase 04 — Platform adapters + metadata normalization
- Phase 05 — Queue + worker + progress
- Phase 06 — Frontend shell + Download + Queue
- Phase 07 — Library + History + Dedup
- Phase 08 — Storage + Google Drive abstraction
- Phase 09 — Batch channel/profile
- Phase 10 — FFmpeg editor + presets
- Phase 11 — V1 hardening + release
- Phase 12 — V2 Discover + search
- Phase 13 — V2 Similarity + quality analysis
- Phase 14 — V2 Watchlist + automation rules

## Quy tắc quan trọng

- Phase hiện tại không được tự ý implement phase sau.
- Không bypass DRM, private content, login restrictions hoặc access controls.
- Không lưu cookie/token vào Git.
- Platform adapter có thể lỗi do website thay đổi; phải cô lập logic theo adapter.
- Tất cả tính năng batch phải đi qua queue.
- Database là nguồn sự thật cho downloaded/history state; không suy ra chỉ bằng filename.
