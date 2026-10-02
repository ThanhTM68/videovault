# GitHub Setup

## Tạo repository

Khuyến nghị:
- Name: `videovault`
- Private trong thời gian development
- Không tạo README/gitignore từ GitHub nếu local starter đã có chúng

Sau khi GitHub tạo repository, thêm remote:

```powershell
git remote add origin https://github.com/YOUR_USERNAME/videovault.git
git push -u origin main
```

## Branch strategy

Mỗi phase một branch:

```text
phase/00-bootstrap
phase/01-foundation
phase/02-database
phase/03-download-engine
...
```

Không để Codex làm Phase 03 trên branch Phase 02.

## Commit convention

Ví dụ:

```text
chore: bootstrap repository
feat: add database persistence
feat: add download engine
feat: add queue worker
fix: recover stale download jobs
test: cover duplicate redownload policy
docs: update storage architecture
```

## Pull Requests

Nếu làm một mình vẫn nên dùng PR cho các phase quan trọng:
- Phase 02
- Phase 03
- Phase 05
- Phase 07
- Phase 08
- Phase 11

PR description:
- phase goal
- major changes
- migration/schema change
- tests
- known risks
- screenshots nếu có UI

## Recommended GitHub protections later

Khi project ổn:
- protect `main`
- require tests before merge
- do not allow force push to `main`

## Repository secrets

Không upload secrets vào repository.

Nếu về sau có CI cần secrets:
GitHub repository settings -> Actions secrets.

Không dùng CI secret như một cách để đưa browser cookies/private session vào project.
