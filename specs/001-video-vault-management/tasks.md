# Tasks: Video Vault Management

**Input**: Design documents from `/specs/001-video-vault-management/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/openapi.yaml, quickstart.md

**Tests**: Automated tests are REQUIRED for behavior changes. Write the test tasks in each story phase first and verify they fail before implementation.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4, US5)
- Include exact file paths in descriptions

## Path Conventions

- **Backend**: `apps/backend/app/`, `apps/backend/tests/`, `apps/backend/alembic/`
- **Frontend**: `apps/frontend/src/`, `apps/frontend/tests/`
- **End-to-end**: `apps/e2e/tests/`, `apps/e2e/fixtures/`
- **Infrastructure**: `infra/terraform/`
- **CI/CD**: `.github/workflows/`
- **Feature docs**: `specs/001-video-vault-management/`

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Initialize the monorepo workspaces and shared tooling required by all stories.

- [ ] T001 Create backend directory skeleton in `apps/backend/app/`, `apps/backend/app/api/routers/`, and `apps/backend/tests/`
- [ ] T002 Initialize backend package with `uv init --package` in `apps/backend/pyproject.toml`
- [ ] T003 Add backend runtime dependencies with `uv add "fastapi[standard]" fastapi-azure-auth sqlmodel alembic azure-storage-blob bencode2` in `apps/backend/pyproject.toml`
- [ ] T004 Add backend development dependencies with `uv add --dev pytest pytest-asyncio httpx ruff ty` in `apps/backend/pyproject.toml`
- [ ] T005 Create frontend React TypeScript workspace with Vite in `apps/frontend/package.json`
- [ ] T006 Configure frontend test dependencies and scripts in `apps/frontend/package.json` and `apps/frontend/vite.config.ts`
- [ ] T007 Initialize Playwright end-to-end workspace in `apps/e2e/package.json` and `apps/e2e/playwright.config.ts`
- [ ] T008 Create Terraform workspace directories in `infra/terraform/bootstrap/`, `infra/terraform/envs/dev/`, and `infra/terraform/modules/`
- [ ] T009 Create architecture decision directory in `docs/decisions/`
- [ ] T010 [P] Create backend container definition in `apps/backend/Dockerfile`
- [ ] T011 [P] Create root ignore rules for Python, Node, Terraform, and Playwright output in `.gitignore`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core application, persistence, authentication, storage, and test foundations that MUST be complete before any user story can be implemented.

**CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T012 Define backend settings, environment names, and test-mode flags in `apps/backend/app/core/config.py`
- [ ] T013 Create database engine/session helpers in `apps/backend/app/core/db.py`
- [ ] T014 Define SQLModel entities and relationships for User, Torrent, TorrentFile, Video, Tag, VideoTag, and TorrentProcessingJob in `apps/backend/app/core/models.py`
- [ ] T015 Configure Alembic migration environment in `apps/backend/alembic/env.py`
- [ ] T016 Create initial Alembic migration for tables, relationships, uniqueness constraints, and search indexes in `apps/backend/alembic/versions/001_initial_video_vault.py`
- [ ] T017 Implement authentication dependency with Entra ID path and explicit test bypass in `apps/backend/app/auth/dependencies.py`
- [ ] T018 Implement role authorization helpers for admin-only routes in `apps/backend/app/auth/authorization.py`
- [ ] T019 Create shared API dependency wiring for sessions, current user, and pagination in `apps/backend/app/api/deps.py`
- [ ] T020 Create FastAPI app factory, router registration, CORS, and health route in `apps/backend/app/main.py`
- [ ] T021 Implement shared error response models and exception handlers in `apps/backend/app/core/errors.py`
- [ ] T022 Create Azure Blob storage abstraction with filesystem/test double support in `apps/backend/app/storage/blob_store.py`
- [ ] T023 Define torrent metadata provider protocol and deterministic fake provider in `apps/backend/app/torrents/provider.py`
- [ ] T024 Create backend pytest fixtures for database, blob store, provider, and test users in `apps/backend/tests/conftest.py`
- [ ] T025 Create frontend API client base, error handling, and auth header injection in `apps/frontend/src/shared/api/client.ts`
- [ ] T026 Create frontend app shell, routing, and test providers in `apps/frontend/src/app/App.tsx` and `apps/frontend/src/test/render.tsx`
- [ ] T027 Create Playwright deterministic auth and torrent fixtures in `apps/e2e/fixtures/test-users.ts` and `apps/e2e/fixtures/torrents.ts`

**Checkpoint**: Foundation ready. User story implementation can now begin in priority order or in parallel where dependencies allow.

---

## Phase 3: User Story 1 - Add Video by Info Hash (Priority: P1) MVP

**Goal**: Users can add a video with a valid info hash, optional personal details, and see metadata processing status.

**Independent Test**: Submit a valid info hash as a standard user, verify a video appears in that user's collection, and verify success/failure metadata status updates without losing personal details.

### Tests for User Story 1 (write first)

- [ ] T028 [P] [US1] Add contract tests for `POST /videos` accepted, invalid hash, and duplicate-personal-entry responses in `apps/backend/tests/contract/test_videos_create_contract.py`
- [ ] T029 [P] [US1] Add unit tests for info hash normalization and rating validation in `apps/backend/tests/unit/test_video_validation.py`
- [ ] T030 [P] [US1] Add unit tests for torrent parsing success, invalid bytes, and non-UTF8 paths in `apps/backend/tests/unit/test_torrent_provider.py`
- [ ] T031 [P] [US1] Add integration tests for adding a video and queuing metadata processing in `apps/backend/tests/integration/test_add_video.py`
- [ ] T032 [P] [US1] Add frontend tests for required hash input, optional fields, and status messages in `apps/frontend/src/features/videos/AddVideoForm.test.tsx`
- [ ] T033 [P] [US1] Add Playwright test for add-video processing status flow in `apps/e2e/tests/add-video.spec.ts`

### Implementation for User Story 1

- [ ] T034 [US1] Implement video create request/response schemas in `apps/backend/app/videos/schemas.py`
- [ ] T035 [US1] Implement info hash normalization and video validation helpers in `apps/backend/app/videos/validation.py`
- [ ] T036 [US1] Implement torrent bencode parsing and metadata normalization in `apps/backend/app/torrents/parser.py`
- [ ] T037 [US1] Implement create-video service with canonical torrent creation and processing job enqueue in `apps/backend/app/videos/service.py`
- [ ] T038 [US1] Implement metadata processing service that stores raw torrent bytes and file metadata in `apps/backend/app/torrents/service.py`
- [ ] T039 [US1] Implement `POST /videos` route in `apps/backend/app/api/routers/videos.py`
- [ ] T040 [US1] Register videos router in `apps/backend/app/main.py`
- [ ] T041 [US1] Implement frontend add-video API call in `apps/frontend/src/features/videos/api.ts`
- [ ] T042 [US1] Implement add-video form with required and optional fields in `apps/frontend/src/features/videos/AddVideoForm.tsx`
- [ ] T043 [US1] Implement metadata status component with pending, processing, succeeded, and failed states in `apps/frontend/src/features/videos/MetadataStatus.tsx`
- [ ] T044 [US1] Add add-video route and navigation entry in `apps/frontend/src/app/routes.tsx`
- [ ] T045 [US1] Validate video submission acknowledgement performance and document results in `specs/001-video-vault-management/validation/add-video-performance.md`

**Checkpoint**: User Story 1 is functional and independently testable.

---

## Phase 4: User Story 2 - View and Search Personal Collection (Priority: P2)

**Goal**: Users can view only their own videos and search by personal details, tags, rating, torrent name, or info hash.

**Independent Test**: Seed multiple users and videos, search as one user, and verify results include only that user's matching videos with clear empty states.

### Tests for User Story 2 (write first)

- [ ] T046 [P] [US2] Add contract tests for `GET /videos` and `GET /videos/{videoId}` in `apps/backend/tests/contract/test_videos_read_contract.py`
- [ ] T047 [P] [US2] Add integration tests for user-scoped collection search and empty results in `apps/backend/tests/integration/test_video_search.py`
- [ ] T048 [P] [US2] Add integration tests preventing cross-user video detail access in `apps/backend/tests/integration/test_video_user_isolation.py`
- [ ] T049 [P] [US2] Add frontend tests for collection loading, search results, and empty states in `apps/frontend/src/features/videos/CollectionPage.test.tsx`
- [ ] T050 [P] [US2] Add Playwright test for collection search by title, tag, rating, torrent name, and info hash in `apps/e2e/tests/search-collection.spec.ts`

### Implementation for User Story 2

- [ ] T051 [US2] Implement collection search query builder with user scoping and pagination in `apps/backend/app/videos/search.py`
- [ ] T052 [US2] Implement video summary/detail response mapping in `apps/backend/app/videos/schemas.py`
- [ ] T053 [US2] Implement `GET /videos` and `GET /videos/{videoId}` routes in `apps/backend/app/api/routers/videos.py`
- [ ] T054 [US2] Implement frontend collection and detail API calls in `apps/frontend/src/features/videos/api.ts`
- [ ] T055 [US2] Implement collection list page with search controls in `apps/frontend/src/features/videos/CollectionPage.tsx`
- [ ] T056 [US2] Implement video detail page with torrent file list in `apps/frontend/src/features/videos/VideoDetailPage.tsx`
- [ ] T057 [US2] Implement loading, error, and empty collection states in `apps/frontend/src/features/videos/CollectionStates.tsx`
- [ ] T058 [US2] Validate 10,000-video search performance and document results in `specs/001-video-vault-management/validation/search-performance.md`

**Checkpoint**: User Story 2 is functional and independently testable.

---

## Phase 5: User Story 3 - Reuse Canonical Torrent Records (Priority: P3)

**Goal**: Multiple users adding the same info hash share one canonical torrent record while retaining separate personal video records.

**Independent Test**: Two users add the same info hash concurrently and end with one torrent record, two video records, and independent personal details.

### Tests for User Story 3 (write first)

- [ ] T059 [P] [US3] Add unit tests for transaction-safe canonical torrent upsert in `apps/backend/tests/unit/test_torrent_upsert.py`
- [ ] T060 [P] [US3] Add integration tests for two users adding the same info hash in `apps/backend/tests/integration/test_canonical_torrent_reuse.py`
- [ ] T061 [P] [US3] Add integration tests for same-user duplicate info hash conflict in `apps/backend/tests/integration/test_duplicate_video_conflict.py`
- [ ] T062 [P] [US3] Add Playwright test for two users referencing the same torrent with separate details in `apps/e2e/tests/canonical-torrent.spec.ts`

### Implementation for User Story 3

- [ ] T063 [US3] Implement transaction-safe torrent lookup/create by unique info hash in `apps/backend/app/torrents/repository.py`
- [ ] T064 [US3] Update create-video service to reuse canonical torrent records and preserve user-specific fields in `apps/backend/app/videos/service.py`
- [ ] T065 [US3] Implement same-user duplicate video conflict handling in `apps/backend/app/videos/service.py`
- [ ] T066 [US3] Add duplicate conflict response handling in `apps/frontend/src/features/videos/AddVideoForm.tsx`
- [ ] T067 [US3] Document canonical torrent concurrency behavior in `docs/decisions/001-canonical-torrent-reuse.md`

**Checkpoint**: User Story 3 is functional and independently testable.

---

## Phase 6: User Story 4 - Admin Tag Management (Priority: P4)

**Goal**: Administrators can create, rename, and delete shared tags while non-admin users are blocked from management actions.

**Independent Test**: Admin creates, renames, and deletes a tag; standard users cannot access tag management; deleted tags disappear from videos and future choices.

### Tests for User Story 4 (write first)

- [ ] T068 [P] [US4] Add contract tests for `GET /admin/tags`, `POST /admin/tags`, `PATCH /admin/tags/{tagId}`, and `DELETE /admin/tags/{tagId}` in `apps/backend/tests/contract/test_admin_tags_contract.py`
- [ ] T069 [P] [US4] Add integration tests for admin tag create, rename, delete, uniqueness, and association cleanup in `apps/backend/tests/integration/test_admin_tags.py`
- [ ] T070 [P] [US4] Add unit tests for admin authorization helpers in `apps/backend/tests/unit/test_authorization.py`
- [ ] T071 [P] [US4] Add frontend tests for admin tag management states in `apps/frontend/src/features/tags/AdminTagManagementPage.test.tsx`
- [ ] T072 [P] [US4] Add Playwright test for admin tag management and non-admin denial in `apps/e2e/tests/admin-tags.spec.ts`

### Implementation for User Story 4

- [ ] T073 [US4] Implement tag request/response schemas in `apps/backend/app/tags/schemas.py`
- [ ] T074 [US4] Implement tag service for create, rename, delete, uniqueness, and association cleanup in `apps/backend/app/tags/service.py`
- [ ] T075 [US4] Implement admin tag routes in `apps/backend/app/api/routers/admin_tags.py`
- [ ] T076 [US4] Register admin tag router in `apps/backend/app/main.py`
- [ ] T077 [US4] Implement frontend tag management API calls in `apps/frontend/src/features/tags/api.ts`
- [ ] T078 [US4] Implement admin tag management page in `apps/frontend/src/features/tags/AdminTagManagementPage.tsx`
- [ ] T079 [US4] Add admin-only route guard and restricted access state in `apps/frontend/src/features/auth/AdminOnly.tsx`

**Checkpoint**: User Story 4 is functional and independently testable.

---

## Phase 7: User Story 5 - Validate Delivery Foundations (Priority: P5)

**Goal**: Developers can set up, validate, and run repeatable local and CI checks for the backend, frontend, e2e, and infrastructure workspaces.

**Independent Test**: From a fresh devcontainer, run documented validation commands and complete deterministic core end-to-end flows without a live external identity provider.

### Tests for User Story 5 (write first)

- [ ] T080 [P] [US5] Add backend CI workflow check definitions in `.github/workflows/backend-ci.yml`
- [ ] T081 [P] [US5] Add frontend CI workflow check definitions in `.github/workflows/frontend-ci.yml`
- [ ] T082 [P] [US5] Add e2e CI workflow check definitions in `.github/workflows/e2e-ci.yml`
- [ ] T083 [P] [US5] Add Terraform validation workflow in `.github/workflows/terraform-ci.yml`
- [ ] T084 [P] [US5] Add Playwright test-mode seed fixture coverage in `apps/e2e/tests/test-mode-fixtures.spec.ts`

### Implementation for User Story 5

- [ ] T085 [US5] Implement backend test-mode user and provider seeding in `apps/backend/app/testsupport/seeding.py`
- [ ] T086 [US5] Implement frontend test-mode auth selection in `apps/frontend/src/features/auth/testMode.ts`
- [ ] T087 [US5] Implement Terraform bootstrap storage resources for remote state in `infra/terraform/bootstrap/main.tf`
- [ ] T088 [US5] Implement Terraform dev environment for SQL, blob storage, Container Apps, and Static Web Apps in `infra/terraform/envs/dev/main.tf`
- [ ] T089 [US5] Implement reusable Terraform modules in `infra/terraform/modules/app/`, `infra/terraform/modules/database/`, and `infra/terraform/modules/storage/`
- [ ] T090 [US5] Add backend deployment workflow using Docker Hub image input in `.github/workflows/deploy-backend.yml`
- [ ] T091 [US5] Add frontend deployment workflow for Static Web Apps in `.github/workflows/deploy-frontend.yml`
- [ ] T092 [US5] Update setup and validation documentation in `README.md`
- [ ] T093 [US5] Validate quickstart commands and record results in `specs/001-video-vault-management/validation/quickstart-validation.md`

**Checkpoint**: User Story 5 is functional and independently testable.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Final quality, security, performance, and documentation work across all stories.

- [ ] T094 [P] Add OpenAPI contract validation command documentation in `docs/decisions/002-api-contract-validation.md`
- [ ] T095 [P] Add production authentication configuration notes in `docs/decisions/003-authentication-configuration.md`
- [ ] T096 [P] Add torrent provider production adapter decision notes in `docs/decisions/004-torrent-metadata-provider.md`
- [ ] T097 Run backend formatting, linting, type checking, and pytest; record results in `specs/001-video-vault-management/validation/backend-validation.md`
- [ ] T098 Run frontend build and tests; record results in `specs/001-video-vault-management/validation/frontend-validation.md`
- [ ] T099 Run Playwright end-to-end tests; record results in `specs/001-video-vault-management/validation/e2e-validation.md`
- [ ] T100 Run Terraform format and validation; record results in `specs/001-video-vault-management/validation/terraform-validation.md`
- [ ] T101 Review security-sensitive configuration defaults in `apps/backend/app/core/config.py` and `infra/terraform/envs/dev/main.tf`
- [ ] T102 Verify all success criteria from `specs/001-video-vault-management/spec.md` and record outcome in `specs/001-video-vault-management/validation/success-criteria.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies; can start immediately.
- **Foundational (Phase 2)**: Depends on Setup completion; blocks all user stories.
- **User Story 1 (Phase 3)**: Depends on Foundational; MVP scope.
- **User Story 2 (Phase 4)**: Depends on Foundational and benefits from US1 data creation, but search can be developed with fixtures.
- **User Story 3 (Phase 5)**: Depends on US1 create-video service and Foundational uniqueness constraints.
- **User Story 4 (Phase 6)**: Depends on Foundational auth and Tag/VideoTag models.
- **User Story 5 (Phase 7)**: Depends on Setup and Foundational; can proceed in parallel with feature stories after shared commands exist.
- **Polish (Phase 8)**: Depends on all desired stories being complete.

### User Story Dependencies

- **US1 Add Video by Info Hash**: MVP; no story dependency after Foundation.
- **US2 View and Search Personal Collection**: Requires models and fixtures; can start after Foundation, but final validation uses US1 video creation.
- **US3 Reuse Canonical Torrent Records**: Extends US1 create-video flow.
- **US4 Admin Tag Management**: Can start after Foundation once auth and Tag models exist.
- **US5 Validate Delivery Foundations**: Can start after Setup and Foundation, with final e2e validation after US1-US4 flows exist.

### Within Each User Story

- Write tests first and verify they fail.
- Implement backend service/domain logic before API route wiring.
- Implement API contract behavior before frontend integration.
- Implement frontend UI states before Playwright validation.
- Complete and validate each story before moving to the next priority when working sequentially.

### Parallel Opportunities

- Setup tasks T010-T011 can run in parallel with other setup tasks after directories exist.
- Foundational tasks T017-T018, T022-T023, and T025-T027 touch separate files and can run in parallel after T012-T016 are underway.
- Test tasks within each user story are parallelizable because they target separate test files.
- US2 and US4 can proceed in parallel after Foundation if staffed separately.
- US5 CI and Terraform tasks can proceed in parallel with US1-US4 implementation after Setup.
- Polish documentation tasks T094-T096 can run in parallel.

---

## Parallel Example: User Story 1

```bash
# Launch US1 tests together:
Task: "T028 Contract tests in apps/backend/tests/contract/test_videos_create_contract.py"
Task: "T029 Validation unit tests in apps/backend/tests/unit/test_video_validation.py"
Task: "T030 Torrent provider unit tests in apps/backend/tests/unit/test_torrent_provider.py"
Task: "T031 Integration tests in apps/backend/tests/integration/test_add_video.py"
Task: "T032 Frontend tests in apps/frontend/src/features/videos/AddVideoForm.test.tsx"
Task: "T033 Playwright test in apps/e2e/tests/add-video.spec.ts"
```

## Parallel Example: User Story 2

```bash
# Launch US2 tests together:
Task: "T046 Contract tests in apps/backend/tests/contract/test_videos_read_contract.py"
Task: "T047 Search integration tests in apps/backend/tests/integration/test_video_search.py"
Task: "T048 User isolation tests in apps/backend/tests/integration/test_video_user_isolation.py"
Task: "T049 Frontend collection tests in apps/frontend/src/features/videos/CollectionPage.test.tsx"
Task: "T050 Playwright search test in apps/e2e/tests/search-collection.spec.ts"
```

## Parallel Example: User Story 4

```bash
# Launch US4 tests together:
Task: "T068 Contract tests in apps/backend/tests/contract/test_admin_tags_contract.py"
Task: "T069 Admin tag integration tests in apps/backend/tests/integration/test_admin_tags.py"
Task: "T070 Authorization unit tests in apps/backend/tests/unit/test_authorization.py"
Task: "T071 Frontend admin tests in apps/frontend/src/features/tags/AdminTagManagementPage.test.tsx"
Task: "T072 Playwright admin test in apps/e2e/tests/admin-tags.spec.ts"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup.
2. Complete Phase 2: Foundational.
3. Complete Phase 3: User Story 1.
4. Stop and validate US1 independently with backend, frontend, and Playwright tests.
5. Demo add-video with deterministic metadata fixture and status updates.

### Incremental Delivery

1. Add US1 to create the first usable video collection entry.
2. Add US2 to make the collection usable through view/search.
3. Add US3 to enforce canonical torrent reuse and concurrency behavior.
4. Add US4 to manage the shared tag catalog.
5. Add US5 to complete CI/CD, infrastructure, and repeatable validation.
6. Run Polish validation and confirm success criteria.

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup and Foundational phases together.
2. Developer A owns US1 create-video flow.
3. Developer B starts US2 search fixtures and UI after Foundation.
4. Developer C starts US4 admin tag management after Foundation.
5. Developer D owns US5 CI/Terraform/test-mode foundation after Setup.
6. Integrate through contract tests, Playwright tests, and quickstart validation.

---

## Notes

- [P] tasks use different files and have no dependency on incomplete tasks in the same phase.
- Each user story includes independent backend, frontend, and end-to-end test coverage.
- Use `uv add` for backend dependencies; do not edit `apps/backend/pyproject.toml` manually for dependency additions.
- Keep authentication bypass explicit and unavailable in production configuration.
- Keep torrent metadata retrieval behind the provider interface; do not spread provider-specific code into video services or UI.
- Leave unrelated existing changes, such as `.codex/config.toml`, out of Spec Kit commits unless explicitly requested.
