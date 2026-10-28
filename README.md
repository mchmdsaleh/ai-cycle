# ai-cycle

Orchestrator untuk workflow coding berbasis agent:

1. Codex membuat atau memperbaiki implementasi.
2. Perintah validasi dijalankan secara deterministik.
3. Claude Code me-review diff.
4. Developer memeriksa hasil sebelum commit atau push.

`ai-cycle` tidak melakukan commit atau push otomatis.

## Install

```bash
cd /opt/project/ai-cycle
pipx install -e .
```

Instalasi editable membuat perubahan source langsung dipakai oleh command
`ai-cycle` tanpa reinstall. Pastikan `git`, `codex`, `claude`, dan `bash`
tersedia di `PATH`.

## Quick Start

Jalankan dari root repository Git yang akan dikerjakan:

```bash
ai-cycle init
ai-cycle spec "Buat fitur hierarchy subtask"
cat .ai-cycle/spec.md
ai-cycle run --max-attempts 1
```

`ai-cycle init` membuat:

- `.ai-cycle/spec.md`: task dan acceptance criteria aktif.
- `.ai-cycle/RULES.md`: aturan permanen untuk implementor dan reviewer.
- `.ai-cycle/config.json`: jumlah attempt, validasi, base branch, dan model.
- `.ai-cycle/runs/`: log setiap cycle.

## Generate Spec

```bash
ai-cycle spec "Buat fitur hierarchy subtask"
ai-cycle spec --input ./docs/wireframe.pdf
ai-cycle spec "Ikuti CR terlampir" --input ./docs/change-request.pdf
```

Codex berjalan dalam plan mode dengan sandbox read-only. Agent boleh
menelusuri repository dan membaca lampiran, tetapi tidak boleh mengubah source.
Setiap spec mengikuti instruksi Odoo Technical Analyst di
`ai_cycle/SPEC_INSTRUCTIONS.md`.

Hasil baru ditulis ke `.ai-cycle/spec.md` setelah agent sukses. Periksa semua
`TBD`, asumsi, open question, dan acceptance criteria sebelum menjalankan cycle.

## Run Cycle

```bash
ai-cycle run                         # fresh cycle
ai-cycle run --max-attempts 1        # batasi biaya dan waktu
ai-cycle run --allow-dirty           # izinkan perubahan lokal existing
ai-cycle run --resume --allow-dirty  # gunakan feedback terminal sebelumnya
```

Secara default working tree harus bersih. Gunakan `--allow-dirty` hanya bila
perubahan lokal memang ingin ikut diimplementasikan dan direview.

`--resume` mencari feedback gagal terakhir dengan branch dan hash spec yang
sama. Opsi ini bukan melanjutkan sesi agent yang lama.

## Configuration

Contoh `.ai-cycle/config.json`:

```json
{
  "max_attempts": 2,
  "base_branch": null,
  "review_model": "kr/claude-opus-5",
  "validation_commands": [
    "python -m unittest"
  ],
  "postmortem": false
}
```

- `max_attempts`: batas panggilan implementer dalam satu run. Pada OpenSpec, setiap panggilan mendapat target requirement wajib. Target belum selesai menghentikan run langsung, tanpa menunggu attempt berikutnya; target selesai membuka pekerjaan berikutnya selama budget masih ada. Panggilan manual `--resume` tetap memulai budget baru.
- `base_branch`: `null` me-review perubahan lokal terhadap `HEAD`. Isi branch
  hanya jika committed branch history memang harus ikut direview.
- `review_model`: model Claude reviewer. Environment variable
  `AI_CYCLE_REVIEW_MODEL` memiliki prioritas lebih tinggi.
- `validation_commands`: dijalankan berurutan sebelum reviewer. Array kosong
  berarti tidak ada validasi otomatis.
- `postmortem`: bila `true`, agent tambahan mengusulkan reusable rule setelah
  cycle gagal. Default `false` untuk menghemat waktu dan token.

Diff review dibatasi 1 MB. Artefak `.ai-cycle/` tidak dimasukkan ke diff.

## Results

### Large Changes: Work Packages

Use one existing OpenSpec capability as the package name (the directory under
`openspec/changes/<change>/specs/`):

```bash
ai-cycle run --change c1 --package purchase-request-rfq \
  --implementer agy --allow-dirty --max-attempts 2
```

The implementer and reviewer receive that capability plus shared proposal,
design and wireframe constraints, not every capability or the full task history.
Context is capped at 96,000 bytes; oversized packages fail with a split request,
never silent truncation. Read dependency contracts before implementing; this is
explicit package selection, not an automatic dependency scheduler.

`requirements.json` covers the package; `global-requirements.json` preserves the
master inventory. `--resume` matches branch, master spec hash AND package, so
feedback from another package or a full-change run cannot leak into this scope.
Optional `package_validation_commands` maps capability names to focused command
lists; when absent, normal `validation_commands` still run.

After source coverage, configured validation and independent review, the result
is **PACKAGE REVIEWED - INTEGRATION PENDING**, never full-change PASS. The
attempt's `package-checkpoint.json` stores report evidence and source-file hashes;
runtime verification can still be pending. Recheck after shared source changes.
Package checkpoints are not automatically combined into a full acceptance result.
Run the normal full-change cycle and integration tests after all packages are
reviewed. Selecting a package does not defer or remove other requirements.

OpenSpec run mempunyai **Scope Coverage** gate: setiap heading Requirement
diinventarisasi dan implementer wajib menulis `attempt-N/completion.json` dengan
`source_status` implemented/partial/missing/unverified serta referensi file/line
source. `verification_status` passed/failed/pending terpisah: source lengkap yang
belum diuji runtime tidak perlu ditulis ulang, tetapi tetap bukan full PASS.
Report lama dengan `status` masih diterima sebagai status source; tidak dinaikkan
otomatis dari partial ke implemented.

Setiap attempt mendapat `work-items.json` (antrean per capability),
`checkpoint.json` (klaim source/evidence terakhir), dan `target.json`. Saat ada
target, implementer melaporkan target itu dan requirement terkait yang benar-
benar diaudit; runner menggabungkannya dengan checkpoint dan mempertahankan yang
lain sebagai antrean. Laporan penuh diwajibkan setelah semua target selesai.
`--resume` memakai report attempt
terakhir dari run branch/spec yang kompatibel, jika struktur/evidence valid.
Checkpoint adalah petunjuk, bukan bukti correctness atau stage resume otomatis.
Semua source tetap wajib masuk pemeriksaan akhir dan review independen.
Implementer harus memakai `checkpoint.json` attempt saat ini sebagai baseline,
bukan menyalin report run lama. Penurunan status source wajib menyertakan
`reassessment: {"previous_status": "implemented", "reason": "temuan source baru dan mengapa klaim sebelumnya salah"}`
pada row terkait, beserta evidence source yang valid. Checker menolak report
dengan penurunan tanpa penjelasan tersebut. Saat resume, report yang ditolak
tidak menggantikan baseline: runner memeriksa ulang referensi source dari incoming
checkpoint attempt tersebut. Ini menjaga kontinuitas klaim progress, bukan
jaminan correctness atau larangan menurunkan status saat ditemukan bug nyata.
Runner menyimpan `target.json` untuk tiap attempt dan menampilkan Required target.
Prioritas: missing, partial, unverified, lalu requirement tanpa checkpoint; urutan
inventory dipakai untuk prioritas yang sama. Dependencies harus diperiksa agent,
bukan dipilih otomatis oleh dependency graph. Target yang selesai boleh mencakup
perbaikan dependency, tetapi cleanup lain tidak menggantikan penyelesaian target.
Jika target tetap belum implemented dengan evidence valid, run langsung berhenti
PARTIAL setelah seluruh `--max-attempts` dipakai. Tiap retry mempertahankan target
yang sama, meneruskan feedback dan checkpoint, lalu menyimpan `target-result.json`
berisi alasan serta opsi resolusi terakhir yang dilaporkan agent. Jika budget habis
setelah target berhasil tetapi masih ada gap lain, hasil tetap PARTIAL dan resume
dapat melanjutkan gap berikutnya. Angka coverage tetap laporan agent, bukan bukti
correctness; validation dan independent review tetap wajib setelah source lengkap.
Runner memvalidasi seluruh ID/range, lalu mengirim source excerpts dan hasil
validation ke reviewer independen. Reviewer wajib melaporkan coverage seluruh
requirement termasuk source yang tidak berubah. Diff yang benar tetapi parsial
tidak cukup untuk PASS; gap masuk feedback retry tanpa mengubah requirement.

`PARTIAL` berarti source belum lengkap. `VERIFICATION PENDING` berarti source
review lolos tetapi verifikasi requirement pending/failed, tasks masih unchecked
atau validation belum dikonfigurasi. Reviewer dapat mempertahankan pending
meskipun implementer mengklaim passed.
Keduanya bukan full acceptance. Exit sukses agent hanya berarti subprocess
selesai. `result.json` menyimpan hasil final; history legacy tanpa hasil eksplisit
ditandai unverified, bukan PASS dari tidak adanya feedback. Evidence dan review
tetap perlu diperiksa manusia; ini bukan bukti matematis correctness.

- `PASS`: validasi dan review lolos; periksa aplikasi serta `git diff`.
- `CHANGES_REQUIRED`: baca `feedback.txt`, lalu jalankan ulang dengan
  `--resume --allow-dirty` bila feedback masih kompatibel.
- `NEEDS_HUMAN`: baca `spec-questions.txt`, perjelas spec, lalu mulai cycle baru.
- Validation failure: baca `validation.txt` sebelum retry.

## Logs

```bash
ai-cycle status
ai-cycle logs <run-id>
tail -f .ai-cycle/runs/<run-id>/attempt-1/implementer.txt
cat .ai-cycle/runs/<run-id>/attempt-1/review-claude.txt
cat .ai-cycle/runs/<run-id>/attempt-1/validation.txt
```

Progress UI menampilkan stage, durasi, lokasi log, dan output terakhir. Claude
print mode dapat diam sampai respons selesai; reviewer dihentikan setelah 120
detik jika tidak selesai.

## Worktrees

```bash
ai-cycle worktree add <name> --base main
ai-cycle worktree add <name> --existing
ai-cycle worktree list
ai-cycle worktree remove <name>
```

Gunakan worktree untuk menjalankan task terpisah tanpa mencampur perubahan.

Untuk ringkasan command langsung di terminal:

```bash
ai-cycle cheatsheet
```
## OpenSpec Workflow

Implementer dapat dipilih dengan `ai-cycle run --implementer agy` atau setting
`"implementer": "agy"` pada `.ai-cycle/config.json`. Default tetap `codex`;
flag CLI mengalahkan config. Contoh C4:

```bash
ai-cycle run --change c4 --implementer agy --allow-dirty
```

Antigravity memerlukan CLI `agy` yang sudah login. AI Cycle memakai print mode,
`accept-edits`, dan sandbox tanpa bypass permission. Untuk command headless,
atur `"toolPermission": "proceed-in-sandbox"` pada
`~/.gemini/antigravity-cli/settings.json`, atau gunakan allow-rules command
terbatas. Policy ini global untuk agy: sandboxed command berjalan tanpa prompt,
command di luar sandbox tetap meminta approval. Jika sandbox tidak tersedia,
CLI dapat kembali meminta review; AI Cycle tidak menonaktifkan pengaman itu.
Mode auto tidak tersedia untuk semua akun, sehingga bukan default integrasi.
Explicit deny/ask rules tetap berlaku. Model mengikuti konfigurasi
Antigravity. Spec planner tetap memerlukan Codex, reviewer tetap Claude; jika
postmortem diaktifkan, Codex juga diperlukan. Log tetap `implementer.txt`.
Prompt lengkap disimpan di `attempt-N/implementer-prompt.md`; `--print=...`
berisi instruksi pendek untuk membaca file itu. Ini menghindari flag parsing
ambigu dan batas panjang argumen OS untuk spec besar; prompt tidak dikirim stdin.
Headless Antigravity tidak dapat meminta izin command secara interaktif. Jika log
menyebut command auto-denied, atur hanya command yang diperlukan melalui
`permissions.allow` di settings Antigravity, atau gunakan `--implementer codex`.
AI Cycle tidak mengaktifkan bypass permission. Pesan `jetski: no output produced`
dianggap kegagalan implementer walaupun CLI mengembalikan exit code 0.

Prioritas pemilihan: `--implementer` > `implementer` di config > `codex`.
Tanpa flag maupun config, implementasi tetap menggunakan Codex. Untuk memilih
Antigravity secara permanen, tambahkan `"implementer": "agy"` ke JSON existing
tanpa menghapus setting lainnya. Setelah itu run biasa memakai Antigravity;
override satu run kembali ke Codex dengan:

```bash
ai-cycle run --change c4 --implementer codex --allow-dirty
```

Opsi yang sama berlaku untuk legacy `ai-cycle run` tanpa `--change`.

Panduan lengkap dan contoh Mandiri CSV tersedia di [OpenSpec + AI Cycle](docs/openspec-workflow.md).

```bash
npm install -g @fission-ai/openspec
ai-cycle spec "Generate payment CSV Mandiri" --input ./docs/mandiri.pdf --change mandiri-payment-export
ai-cycle spec "Jawaban blocker: ..." --change mandiri-payment-export
ai-cycle run --change mandiri-payment-export --allow-dirty
```

`--change` memakai artifact OpenSpec sebagai source of truth. Schema Odoo,
wireframe, tasks, dan readiness dibuat pada penggunaan pertama. Draft/blockers
menghentikan implementasi sebelum agent berjalan. Command tanpa `--change`
tetap memakai `.ai-cycle/spec.md`. Archive dilakukan manual setelah review/UAT.

## Blocker Questions

Saat planning menemukan blocker, `proposal.md` bagian Open Questions menjelaskan
masalah, alasan memblokir, dampak, contoh, dan pertanyaan ber-ID dengan opsi serta
konsekuensinya. Rekomendasi harus beralasan dan tetap memerlukan keputusan user.
Contoh menjawab: `ai-cycle spec "Jawaban: D1.1 A; D1.2 B" --change nama-fitur`.
ID mengikuti artifact aktual, bukan selalu D1.1. `ai-cycle spec` menampilkan
bagian pertanyaan jika ada blocker; JSON lengkap tetap di readiness.json.

## Planned Improvements

Rencana stage persistence, resume tanpa mengulang implementasi, retry reviewer,
alasan berhenti yang eksplisit, dan animasi progress terinspirasi Ruflo tersedia
di [Execution Recovery and Progress Plan](docs/execution-recovery-plan.md).
Fitur pada dokumen tersebut masih berstatus planned.
