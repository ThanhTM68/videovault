# Codex Setup & Workflow

## 1. Cấu hình project

File `.codex/config.toml` trong starter pack đặt mặc định:

```toml
model = "gpt-6.1-sol"
model_reasoning_effort = "medium"
approval_policy = "on-request"
sandbox_mode = "workspace-write"
web_search = "cached"
personality = "pragmatic"
```

Codex chỉ đọc project-level config khi repo được Trust.

## 2. Model strategy

Không cần dùng model mạnh nhất cho mọi việc.

| Loại việc | Model | Reasoning |
|---|---|---|
| Architecture / DB / downloader abstraction | gpt-6.1-sol | high |
| Feature backend/frontend thông thường | gpt-6.1-sol | medium |
| Integration khó / bug khó / release review | gpt-6.1-sol | high |
| CRUD nhỏ / docs / polish / repetitive tests | gpt-6-luna | medium |
| Rất khó và đang bế tắc | gpt-6.1-sol | xhigh, chỉ khi cần |

Mặc định giữ `gpt-6.1-sol / medium`.

## 3. Cách chạy một phase

Ví dụ Phase 03:

1. Tạo branch:

```powershell
git checkout -b phase/03-download-engine
```

2. Chọn model theo `MODEL_MATRIX.md`.

3. Mở `prompts/phase-03-download-engine.md`.

4. Copy toàn bộ prompt vào Codex.

5. Để Codex inspect repo, implement, chạy test.

6. Sau khi Codex báo xong, dùng prompt review:

```text
Review the current phase against its ExecPlan and acceptance criteria.
Do not add new product features.
Run all relevant tests and inspect the git diff.
Fix correctness, maintainability, typing, migration, error-handling, and test gaps.
Then report:
1. acceptance criteria status,
2. tests run,
3. changed files,
4. remaining risks,
5. intentionally deferred items.
```

7. Nếu pass:

```powershell
git status
git add .
git commit -m "feat: complete phase 03 download engine"
```

## 4. Không chạy nhiều phase trong cùng một thread khi không cần

Khuyến nghị:
- 1 thread = 1 phase lớn.
- Bug nhỏ có thể tiếp tục thread phase đó.
- Khi sang phase mới, mở thread mới để giảm context cũ.

## 5. Khi Codex muốn mở rộng scope

Trả lời:

```text
Stay within the current phase.
Record the idea under Deferred / Future Work in the phase ExecPlan,
but do not implement it now.
```

## 6. Khi Codex bị kẹt

Dùng:

```text
Stop changing code for a moment.
Inspect the current implementation, failing tests, logs, and relevant docs.
Identify the smallest root cause.
Propose the minimal fix within the current phase.
Then implement and verify it.
Do not rewrite unrelated modules.
```

Chuyển reasoning lên High nếu lỗi liên quan:
- transaction / concurrency
- downloader state machine
- queue recovery
- Alembic migrations
- cross-platform filesystem
- ffmpeg command construction
- OAuth / Drive resumable upload

## 7. Definition of Done chung

Một phase chỉ được coi hoàn thành khi:

- Acceptance criteria trong ExecPlan đều pass.
- Test mới có cho logic quan trọng.
- Test cũ vẫn pass.
- Không có secret trong Git.
- `.env.example` được cập nhật nếu thêm config.
- Docs được cập nhật nếu thay đổi API/schema/architecture.
- Không có TODO quan trọng bị giấu.
- `git diff` không chứa thay đổi ngoài scope.
