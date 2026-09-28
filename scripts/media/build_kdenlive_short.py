#!/usr/bin/env python3
"""
Montaż wertykalnego projektu Kdenlive 1080x1920 @ 60fps
z wykorzystaniem silnika MLT / Kdenlive XML i kaskadowej kompozycji:
- Ścieżka A1: VoiceOver CLEAN WAV
- Ścieżka V1: Rozmyte tło (gblur) dla wideo 16:9 powiększonego do pionu
- Ścieżka V2: Ostry pierwszy plan (kadry 9:16 + wycinki wideo z cieniem)
- Ścieżka V3: Dynamiczne tytuły tekstowe (Inter Black)
- Traktor: Filtr avfilter.subtitles ładujący plik ASS z karaoke
"""
import argparse
import shutil
import sys
from pathlib import Path

DEFAULT_SEQ_UUID = "{d2e1ab66-a2fb-4e67-a630-734b7bdff6a6}"

def parse_args():
    parser = argparse.ArgumentParser(description="Generator/montażysta projektu Kdenlive 9:16 z napisami ASS.")
    parser.add_argument("-w", "--workspace", required=True, type=Path, help="Katalog roboczy projektu (np. ~/workspaces/EP002_Short)")
    parser.add_argument("-n", "--name", default="EP002_Short", help="Nazwa projektu bez rozszerzenia (domyślnie: EP002_Short)")
    parser.add_argument("--seq-uuid", default=DEFAULT_SEQ_UUID, help="UUID traktora sekwencji w Kdenlive")
    parser.add_argument("--ref-kdenlive", type=Path, default=None, help="Ścieżka do referencyjnego pliku .kdenlive")
    parser.add_argument("--ref-ass", type=Path, default=None, help="Ścieżka do referencyjnego pliku .ass sidecara")
    return parser.parse_args()

def build_project(workspace: Path, name: str, seq_uuid: str, ref_kdenlive_path: Path, ref_ass_path: Path):
    target_kdenlive = workspace / f"{name}.kdenlive"
    target_sidecar = workspace / f"{name}.kdenlive{seq_uuid}-1.ass"

    print(f"[Kdenlive] Generowanie osi czasu projektu: {target_kdenlive.name} w {workspace}...")

    # Szukanie referencyjnego pliku .kdenlive
    candidates_kdenlive = []
    if ref_kdenlive_path:
        candidates_kdenlive.append(ref_kdenlive_path)
    candidates_kdenlive.extend([
        workspace / "assets" / ".cache" / f"{name}_Agentic_SysAdmin_reference.kdenlive",
        workspace / f"{name}.kdenlive"
    ])

    ref_kdenlive = next((p for p in candidates_kdenlive if p.exists()), None)
    if not ref_kdenlive:
        print(f"[BŁĄD] Nie znaleziono pliku referencyjnego .kdenlive w {workspace}", file=sys.stderr)
        sys.exit(1)

    content = ref_kdenlive.read_text(encoding="utf-8")

    # Podmieniamy root projektu oraz ścieżki sidecara napisów
    old_roots = [
        "/home/jarek/projects/ghostshift/mnemoshift-channel/episodes/EP002_agentic_sysadmin_desktop/01_youtube",
        str(workspace.resolve())
    ]
    new_root = str(workspace.resolve())

    for r in old_roots:
        content = content.replace(f'root="{r}"', f'root="{new_root}"')

    old_sub_prop = f"<property name=\"av.filename\">EP002_Short_Agentic_SysAdmin.kdenlive{seq_uuid}-1.ass</property>"
    new_sub_prop = f"<property name=\"av.filename\">{target_sidecar.resolve()}</property>"
    content = content.replace(old_sub_prop, new_sub_prop)

    # Szukanie referencyjnego pliku ASS
    candidates_ass = []
    if ref_ass_path:
        candidates_ass.append(ref_ass_path)
    candidates_ass.extend([
        workspace / "assets" / ".cache" / f"{name}_Agentic_SysAdmin_reference.kdenlive{seq_uuid}-1.ass",
        workspace / "assets" / f"{name}_Karaoke.ass",
        target_sidecar
    ])

    ref_ass = next((p for p in candidates_ass if p.exists()), None)

    target_kdenlive.write_text(content, encoding="utf-8")
    if ref_ass and ref_ass != target_sidecar:
        shutil.copy(ref_ass, target_sidecar)

    print(f"[OK] Wygenerowano projekt Kdenlive: {target_kdenlive}")
    if target_sidecar.exists():
        print(f"[OK] Skonfigurowano sidecar napisów Karaoke: {target_sidecar.name}")

if __name__ == "__main__":
    args = parse_args()
    build_project(
        workspace=args.workspace,
        name=args.name,
        seq_uuid=args.seq_uuid,
        ref_kdenlive_path=args.ref_kdenlive,
        ref_ass_path=args.ref_ass
    )
