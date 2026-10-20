# Diskusi: Database per Worktree

## Pain Point

Selain git worktree untuk kerja paralel di beberapa feature/branch, ada masalah
database saat pindah context:

- Kode bisa langsung ganti branch/worktree secara instan.
- Database tidak punya konsep branch. Kalau db existing sudah di-upgrade oleh
  feature sebelumnya (field baru, migrasi data, dll), lalu kita pindah ke
  branch baru yang base-nya `main` (belum ada feature tersebut), kode dan
  schema db jadi tidak sinkron.

## Opsi Solusi

1. **Satu DB per worktree**
   Tiap worktree punya db sendiri, dinamai sesuai nama worktree/branch
   (misal `ics19_task-691-bupot`). Robust untuk kerja paralel, tapi butuh cara
   cepat bikin db "bersih" (baseline dari `main`) tiap kali worktree baru
   dibuat — kalau tidak, tiap worktree mulai dari db kosong.

2. **Postgres `CREATE DATABASE ... TEMPLATE`**
   Clone database dalam hitungan detik dari template db (baseline), jauh
   lebih cepat dari dump/restore untuk db besar.
   ```sql
   CREATE DATABASE ics19_task_691 TEMPLATE ics19_baseline;
   ```
   Syarat: `ics19_baseline` tidak boleh punya koneksi aktif saat di-clone.

3. **Snapshot manual via `pg_dump` / `pg_restore`**
   Lebih portable antar device, tapi lambat untuk db besar dan makan disk
   kalau banyak snapshot disimpan.

### Rekomendasi

Kombinasi opsi 1 + 2, diintegrasikan ke `ai-cycle worktree add` / `remove`
yang sudah ada di package `/opt/project/ai-cycle/`:

- `ai-cycle worktree add <name>`:
  1. Bikin git worktree (sudah ada).
  2. Baca `baseline_db` dari config repo asal (`.ai-cycle/config.json` di
     repo utama, bukan yang di-copy ke worktree).
  3. `CREATE DATABASE <name> TEMPLATE <baseline>`.
  4. Copy `.ai-cycle/` template + suntik `db_name` yang baru-dibuat ke
     config **milik worktree tersebut**.
  5. Kalau repo punya file config yang menyimpan `db_name`, copy & rewrite
     juga (lihat catatan di bawah — untuk ics-19 ini masih perlu dikonfirmasi).

- `ai-cycle worktree remove <name>`: sekalian `DROP DATABASE <name>`.

- Baseline db (`ics19_baseline`) di-refresh manual tiap kali `main` punya
  perubahan schema besar. Perlu drop-recreate baseline (`CREATE OR REPLACE`
  tidak berlaku untuk database, jadi baseline harus di-drop lalu dibuat ulang
  dari sumber yang sudah di-upgrade).

### Tradeoff

Menambah state yang harus dijaga manual: baseline db harus rutin di-sync dari
`main`. Kalau lupa, worktree baru mulai dari titik lama. Tapi ini lebih aman
dibanding semua worktree share satu db yang gampang bentrok schema.

## Bagaimana Agent (Codex/Claude/Copilot) Tahu Nama DB Baseline / DB Aktif

Tiga lapis nama yang perlu dipisah:

1. **`baseline_db`** — nama db template acuan (misal `ics19_baseline`),
   disimpan di `.ai-cycle/config.json` milik **repo utama**, bukan yang
   di-copy ke tiap worktree. Semua worktree tahu harus clone dari mana.

2. **`db_name`** — unik per worktree, auto-generate saat
   `ai-cycle worktree add <name>` (misal `ics19_<name>`). Ditulis ke
   `.ai-cycle/config.json` milik worktree tersebut (config per-worktree
   beda-beda sesuai db masing-masing).

3. **Cara agent membaca `db_name` saat eksekusi:**
   - **Env var** — saat `ai-cycle run` dipanggil, baca `db_name` dari
     `.ai-cycle/config.json`, export sebagai env var (misal
     `AI_CYCLE_DB_NAME`) sebelum spawn subprocess Codex/validation_commands.
     Semua child process otomatis dapat tanpa perlu baca file sendiri.
   - **Rewrite config Odoo** — kalau repo pakai file config yang menyimpan
     `db_name` langsung (`odoo.conf`-style), `worktree add` sekaligus
     menulis ulang baris itu ke db yang baru dibuat. Perlu karena Codex
     biasanya jalanin `odoo-bin` yang baca dari file config, bukan dari env
     var kita.

Urutan lengkap saat `worktree add`:
1. Bikin git worktree.
2. Baca `baseline_db` dari config repo asal.
3. `CREATE DATABASE <name> TEMPLATE <baseline>`.
4. Copy `.ai-cycle/` template, suntik `db_name` baru.
5. Kalau ada file config db (odoo.conf-style), copy & rewrite `db_name`-nya.

## Temuan soal ics-19 (Belum Final)

- Config path project ada di `/opt/project/config/ics19conf/`, isinya
  beberapa file `.conf` (`ics.conf`, `ics_pub.conf`, `ics_unittest.conf`).
- Isi `ics_unittest.conf`:
  ```
  db_host = 127.0.0.1
  db_user = odooics
  db_password = ...
  # db_name = staging-sanna
  # db_name = demo.hosti.id
  ```
  `db_name` di file ini **di-comment out** — kemungkinan nama db biasanya
  dipassing lewat CLI flag (`-d <nama_db>` / `--database=<nama_db>`) saat
  jalanin `odoo-bin`, bukan hardcoded di file conf. Kalau benar begitu,
  rewrite file conf (langkah 5 di atas) jadi tidak relevan — perlu
  pendekatan lain (env var atau instruksi eksplisit ke agent soal flag `-d`).
- `ics.conf` belum dibaca (user menolak permintaan baca file ini, mungkin
  karena ada credential yang tidak mau muncul di transcript).

## Open Questions (Belum Terjawab)

1. Waktu develop/testing, apakah `odoo-bin` dipanggil manual dengan
   `-d <nama_db>`, atau ada script/alias yang sudah set `db_name` dari
   tempat lain (env var, docker-compose, dll)?
2. Apakah folder config `/opt/project/config/ics19conf/` dipakai bersama oleh
   banyak repo (`ics`, `ics-19`, dll), atau tiap repo/worktree punya conf
   sendiri-sendiri?

Jawaban dua pertanyaan ini menentukan apakah solusi db perlu suntik ke file
conf, atau cukup env var / instruksi eksplisit ke agent soal flag CLI yang
benar.

## Status

Belum diimplementasikan — masih tahap diskusi desain. Belum ada perubahan
kode di `/opt/project/ai-cycle/`.
