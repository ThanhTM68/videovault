# Windows Setup — VideoVault + Codex

Hướng dẫn này giả định Windows 10/11 + PowerShell.

## 1. Cài Git

Có thể cài từ Git for Windows hoặc dùng winget:

```powershell
winget install --id Git.Git -e
```

Mở terminal mới:

```powershell
git --version
```

## 2. Cài Python

Khuyến nghị Python 3.12+.

Ví dụ:

```powershell
winget install --id Python.Python.3.12 -e
```

Kiểm tra:

```powershell
python --version
pip --version
```

## 3. Cài Node.js

Dùng Node LTS.

```powershell
winget install --id OpenJS.NodeJS.LTS -e
```

Kiểm tra:

```powershell
node --version
npm --version
```

## 4. Cài FFmpeg

Bạn có thể cài FFmpeg bằng package manager hoặc bản build phù hợp.

Sau khi cài, các lệnh này phải chạy được:

```powershell
ffmpeg -version
ffprobe -version
```

Nếu không nhận lệnh, thêm thư mục `bin` của FFmpeg vào PATH.

## 5. Cài Codex CLI

```powershell
npm install -g @openai/codex@latest
```

Kiểm tra:

```powershell
codex --version
```

Khởi động:

```powershell
codex
```

Làm theo bước đăng nhập hiển thị bởi Codex.

## 6. Docker — optional

Docker Desktop không bắt buộc cho các phase đầu.

Nếu muốn dùng về sau:

```powershell
winget install --id Docker.DockerDesktop -e
```

## 7. Chuẩn bị repo

Giải nén starter pack:

```text
videovault-codex-starter/
```

Bạn có thể rename thành:

```text
videovault/
```

Mở PowerShell tại folder đó.

```powershell
git init
git branch -M main
git add .
git commit -m "chore: initialize VideoVault Codex project"
```

## 8. Kiểm tra tool

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\verify-tools.ps1
```

Tối thiểu trước Phase 03:
- Git
- Python
- Node/npm
- FFmpeg
- ffprobe

## 9. Trust project trong Codex

Project config nằm ở:

```text
.codex/config.toml
```

Nếu Codex hỏi repo có đáng tin cậy hay không, chỉ trust repo của chính bạn.

Mặc định starter:
- gpt-6.1-sol
- medium reasoning
- on-request approvals
- workspace-write sandbox

Không đổi sang danger-full-access chỉ để tránh approval.

## 10. Chạy Phase 00

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-phase.ps1 -Phase 0
```

Script sẽ chỉ cho bạn:
- branch nên tạo
- prompt cần mở

Sau đó:

```powershell
git checkout -b phase/00-bootstrap
codex
```

Trong Codex, paste nội dung:

```text
prompts/phase-00-bootstrap.md
```

## 11. Sau khi phase hoàn tất

Chạy review prompt:

```text
prompts/REVIEW_CURRENT_PHASE.md
```

Sau khi pass:

```powershell
git status
git add .
git commit -m "feat: complete phase 00 bootstrap"
git checkout main
git merge --no-ff phase/00-bootstrap
```

Sau đó chuyển Phase 01.

## 12. Không lưu secrets

Không commit:
- `.env`
- cookie
- Google OAuth token
- credential JSON
- video tải xuống
- temp media

Kiểm tra trước commit:

```powershell
git status
git diff --cached
```
