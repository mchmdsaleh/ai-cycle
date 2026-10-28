# OpenSpec + AI Cycle

OpenSpec mengelola requirement, design, wireframe, tasks, dan archive. AI Cycle
menjalankan implementer (default Codex, opsional Antigravity), validation,
Claude independent review, dan retry.
Source of truth untuk mode ini adalah folder change, bukan `.ai-cycle/spec.md`.

## Setup

```bash
npm install -g @fission-ai/openspec
cd /path/to/odoo-repository
ai-cycle init
```

OpenSpec saat ini membutuhkan Node.js 20.19+. Pada penggunaan pertama `--change`,
AI Cycle menjalankan `openspec init --tools codex` jika openspec/ belum ada,
menyalin schema `odoo-spec-driven` tanpa menimpa custom schema existing, dan
membuat change melalui CLI OpenSpec. Tidak perlu memilih model baru: planner
tetap memakai konfigurasi Codex existing. Planning memakai sandbox read-only;
AI Cycle menyimpan output terstruktur sesudah validasi.

## Use Case: Mandiri Payment CSV

### Completion Gate

For large changes, select one capability per run with `--package <capability>`.
Example: `ai-cycle run --change c1 --package purchase-request-rfq --implementer agy --allow-dirty`.
Only that capability and shared proposal/design/wireframe context are sent to
the implementer/reviewer; task history and unrelated capability text are omitted.
The full master inventory remains recorded separately. Context over 96,000 bytes
requires an explicit split, not truncation. Dependencies must still be inspected.

`package_validation_commands` can map package names to focused command lists;
otherwise global validation commands apply. Resume is isolated by package,
branch and master spec hash. A completed package produces package-checkpoint.json
with source hashes and a PACKAGE REVIEWED - INTEGRATION PENDING result. Pending
runtime checks remain pending. Checkpoints do not auto-approve other packages
or the full change: run global integration checks/full-change review afterwards.

Run menginventarisasi seluruh heading `### Requirement:` dengan ID berbentuk
`specs/<capability>/spec.md::<title>`. ID/nama heading harus unik. Snapshot spec
dan inventory disimpan di run. Setiap attempt meminta `completion.json`:

```json
{"requirements":[{"id":"specs/payment-export/spec.md::Export payments","source_status":"implemented","reason":"Serializer dan action tersedia","verification_status":"pending","verification_reason":"Source checks passed; ORM/browser belum dijalankan","evidence":[{"path":"my_module/models/export.py","line":1,"end_line":20}]}]}
```

Setiap requirement aktif wajib masuk tepat sekali; tidak boleh hilang, duplikat
atau dipindahkan implementer ke deferred. Source reference harus ada di repo,
line valid, bukan planning/config/log. Runner membaca excerpt aktual, bukan hanya
percaya klaim agent. Independent reviewer menerima semua ID dan source evidence
serta actual validation output dan wajib memberi coverage seluruh requirement.
Partial/missing/unverified source memicu feedback/retry sampai batas attempt.
Tidak ada extra model call untuk pemeriksaan struktur completion report.
Setiap panggilan implementer mendapat `target.json` dengan satu ID requirement
wajib. Runner memilih missing sebelum partial/unverified atau source tanpa
checkpoint. Pengerjaan dependency diperbolehkan, tetapi cleanup unrelated tidak
menyelesaikan target. Jika target belum implemented dengan evidence valid, runner
langsung berhenti, menyimpan alasan dan resolution_options agent dalam
`target-result.json`, dan tidak menghabiskan attempt berikutnya. Target selesai
membuka target berikutnya selama budget max_attempts masih tersedia.
Budget habis dengan gap tersisa tetap PARTIAL, bukan full PASS. `--resume` memakai
checkpoint yang kompatibel untuk melanjutkan; jangan mengulang blocker yang sama
tanpa keputusan, izin atau perbaikan sumber yang dibutuhkan.

`work-items.json` mengelompokkan requirement pending/source-complete per capability.
`checkpoint.json` membawa report terakhir yang lolos pemeriksaan struktur/evidence
ke attempt berikutnya, termasuk resume branch/spec yang sama. Dalam targeted run,
report cukup memuat target dan requirement yang benar-benar diperiksa; runner
menggabungkan baris itu dengan checkpoint dan menjaga sisanya tetap queued.
Tanpa target, report wajib memuat seluruh inventory. Agent tetap memeriksa
dependency dan mengerjakan satu kelompok. Requirement selesai bukan dihapus dari scope; source yang
terpengaruh perubahan tetap harus diperiksa ulang. Ini instruksi kerja agent,
bukan scheduler dependency otomatis atau jaminan agent pasti menyimpan checkpoint.

`source_status` hanya menilai kelengkapan kode. Source lengkap dengan runtime
belum tersedia memakai implemented + verification_status pending, bukan partial
hanya karena ORM/browser belum diuji. Source sungguh belum lengkap tetap partial
atau missing. `verification-pending.json` mencatat verifikasi implementer yang
belum passed; hasil final juga memasukkan pending dari reviewer independen.
Report legacy `status` diterima tanpa otomatis mengubah partial menjadi complete.

Report menyatakan source completeness, bukan lulus test. Checklist yang masih
pending, validasi yang belum dikonfigurasi dan runtime yang belum diuji tetap
menghasilkan VERIFICATION PENDING setelah source review; bukan acceptance.
Planning readiness tetap terpisah. Exit0, prepared tests dan source mocks tidak
membuktikan ORM/browser/migration. Bila tidak ada diff, gate tetap dapat memeriksa
source yang sudah committed; tanpa source evidence tidak ada PASS otomatis.

Schema proyek lama tidak ditimpa otomatis. Prompt runner tetap mengirim kontrak
completion terbaru, dan template/schema C1 sudah diselaraskan secara terarah.
Nama stage implementer done berarti subprocess selesai; Scope Coverage adalah
pemeriksaan kelengkapan source berikutnya. `result.json` menyimpan status dan
alasan final. Run legacy yang belum memiliki hasil eksplisit tetap unverified.

### 1. Requirement dari CR atau wireframe

```bash
ai-cycle spec "Generate payment CSV Bank Mandiri" \
  --input ./docs/mandiri.pdf --change mandiri-payment-export
```

Output:

```text
openspec/changes/mandiri-payment-export/
  .openspec.yaml
  proposal.md
  specs/<capability>/spec.md
  design.md
  wireframe.md
  tasks.md
  readiness.json
```

| Artifact | Isi |
| --- | --- |
| proposal.md | Tujuan bisnis, scope, capability, keputusan, pertanyaan terbuka |
| specs/.../spec.md | Requirement SHALL/MUST dan scenario WHEN/THEN; delta terhadap spec existing |
| design.md | Versi Odoo, model/field/XML ID terverifikasi, ACL, compute, migration, acceptance criteria |
| wireframe.md | Layout teks, navigasi, loading, empty, error dan success; Not applicable jika tidak ada UX |
| tasks.md | Checklist implementasi dan verifikasi per task |
| readiness.json | Status draft/ready dan daftar blocker bisnis |

Instruksi Odoo Technical Analyst existing tetap disertakan. Tidak boleh mengarang
nama teknis, mempersempit scope, atau memasukkan keputusan bisnis tanpa dasar.
Wireframe mengikuti lampiran dan pola UI existing; schema default memakai layout
teks Markdown. Sesuaikan template/rules jika perlu format wireframe khusus.

### 2. Jawab blocker dan review planning

Contoh pertanyaan: status payment eligible dan sumber nama rekening D2.

```bash
ai-cycle spec "Keputusan: hanya In Process. D2 memakai Nama Rekening; jika kosong harus error tanpa menyimpan snapshot." \
  --change mandiri-payment-export
```

Agent membaca artifact existing, merevisi semua artifact terkait, mempertahankan
requirement, dan menghapus pertanyaan yang sudah resolved. Nama status dan field
teknis harus diverifikasi dari source. Contoh scenario:

```markdown
### Requirement: Beneficiary account name
The system SHALL reject export when the selected beneficiary account name is empty.

#### Scenario: Empty beneficiary name
- **WHEN** user generates an export with an empty beneficiary account name
- **THEN** export is rejected and identifies the affected payment
- **AND** no export snapshot is saved
```

Periksa seluruh artifact sebelum run. readiness.json bukan bukti persetujuan
manusia: menjalankan run setelah review adalah keputusan untuk implementasi.

```json
{"status": "ready", "blockers": []}
```

Status draft atau blocker yang belum kosong menghentikan cycle sebelum agent.
Output planner yang tidak valid tidak mengganti artifact lama. OpenSpec strict
validation memeriksa struktur requirement, bukan kebenaran keputusan bisnis.

### 3. Implementasi dan independent review

```bash
ai-cycle run --change mandiri-payment-export --allow-dirty
```

Implementer default adalah Codex. Pemilihan mengikuti prioritas:
`--implementer` > `implementer` pada `.ai-cycle/config.json` > `codex`.
Untuk memakai Antigravity pada satu run:

```bash
ai-cycle run --change mandiri-payment-export --implementer agy --allow-dirty
```

Untuk permanen, tambahkan `"implementer": "agy"` ke config JSON existing tanpa
menghapus setting lain. Run tanpa flag selanjutnya memakai Antigravity. Untuk
sementara kembali ke Codex:

```bash
ai-cycle run --change mandiri-payment-export --implementer codex --allow-dirty
```

CLI `agy` harus terpasang dan login; model mengikuti konfigurasi Antigravity.
Runner memakai print mode, accept-edits, dan sandbox tanpa bypass permission.
Untuk headless, settings global agy dapat memakai toolPermission
proceed-in-sandbox: command dalam sandbox tidak meminta approval; di luar tetap
meminta approval. Explicit deny/ask tetap berlaku. Jika sandbox tidak tersedia,
CLI dapat meminta review. Mode auto tidak tersedia untuk semua akun.
Planner spec tetap Codex dan reviewer tetap Claude. Postmortem opsional juga
memerlukan Codex. Pilihan ini berlaku pula pada legacy run tanpa `--change`;
log keduanya tetap `implementer.txt`.

Implementer terpilih membaca semua artifact dan mengerjakan tasks. Task hanya dicentang setelah
verifikasinya berhasil. Acceptance criteria tidak otomatis dianggap lulus.
Validation menggunakan `.ai-cycle/config.json`; daftar kosong berarti tidak ada
validasi otomatis. Claude memeriksa diff terhadap artifact yang sama.
Cycle berhenti jika implementer mengubah planning selain checkbox tasks dan
catatan pada bagian akhir `Implementation evidence`.

| Hasil | Tindakan |
| --- | --- |
| PASS | Review perilaku, git diff, lalu UAT |
| CHANGES_REQUIRED | Retry otomatis sampai max_attempts; kemudian baca feedback |
| NEEDS_HUMAN | Baca spec-questions.txt, jawab lewat spec --change, lalu run lagi |

Untuk kegagalan dengan requirement yang sama:

```bash
ai-cycle run --change mandiri-payment-export --resume --allow-dirty
```

Resume memakai feedback compatible, bukan melanjutkan sesi agent. Perubahan
checkbox tasks tidak mengubah hash planning; perubahan requirement/design
mengubah hash dan memulai fresh run. OpenSpec tidak menghilangkan latency model,
timeout, atau kebutuhan environment Odoo/Playwright yang benar.

### 4. Perubahan scope

```bash
ai-cycle spec "Keputusan baru: payment Paid juga eligible; pertahankan requirement lainnya." \
  --change mandiri-payment-export
ai-cycle run --change mandiri-payment-export --allow-dirty
```

Gunakan nama change yang sama untuk revisi fitur yang sama. Gunakan nama baru
untuk fitur berbeda. Legacy `ai-cycle spec` tanpa --change tetap menghasilkan
.ai-cycle/spec.md; legacy `ai-cycle run` tetap membaca file tersebut.

### 5. UAT dan archive

```bash
openspec status --change mandiri-payment-export
openspec validate mandiri-payment-export --strict
# Setelah human review, runtime/browser tests dan UAT terkait selesai:
openspec archive mandiri-payment-export
```

Archive menggabungkan delta ke openspec/specs/ dan menyimpan change di archive.
AI Cycle tidak melakukan archive, commit, push, deployment atau approval bank.
Jangan archive jika verifikasi wajib masih belum selesai. Task kecil tetap punya
artifact yang ringkas; tidak perlu wireframe rumit untuk readonly field.

Commit openspec/schemas/, openspec/specs/, openspec/changes/ dan konfigurasi
workflow bersama source. Hindari memasukkan dokumen binary/vendor unrelated ke
diff reviewer. `.ai-cycle/runs/` berisi log dan perlu di-ignore.
