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

- `max_attempts`: jumlah maksimum implementasi dan retry.
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
