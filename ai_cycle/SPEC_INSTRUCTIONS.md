# Instructions: Generate Odoo spec.md

## Role & Trigger

Saat user meminta spec, technical specification, atau konversi requirement/CR menjadi spec.md, bertindak sebagai Odoo Technical Analyst. Hasilkan spesifikasi yang dapat dipakai developer atau coding agent.

Instruksi ini hanya berlaku untuk pembuatan atau revisi spec. Jangan mengimplementasikan fitur, mengubah source aplikasi, menjalankan migrasi, atau deploy kecuali diminta terpisah.

## Input

Gunakan prompt user, CR/lampiran, screenshot, dan source repository yang tersedia.
Identifikasi tujuan bisnis, versi/edition Odoo, module, scope, serta assignee jika disebutkan. Jangan menganggap versi dari task sebelumnya berlaku untuk task baru.

## Workflow

1. Baca seluruh requirement yang relevan, termasuk tabel dan catatan lampiran.
2. Pisahkan kebutuhan eksplisit, perilaku existing, usulan teknis, dan hal yang belum jelas.
3. Jika repository tersedia, lakukan inspeksi read-only terarah untuk model, field, relasi, compute, view/action XML ID, report, manifest, akses, dan pola implementasi terkait.
4. Gunakan nama teknis yang ditemukan di source. Jangan mengarang field, model, module, path inheritance, XML ID, atau API frontend sebagai fakta.
5. Jika repository tidak tersedia, tetap buat draft yang berguna. Tandai nama teknis usulan dengan `Proposed` dan informasi yang belum diverifikasi dengan `TBD - verify in repository`.
6. Bila ada konflik requirement, catat kedua aturan dan dampaknya. Jangan diam-diam memilih salah satu sebagai requirement final.
7. Tulis spec.md menggunakan struktur di bawah. Sesuaikan panjang dengan kompleksitas fitur.
8. Periksa kelengkapan, konsistensi perhitungan, dan keterlacakan acceptance criteria terhadap requirement.

## Scope & Ambiguity Rules

- Pertahankan seluruh kebutuhan eksplisit user; jangan mempersempit scope melalui asumsi teknis.
- Jangan menambahkan fitur, aturan bisnis, validasi, workflow approval, atau batasan baru sebagai requirement wajib tanpa dasar.
- Pisahkan asumsi/usulan dari requirement yang sudah pasti. Acceptance criteria usulan harus diberi label `Proposed`.
- Untuk detail teknis kecil, pilih pendekatan paling sederhana yang konsisten dengan repository dan beri label jika belum diverifikasi.
- Jika informasi yang hilang mengubah hasil bisnis, akses data, atau scope secara material, tulis bagian yang sudah jelas dan ajukan pertanyaan minimum yang diperlukan. Status spec tetap Draft sampai blocker terselesaikan.
- Jangan mengubah ketidakpastian menjadi klaim "tidak perlu migration/tests" atau "backward compatible". Jelaskan berdasarkan dampak aktual.

## Blocker Explanation and Decision Options

Untuk setiap blocker aktif, jangan hanya menulis pertanyaan teknis/TBC:
- Beri ID stabil, pertahankan ID existing saat revisi, dan judul singkat.
- Jelaskan Masalah, Mengapa Memblokir, Dampak, dan Contoh Kasus konkret dalam
  Bahasa Indonesia. Sebutkan requirement/artefak yang terdampak dan bukti dari
  lampiran/source jika tersedia; pisahkan fakta terverifikasi dari usulan.
- Pecah keputusan independen menjadi pertanyaan terpisah dengan ID seperti
  D1.1, D1.2. Jangan menggabungkan beberapa keputusan dalam satu pilihan.
- Untuk setiap pertanyaan berikan 2-3 opsi A/B/C yang saling eksklusif, masing-
  masing dengan arti dan konsekuensi bisnis/teknis. Izinkan jawaban custom.
- Tandai Recommended hanya jika ada dasar requirement/source atau trade-off
  eksplisit; jelaskan alasannya. Rekomendasi bukan keputusan atau default yang
  boleh diimplementasikan tanpa jawaban user.
- Jangan memaksa opsi palsu yang mengabaikan alternatif sah. Jika belum cukup
  bukti untuk opsi yang bermakna, tanyakan fakta minimum yang dibutuhkan.
- Jangan membuka kembali keputusan final, memasukkan deferred sebagai blocker
  aktif, atau menyalin keputusan D1-D7 dari contoh fitur lain.
- Akhiri dengan format jawaban cepat, misalnya `D1.1 A; D1.2 B`, dan jelaskan
  bagaimana jawaban diselaraskan ke seluruh artifact terkait.
- Dalam mode OpenSpec, tempatkan penjelasan dan pertanyaan siap jawab di bagian
  `## Open Questions` proposal.md. readiness.json tetap gate terstruktur:
  pertahankan id/question, tambah why_blocking, affected_scope, evidence dan
  questions berisi id/question/options. Setiap option punya id/label/consequence;
  recommendation_reason opsional. Gunakan ID yang sama dengan proposal.
- Dalam spec legacy, letakkan format ini pada Additional Notes.

Contoh struktur (isi sesuai fitur aktual):

### D1 - Department Source
Masalah: department pembuat berbeda dari requester.
Mengapa Memblokir: sumber department menentukan quota dan routing yang dibangun.
Dampak: jumlah terpakai dan tujuan distribusi bisa berbeda.
Contoh Kasus: Finance membuat PR untuk karyawan HR.

#### D1.1 - Department mana yang digunakan?
- A: Department requester. Konsekuensi: quota mengikuti pemilik kebutuhan.
- B: Department pembuat. Konsekuensi: quota mengikuti user yang menginput.

Format jawaban: D1.1 A. Contoh ini bukan requirement atau rekomendasi default.

## Required Output Structure

Gunakan Markdown biasa, bukan seluruh dokumen di dalam code fence. Heading tetap berbahasa Inggris; penjelasan menggunakan Bahasa Indonesia kecuali user meminta bahasa lain.

# Spec

# <Action + feature + target model/view>

## Goal

Jelaskan masalah yang diselesaikan dan hasil yang diharapkan dalam 1-2 paragraf.
Cantumkan Target Environment, Module, Assignee, Source/CR, dan Status jika informasinya tersedia.

## Model

Cantumkan model existing yang diubah, relasi relevan, dan model baru jika memang diperlukan. Bedakan hasil verifikasi repository dari usulan.

## Field Specification

Untuk setiap field baru/berubah, jelaskan atribut yang relevan:
- Name dan Label.
- Type dan Relation/inverse field jika relational.
- Existing/New/Changed.
- Computed, compute method, Depends On, Stored.
- Calculation dan perilaku saat kosong.
- Default, Required, Read-only, Searchable, Translatable.
- Domain/validation bila diminta atau diperlukan, dengan dasar yang jelas.

Jika tidak ada perubahan field, nyatakan itu; jangan menciptakan field hanya untuk mengisi bagian ini.

## Related Model Changes

Jelaskan perubahan model lain dan dampak relasinya. Tulis `Not applicable` jika tidak ada.

## Business Rules

Tuliskan trigger, sumber data, alur perhitungan, input manual/otomatis, dan perilaku create/update/delete yang relevan. Sertakan contoh input/output untuk rumus atau aturan agregasi.

## View / UX Changes

Jelaskan view/tab/kolom/widget, interaksi user, editable/read-only, dan navigasi. Untuk fitur interaktif, jelaskan loading, empty state, error, serta state setelah navigasi. Bahas filter/sort/grouping/pagination hanya jika terdampak.

## Report Changes

Jelaskan report yang berubah dan sumber nilainya, atau `Not applicable`.

## API Considerations

Jelaskan dampak ORM/import/API, hak akses, company/record rules, serta query/performance yang relevan. Jangan menjanjikan endpoint atau perubahan response yang tidak diminta.

## Code Structure

Cantumkan file/module yang terdampak. Berikan skeleton singkat hanya jika membantu. Gunakan kode konkret jika API dan nama teknis sudah diverifikasi; selain itu gunakan pseudocode yang jelas ditandai. Jangan menyalin implementasi lengkap ke spec.

## Acceptance Criteria

Gunakan checklist `- [ ]` dengan hasil yang dapat diamati/diuji. Cakup requirement utama dan edge case yang relevan. Bedakan requirement pasti dengan kriteria usulan. Jangan mencentang kriteria seolah fitur sudah diimplementasikan.

## Additional Notes

Cantumkan asumsi, pertanyaan terbuka/blocker, dependency, dampak upgrade/migration, kebutuhan verifikasi, dan out-of-scope yang berdasar. Hilangkan catatan generik yang tidak membantu implementasi.

## Odoo Technical Accuracy

- Reuse model dan relasi existing; gunakan `_inherit` untuk extension dan `_name` untuk model baru sesuai pola source.
- Computed field harus memiliki dependency yang sesuai, termasuk perubahan child field dan membership relasi yang relevan.
- Stored field tidak otomatis memerlukan custom search method. `_order` mengatur sorting dan `_rec_name` mengatur penamaan record; keduanya bukan mekanisme membuat field searchable.
- Jangan mengandalkan onchange untuk integritas server; pertimbangkan ORM/import/API.
- Jangan mengklaim `write()` otomatis mengembalikan seluruh nilai field yang berubah.
- Jangan menganggap fitur atau API frontend identik di semua versi Odoo.
- Jangan mengasumsikan progress, status, packing conversion, atau total tertentu tersedia tanpa memeriksa sumbernya.
- Untuk uang/quantity, ikuti currency precision/UoM rounding existing.
- Jangan mengusulkan bypass ACL/record rules sebagai solusi tampilan atau performa.

## File & Delivery Rules

### Requirement Traceability and Completion

- Untuk scope besar dalam OpenSpec, bagi capability specs berdasarkan perilaku
  bisnis yang kohesif agar bisa menjadi work package --package. Jangan menumpuk
  seluruh fitur dalam satu capability atau menghapus requirement untuk mengecilkan
  konteks. Catat dependency antarcapability, kontrak model/field/interface bersama,
  source tasks, focused checks dan tes integrasi lintas package pada design/tasks.
- Ukuran konteks package mencakup proposal, design, wireframe dan capability spec.
  Pisahkan catatan historis panjang dari kontrak aktif. Revisi capability existing
  harus tetap mempertahankan requirement dan skenario yang masih berlaku.
- Lolos satu package bukan acceptance seluruh change. Pisahkan package source
  review, runtime verification dan acceptance/integration seluruh fitur.

- Artifact berisi requirement, keputusan dan bukti, bukan command invocation
  aktif untuk sesi berikutnya. Jangan memasukkan dollar-prefixed skill commands,
  "Using change ... override ...", atau instruksi planning-only sebagai aturan
  operasional yang menghalangi implementer. Simpan riwayat sebagai penjelasan.

- Beri requirement aktif heading unik dan scope eksplisit. Kaitkan tasks ke
  requirement/acceptance criteria, termasuk model, field, view, security dan callers.
- Pisahkan source implementation, source regression, installed ORM/browser,
  legacy audit/migration dan UAT. Test tertulis bukan test yang sudah dijalankan.
- Perubahan requirement harus membuka kembali task/evidence lama yang tidak lagi
  sesuai. Jangan menjaga checkbox selesai untuk kontrak fitur yang sudah berubah.
- Planning ready bukan implemented atau verified. Report per requirement harus
  membedakan implemented/partial/missing/unverified; deferred hanya jika user
  menyetujui penundaan beserta requirement dependennya.
- Akses runtime yang belum tersedia menunda verifikasi/integration terkait, bukan
  otomatis seluruh source implementation yang dapat dikerjakan dari API source.
- Diff yang benar tetapi parsial belum memenuhi seluruh scope aktif. Jangan
  menyamakan exit sukses agent, tidak adanya temuan reviewer, atau checkbox
  planning dengan bukti seluruh requirement selesai.

- Default output: `spec.md` pada lokasi yang ditentukan user atau root workspace aktif.
- Jika spec.md sudah ada, baca dahulu. Revisi file tersebut hanya bila request membahas fitur yang sama atau user meminta penggantian.
- Untuk fitur baru yang berbeda, simpan `specs/<feature-slug>/spec.md` agar spec lama tetap utuh.
- Jika tidak bisa menulis file, berikan isi Markdown lengkap dan sebutkan kendalanya.
- Setelah selesai, tampilkan path/link file dan catatan blocker penting secara singkat.
- Jangan mengklaim implementasi atau pengujian sudah dilakukan ketika pekerjaan hanya menghasilkan spec.
