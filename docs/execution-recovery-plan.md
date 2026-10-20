# Execution Recovery and Progress Plan

Status: Planned. Dokumen ini belum mengubah perilaku command.

## Goal

Mengurangi waktu dan token terbuang ketika implementasi selesai tetapi validation
atau reviewer gagal. User harus mengetahui stage terakhir, penyebab berhenti,
dan cara melanjutkan tanpa mengulang pekerjaan yang masih valid.

Inspirasi lokal: `/opt/project/ruflo/plugins/ruflo-workflows/README.md`, runtime
`v3/@claude-flow/cli/src/mcp-tools/workflow-tools.ts`, serta console/TUI Ruflo.
Adopsi pola persistence dan keterbacaan visual; kompatibilitas runtime Ruflo
dan penghematan token belum dibuktikan melalui benchmark.

## Scope

1. Simpan status sukses/gagal setiap stage secara persisten.
2. Resume dari stage yang belum selesai, dengan pemeriksaan validitas hasil lama.
3. Retry reviewer tanpa memanggil implementer jika implementasi masih valid.
4. Tampilkan alasan berhenti dan hasil setiap stage secara eksplisit.
5. Perbaiki animasi progress terminal dengan referensi Ruflo.

Planner OpenSpec, pilihan Codex/Antigravity, independent Claude review, serta
human acceptance gate tetap menjadi bagian workflow. Tidak membutuhkan swarm,
vector memory, migrasi ke Ruflo, atau dashboard web untuk mencapai scope ini.

## Stage Persistence

- Simpan status `pending`, `running`, `succeeded`, `failed`, `interrupted`, atau
  `needs_human`, beserta waktu mulai/selesai, attempt, log path dan error ringkas.
- Persist transisi sebelum subprocess berjalan dan segera setelah hasil diketahui.
- Gunakan penulisan state atomik agar penghentian mendadak tidak merusak JSON.
- Simpan identitas run, branch/commit, change/spec/rules hash, konfigurasi relevan,
  fingerprint diff termasuk untracked files, dan hasil validation/review.
- Bedakan subprocess timeout, exit nonzero, parse verdict gagal, review meminta
  perubahan, pertanyaan manusia, serta validation yang tidak dikonfigurasi.
- Run tanpa command validation harus tampil `not configured`, bukan mengklaim
  tests lulus. Saat proses terputus, jangan menganggap stage `running` sebagai PASS.
- Cegah dua proses melanjutkan run yang sama secara bersamaan.

## Resume Rules

Semantik `--resume` existing saat ini hanya membawa feedback. Perubahan semantik
harus dijelaskan di help/cheatsheet dan tetap menangani run legacy tanpa stage
state; fallback harus terlihat, bukan diam-diam mengklaim stage recovery.

| Kondisi | Kelanjutan yang direncanakan |
| --- | --- |
| Implementer sukses; validation/reviewer belum mulai | Lewati implementer jika snapshot masih valid |
| Reviewer timeout/exit error/output tidak valid | Ulang reviewer jika implementation dan validation masih valid |
| Reviewer CHANGES_REQUIRED | Jalankan implementer dengan feedback, kemudian validation dan review ulang |
| Reviewer NEEDS_HUMAN | Tunggu revisi planning; hitung ulang stage mana yang invalid |
| Source berubah setelah validation | Jalankan validation dan review ulang; evaluasi ulang kesesuaian implementasi |
| Spec/rules berubah | Jangan memakai hasil review lama; jalankan implementer terhadap requirement terbaru |
| Validation config berubah | Jalankan validation dan review ulang |
| Model/prompt reviewer berubah | Ulang review; tidak otomatis mengulang implementasi |
| Run lama tidak punya snapshot/state | Jelaskan fallback ke feedback-only/fresh run |

Status dan alasan pemilihan stage harus tampil sebelum menjalankan agent.
Task completion/evidence OpenSpec mengikuti normalisasi existing; perubahan
requirement atau isi task tetap harus terdeteksi. Detail fingerprint dan migrasi
state ditentukan setelah membaca runner/resume existing saat implementasi.

## Reviewer Retry

- Bedakan kegagalan infrastruktur dari verdict substantif; timeout bukan BLOCKER
  dan bukan SPEC_QUESTION.
- Pertahankan log tiap percobaan; jangan menimpa bukti reviewer sebelumnya.
- Sediakan jalur menjalankan ulang review dari run tertentu; nama opsi/command
  final ditentukan pada implementasi dan harus menolak snapshot yang kedaluwarsa.
- Retry harus terbatas dan menampilkan jumlah percobaan. Jangan retry otomatis
  tanpa batas atau memakai output parsial sebagai PASS.
- Perubahan model reviewer dapat dipakai untuk retry tanpa mengubah source.

## Progress and Animation

Gunakan gaya console Ruflo sebagai referensi: transisi stage yang jelas, timer,
status agent, dan informasi ringkas yang mudah dipindai. Tetap gunakan Rich dan
komponen terminal existing jika mencukupi; tidak perlu dependency animasi baru.

- Spinner hanya bergerak selama stage benar-benar aktif; sukses/gagal/interrupted
  menghentikannya dan meninggalkan tampilan final yang benar.
- Pisahkan elapsed time, waktu sejak output terakhir, dan sisa timeout bila tersedia.
- Tampilkan implementer terpilih, stage/attempt, log path, output terakhir dan
  jumlah retry. Output/log diperlakukan sebagai literal, bukan Rich markup.
- Saat output dibuffer, tampilkan `waiting for output` tanpa mengklaim agent idle
  atau hang; heartbeat UI tidak membuktikan model sedang membuat progres.
- Gunakan perubahan warna/status dan animasi transisi ringan; jangan memakai
  persentase fiktif atau progress bar yang naik berdasarkan waktu saja.
- Layout stabil pada terminal sempit; path panjang tidak membuat tabel berulang
  atau menutupi error. Hindari mencetak ulang seluruh tabel sebagai log scroll.
- Piped output/non-TTY memakai baris status statis tanpa spinner/escape sequence.
- Setelah gagal, tampilkan alasan serta command kelanjutan konkret dengan change
  dan run yang benar. Jangan menyarankan fresh implementation untuk setiap error.

## Implementation Order

1. State stage, atomic persistence, snapshot/fingerprint, dan proteksi concurrent run.
2. Pemilihan stage resume dan retry reviewer berdasarkan hasil yang masih valid.
3. Integrasi error reporting, status/history/logs, serta command recovery.
4. Animasi dan tampilan final yang bersumber dari state yang sama.
5. Update README, cheatsheet, workflow docs, dan bukti pengujian.

## Acceptance Criteria

- [ ] Reviewer timeout setelah implementasi sukses dapat dilanjutkan tanpa panggilan implementer kedua.
- [ ] CHANGES_REQUIRED tetap menjalankan perbaikan dan validation sebelum review ulang.
- [ ] Perubahan source/untracked/spec/rules/config menginvalidasi hasil stage yang relevan.
- [ ] SIGINT/crash tidak menghasilkan PASS palsu dan log/state yang tersimpan dapat dipakai untuk recovery.
- [ ] Dua proses tidak bisa mengeksekusi stage recovery yang sama secara bersamaan.
- [ ] Run lama tetap terbaca dan fallback terlihat eksplisit.
- [ ] History dan layar akhir menunjukkan stage terakhir, alasan berhenti, dan langkah berikutnya.
- [ ] Semua retry memiliki log terpisah dan batas percobaan.
- [ ] Animasi berhenti saat subprocess berakhir; layout terminal sempit dan output non-TTY tetap terbaca.
- [ ] Uji subprocess stub untuk success/timeout/nonzero/interrupt dan pastikan jumlah panggilan implementer/reviewer sesuai.
- [ ] Catat perbandingan jumlah panggilan agent pada kasus timeout sebelum/sesudah; jangan mengklaim penghematan token tanpa pengukuran.

## Delivery Notes

Tidak ada implementasi, live agent run, atau perubahan project Odoo dalam plan
ini. Pause/resume sesi internal Codex/Antigravity bukan target: recovery berada
di batas stage orchestrator. Stage yang terputus di tengah implementasi mungkin
tetap memerlukan panggilan implementer baru untuk menilai partial changes.
