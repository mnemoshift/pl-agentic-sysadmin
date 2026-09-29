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

    repo_root = Path(__file__).resolve().parent.parent.parent
    default_template = repo_root / "templates" / "kdenlive" / "short_9_16_template.kdenlive"

    # Zapewnienie katalogu assets i kopiowanie domyślnych placeholderów graficznych jeśli brak
    assets_dir = workspace / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    template_assets = repo_root / "templates" / "assets"
    if template_assets.exists():
        for img in template_assets.glob("*.jpg"):
            target_img = assets_dir / img.name
            if not target_img.exists():
                shutil.copy(img, target_img)

    # Szukanie referencyjnego pliku .kdenlive
    candidates_kdenlive = []
    if ref_kdenlive_path:
        candidates_kdenlive.append(ref_kdenlive_path)
    candidates_kdenlive.extend([
        default_template,
        workspace / "assets" / ".cache" / f"{name}_Agentic_SysAdmin_reference.kdenlive",
        workspace / f"{name}.kdenlive"
    ])

    ref_kdenlive = next((p for p in candidates_kdenlive if p.exists()), None)
    if not ref_kdenlive:
        print(f"[BŁĄD] Nie znaleziono pliku referencyjnego .kdenlive w {workspace} ani w {default_template}", file=sys.stderr)
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

    # Dynamiczne dopasowanie ścieżki do pliku lektora (WAV)
    candidate_wavs = list(assets_dir.glob("*.wav")) + list((workspace / "input").glob("*.wav"))
    if candidate_wavs:
        # Preferujemy plik z CLEAN w nazwie
        clean_wav = next((w for w in candidate_wavs if "CLEAN" in w.name.upper()), candidate_wavs[0])
        # Względna ścieżka od workspace
        try:
            rel_wav = clean_wav.relative_to(workspace)
        except ValueError:
            rel_wav = f"assets/{clean_wav.name}"
        content = content.replace("assets/EP002_Short_VoiceOver_CLEAN.wav", str(rel_wav))

    # Dynamiczne dopasowanie pliku wideo z b-rolla / screencastu (MP4)
    input_dir = workspace / "input"
    candidate_mp4s = []
    if input_dir.exists():
        candidate_mp4s.extend([p for p in input_dir.glob("*.mp4") if "voiceover" not in p.name.lower()])
    candidate_mp4s.extend([p for p in workspace.glob("*.mp4") if "voiceover" not in p.name.lower() and p.name != f"{name}.mp4"])

    if candidate_mp4s:
        chosen_mp4 = candidate_mp4s[0]
        try:
            rel_mp4 = chosen_mp4.relative_to(workspace)
        except ValueError:
            rel_mp4 = chosen_mp4.name
        content = content.replace("EP002_Zorin_Desktop_FINAL.mp4", str(rel_mp4))

    default_template_ass = repo_root / "templates" / "kdenlive" / f"short_9_16_template.kdenlive{seq_uuid}-1.ass"

    # Szukanie referencyjnego pliku ASS
    candidates_ass = []
    if ref_ass_path:
        candidates_ass.append(ref_ass_path)
    candidates_ass.extend([
        workspace / "assets" / f"{name}_Karaoke.ass",
        default_template_ass,
        workspace / "assets" / ".cache" / f"{name}_Agentic_SysAdmin_reference.kdenlive{seq_uuid}-1.ass",
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
