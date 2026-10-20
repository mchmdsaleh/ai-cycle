from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="ai-cycle",
    help="🤖 Multi-agent AI coding cycle orchestrator",
    no_args_is_help=True,
)
console = Console()


@app.command()
def cheatsheet():
    """Print panduan singkat penggunaan ai-cycle."""
    console.print("""AI-CYCLE CHEATSHEET

Alur: implementer (default Codex) -> validasi -> Claude review -> cek manual.
Jalankan cycle dari root repo Git. Command cheatsheet bisa dari mana saja.

MULAI PAKAI
  cd /path/ke/project
  ai-cycle init

  Isi .ai-cycle/spec.md      : task, batasan, kriteria selesai.
  Isi .ai-cycle/RULES.md     : aturan coding permanen.
  Isi .ai-cycle/config.json  : model, jumlah percobaan, validasi.
  Tambahkan .ai-cycle/runs/ ke .gitignore agar log tidak ikut Git.
  Commit/stash perubahan awal, atau gunakan --allow-dirty dengan sengaja.

PERINTAH HARIAN
  ai-cycle run                         Mulai tanpa feedback sebelumnya
  ai-cycle run --max-attempts 1         Batasi satu percobaan
  ai-cycle run --allow-dirty            Izinkan perubahan belum di-commit
  ai-cycle run --implementer agy        Gunakan Antigravity CLI
  Config permanen: "implementer": "agy" (default: "codex").
  ai-cycle run --resume --allow-dirty   Gunakan feedback kegagalan sebelumnya
  ai-cycle spec "Buat fitur..."          Buat spec.md dalam plan mode
  ai-cycle spec --input ./docs/file.pdf Buat spec.md dari dokumen
  ai-cycle status                      Lihat riwayat run
  ai-cycle logs <run-id>                Lihat lokasi file log
  ai-cycle cheatsheet                   Tampilkan panduan ini
  ai-cycle --help                       Semua perintah

  --resume mengambil feedback gagal yang cocok dengan branch dan isi spec,
  bukan melanjutkan sesi agent persis dari posisi terakhir.
  run biasa tidak membawa feedback lama atau menghapus perubahan sebelumnya.

SPEC GENERATOR
  ai-cycle spec "Buat fitur..." --change nama-fitur   Buat/revisi OpenSpec
  ai-cycle run --change nama-fitur --allow-dirty     Implement OpenSpec
  Jalankan dari root repository Git:
  ai-cycle spec "Buat fitur hierarchy subtask"
  ai-cycle spec --input ./docs/wireframe.pdf
  ai-cycle spec "Ikuti CR terlampir" --input ./docs/change-request.pdf

  Codex bekerja dalam plan mode dengan akses read-only: agent boleh membaca
  source dan lampiran, tetapi tidak boleh mengubah aplikasi. Setiap spec memakai
  instruction Odoo Technical Analyst dari ai_cycle/SPEC_INSTRUCTIONS.md.
  Hasil ditulis ke .ai-cycle/spec.md hanya setelah proses sukses. Periksa spec,
  selesaikan blocker/TBD, lalu jalankan ai-cycle run.

PILIH IMPLEMENTER
  Prioritas: --implementer > config implementer > default codex.
  Tanpa flag/config: Codex yang implementasi.
  Sekali run dengan Antigravity:
  ai-cycle run --change c4 --implementer agy --allow-dirty
  Permanen: tambahkan "implementer": "agy" ke .ai-cycle/config.json;
  pertahankan setting lain. Kemudian run tanpa --implementer memakai agy.
  Override kembali ke Codex untuk satu run:
  ai-cycle run --change c4 --implementer codex --allow-dirty
  Flag yang sama berlaku pada legacy run tanpa --change.
  agy harus terpasang dan sudah login; model mengikuti konfigurasi agy.
  Mode agy: print + accept-edits + sandbox; permission tidak di-bypass.
  Planner spec tetap Codex, reviewer tetap Claude. Log: implementer.txt.

OPENSPEC (install: npm install -g @fission-ai/openspec)
  ai-cycle spec "Generate payment CSV Mandiri" --change mandiri-payment-export
  ai-cycle spec "Jawaban: D2 pakai Nama Rekening, kosong harus error" --change mandiri-payment-export
  Periksa openspec/changes/mandiri-payment-export/ dan readiness.json.
  Status draft atau blockers belum kosong akan menghentikan run sebelum agent.
  ai-cycle run --change mandiri-payment-export --allow-dirty
  ai-cycle run --change mandiri-payment-export --resume --allow-dirty
  openspec status --change mandiri-payment-export
  Setelah review dan UAT: openspec archive mandiri-payment-export
  Requirement terbaru tidak memakai feedback lama yang hash-nya berbeda.

CONFIG CONTOH (.ai-cycle/config.json)
  Sesuaikan branch dan command validasi dengan proyek:
  {
    "max_attempts": 2,
    "base_branch": "main",
    "review_model": "kr/claude-opus-5",
    "validation_commands": ["npm test"],
    "postmortem": false
  }

  validation_commands: [] berarti tidak ada validasi otomatis.
  postmortem: true menambah panggilan agent usulan aturan setelah gagal.
  Override model satu run (prioritas di atas config):
  AI_CYCLE_REVIEW_MODEL='model-id' ai-cycle run

PANTAU PROSES
  Tampilan menunjukkan stage, timer, output terakhir, dan lokasi log.
  Claude bisa belum mengeluarkan output sampai jawabannya selesai.
  Ganti <run-id> dan nomor attempt sesuai run yang ingin dibaca:
  tail -f .ai-cycle/runs/<run-id>/attempt-1/implementer.txt
  cat .ai-cycle/runs/<run-id>/attempt-1/review-claude.txt
  cat .ai-cycle/runs/<run-id>/attempt-1/feedback.txt

HASIL DAN LANGKAH BERIKUTNYA
  PASS              Cek aplikasi dan git diff, lalu commit sendiri.
  CHANGES_REQUIRED  Baca blocker; lanjut dengan --resume --allow-dirty.
  NEEDS_HUMAN       Baca spec-questions.txt, perjelas spec, jalankan lagi.
  Validasi gagal   Baca validation.txt sebelum mengulang.

BIAR HEMAT
  Buat satu task kecil dengan kriteria jelas; mulai --max-attempts 1.
  Baca feedback sebelum retry. Tidak ada commit/push otomatis.
  Riwayat status bisa salah menandai run terputus sebagai PASS;
  pastikan hasil review dan validasinya.
""", markup=False, highlight=False)


@app.command()
def spec(
    request: Optional[str] = typer.Argument(None, help="Feature or change to specify"),
    input_path: Optional[Path] = typer.Option(
        None, "--input", exists=True, file_okay=True, dir_okay=False,
        readable=True, resolve_path=True, help="Document or artifact to inspect",
    ),
    change: Optional[str] = typer.Option(None, "--change", help="Create or revise an OpenSpec change (kebab-case)"),
):
    """Plan a legacy spec or an OpenSpec change with Codex (read-only)."""
    if not request and not input_path:
        raise typer.BadParameter("Provide a request or --input FILE")

    from ai_cycle.agents.codex import codex_plan_spec
    from ai_cycle.core.config import get_project_paths, initialize_project, write
    from ai_cycle.core.git import assert_git_repo
    from ai_cycle.core.runner import require_commands

    root = Path.cwd()
    require_commands(["git", "codex"])
    assert_git_repo(root)
    initialize_project(root)
    if change:
        from ai_cycle.core.openspec import ARTIFACTS, openspec, prepare_change, save_artifacts
        path = prepare_change(root, change)
        context = "\n\n".join(openspec(root, "instructions", artifact, "--change", change, "--json") for artifact in ARTIFACTS)
        existing = sorted(path.rglob("*.md"))
        if (path / "readiness.json").exists():
            existing.append(path / "readiness.json")
        context += "\n\nExisting artifacts to reconcile:\n" + "\n\n".join(f"{item.relative_to(path)}:\n{item.read_text()}" for item in existing)
        with console.status("[bold]Planning OpenSpec change with Codex..."):
            generated = codex_plan_spec(request, input_path, root, planning_context=context)
        save_artifacts(path, generated)
        openspec(root, "validate", change, "--strict")
        console.print(f"[green]OpenSpec change written:[/green] {path}")
        console.print((path / "readiness.json").read_text())
        return
    with console.status("[bold]Planning spec with Codex...[/bold]"):
        generated = codex_plan_spec(request, input_path, root)
    spec_path = get_project_paths(root)["state"] / "spec.md"
    write(spec_path, generated)
    console.print(f"[green]Spec written:[/green] {spec_path}")


@app.command()
def run(
    resume: bool = typer.Option(False, help="Resume from latest failed run"),
    allow_dirty: bool = typer.Option(False, help="Allow dirty working tree"),
    max_attempts: Optional[int] = typer.Option(None, help="Override max attempts"),
    change: Optional[str] = typer.Option(None, "--change", help="Implement this OpenSpec change"),
    implementer: Optional[str] = typer.Option(None, "--implementer", help="Override implementer: codex or agy"),
):
    """🚀 Run the AI coding cycle"""
    from ai_cycle.orchestrator import execute_cycle

    execute_cycle(resume=resume, allow_dirty=allow_dirty, max_attempts=max_attempts, change=change, implementer=implementer)


@app.command()
def status():
    """📊 Show status of all runs"""
    from ai_cycle.ui.panels import render_status_table

    render_status_table()


@app.command()
def logs(run_id: str = typer.Argument(..., help="Run ID, e.g. 20260814-141321")):
    """📋 Show detailed logs for a specific run"""
    from ai_cycle.ui.panels import render_run_details

    render_run_details(run_id)


@app.command()
def init():
    """📁 Initialize .ai-cycle/ in current directory"""
    from ai_cycle.core.config import initialize_project

    created = initialize_project()
    if created:
        console.print("[green]Created:[/green]")
        for p in created:
            console.print(f"  {p}")
    else:
        console.print("[dim].ai-cycle/ already initialized.[/dim]")


worktree_app = typer.Typer(help="🌳 Manage git worktrees for parallel tasks")
app.add_typer(worktree_app, name="worktree")


@worktree_app.command("add")
def worktree_add(
    name: str,
    base: str = typer.Option("main", help="Base branch to branch from"),
    existing: bool = typer.Option(False, help="Use an existing branch instead of creating one"),
):
    """Create a new worktree with .ai-cycle/ template copied in"""
    from ai_cycle.core.config import get_project_paths, initialize_project
    from ai_cycle.core.git import worktree_add as git_worktree_add

    root = Path.cwd()
    target = git_worktree_add(root, name, base=base, existing=existing)

    src_state = get_project_paths(root)["state"]
    if src_state.exists():
        import shutil

        dst_state = target / ".ai-cycle"
        for fname in ("config.json", "RULES.md", "spec.md"):
            src_file = src_state / fname
            if src_file.exists():
                dst_state.mkdir(parents=True, exist_ok=True)
                shutil.copy(src_file, dst_state / fname)
    else:
        initialize_project(target)

    console.print(f"[green]Worktree created:[/green] {target}")
    console.print(f"Next: cd {target} && ai-cycle run")


@worktree_app.command("list")
def worktree_list_cmd():
    """List active worktrees and their cycle status"""
    from ai_cycle.core.git import worktree_list

    root = Path.cwd()
    entries = worktree_list(root)

    table = Table(title="🌳 Active Worktrees")
    table.add_column("Path")
    table.add_column("Branch")
    for entry in entries:
        if entry.get("bare"):
            continue
        table.add_row(entry.get("path", "?"), entry.get("branch", "?"))
    console.print(table)


@worktree_app.command("remove")
def worktree_remove_cmd(
    name: str,
    force: bool = typer.Option(False, help="Force removal even with uncommitted changes"),
):
    """Remove a worktree"""
    from ai_cycle.core.git import worktree_remove, worktrees_root

    root = Path.cwd()
    path = worktrees_root(root) / name
    worktree_remove(root, path, force=force)
    console.print(f"[green]Removed worktree:[/green] {path}")


if __name__ == "__main__":
    app()
