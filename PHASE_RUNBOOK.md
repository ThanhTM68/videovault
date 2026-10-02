# Phase Runbook

## Quy trình chuẩn cho MỌI phase

### A. Đồng bộ main

```powershell
git checkout main
git pull
git status
```

Working tree phải sạch.

### B. Xem phase tiếp theo

```powershell
.\scripts\start-phase.ps1 -Phase 3
```

Đổi `3` thành phase cần chạy.

### C. Tạo branch

```powershell
git checkout -b phase/03-download-engine
```

### D. Chọn model

Xem:
`MODEL_MATRIX.md`

Ví dụ Phase 03:
- GPT-6.1 Sol
- High reasoning

Nếu dùng app/IDE, chọn trong model selector.
Nếu project config đang Medium, đổi reasoning của thread sang High.

### E. Chạy implementation prompt

Paste:
`prompts/phase-03-download-engine.md`

Không thêm yêu cầu phase sau vào giữa phase hiện tại.

### F. Nếu phát hiện bug

Dùng:
`prompts/BUG_FIX.md`

### G. Review phase

Dùng:
`prompts/REVIEW_CURRENT_PHASE.md`

Review tốt nhất bằng:
- GPT-6.1 Sol
- High

### H. Kiểm tra thủ công

```powershell
git status
git diff
```

Đọc các file quan trọng Codex đã thay đổi.

### I. Commit

```powershell
git add .
git commit -m "feat: complete phase 03 download engine"
```

### J. Merge

```powershell
git checkout main
git merge --no-ff phase/03-download-engine
```

Có thể push branch + tạo PR thay vì merge local.

## Khi một phase quá lớn

Không chia theo "frontend/backend" tùy tiện nếu làm hỏng acceptance flow.

Hãy yêu cầu Codex:

```text
Break the current ExecPlan into 2-4 implementation milestones,
but keep all milestones inside this same phase.
Complete and test one milestone at a time.
Do not implement future phases.
```

Ví dụ Phase 05 có thể chia:
1. job state model
2. claiming/worker
3. retry/recovery
4. API/progress/tests

## Khi context Codex quá dài

Mở thread mới và nói:

```text
Continue Phase 05 only.
Read AGENTS.md and docs/exec-plans/phase-05-queue-worker.md.
Inspect the repository to determine completed work.
Do not assume prior chat context.
Continue only missing acceptance criteria.
```

Repo + ExecPlan phải đủ để agent tiếp tục mà không cần chat cũ.
