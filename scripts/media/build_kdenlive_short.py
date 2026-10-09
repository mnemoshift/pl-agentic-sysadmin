#!/usr/bin/env python3
"""
Montaż wertykalnego projektu Kdenlive 1080x1920 @ 60fps
z wykorzystaniem silnika MLT / Kdenlive XML i kaskadowej kompozycji:
- Ścieżka A1: VoiceOver CLEAN WAV (dynamicznie dopasowana do rzeczywistej długości nagrania)
- Ścieżka V1: Rozmyte tło (gblur) dla wideo 16:9 powiększonego do pionu
- Ścieżka V2: Ostry pierwszy plan (kadry 9:16 + wycinki wideo z cieniem)
- Ścieżka V3: Dynamiczne tytuły tekstowe (Inter Black)
- Traktor: Filtr avfilter.subtitles ładujący plik ASS z karaoke (generowany dla bieżącego audio)
"""
import argparse
import re
import shutil
import subprocess
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
    parser.add_argument("--with-karaoke", action="store_true", help="Dołącz napisy karaoke (domyślnie wyłączone; generowane i podpinane w osobnym kroku)")
    return parser.parse_args()

def get_audio_duration(audio_path: Path) -> float:
    try:
        import wave
        with wave.open(str(audio_path), "rb") as wf:
            return wf.getnframes() / float(wf.getframerate())
    except Exception:
        res = subprocess.run([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)
        ], capture_output=True, text=True)
        try:
            return float(res.stdout.strip())
        except ValueError:
            return 30.5

def format_ts_mlt(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"

def build_project(workspace: Path, name: str, seq_uuid: str, ref_kdenlive_path: Path, ref_ass_path: Path, with_karaoke: bool = False):
    target_kdenlive = workspace / f"{name}.kdenlive"
    target_sidecar = workspace / f"{name}.kdenlive{seq_uuid}-1.ass"

    print(f"[Kdenlive] Generowanie osi czasu projektu: {target_kdenlive.name} w {workspace}...")

    repo_root = Path(__file__).resolve().parent.parent.parent
    default_template = repo_root / "templates" / "kdenlive" / "short_9_16_template.kdenlive"

    # Zapewnienie katalogu assets
    assets_dir = workspace / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

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

    # Podmieniamy root projektu
    new_root = str(workspace.resolve())
    content = re.sub(r'root="[^"]*"', f'root="{new_root}"', content)

    # Dynamiczne dopasowanie ścieżki do pliku lektora (WAV)
    candidate_wavs = list(assets_dir.glob("*.wav")) + list((workspace / "input").glob("*.wav"))
    audio_duration = 30.5
    clean_wav = None
    if candidate_wavs:
        # Preferujemy plik z CLEAN w nazwie
        clean_wav = next((w for w in candidate_wavs if "CLEAN" in w.name.upper()), candidate_wavs[0])
        try:
            rel_wav = clean_wav.relative_to(workspace)
        except ValueError:
            rel_wav = f"assets/{clean_wav.name}"
        content = content.replace("assets/EP002_Short_VoiceOver_CLEAN.wav", str(rel_wav))
        audio_duration = get_audio_duration(clean_wav)
        print(f"[Audio] Wykryto plik lektorski: {rel_wav} (długość: {audio_duration:.2f}s)")

    # Dynamiczne dostosowanie długości osi czasu do rzeczywistego czasu audio
    dur_str = format_ts_mlt(audio_duration)
    frames = int(round(audio_duration * 60))

    content = re.sub(r'<property name="kdenlive:duration">00:00:30\.\d+</property>', f'<property name="kdenlive:duration">{dur_str}</property>', content)
    content = re.sub(r'<chain id="chain0" out="00:00:30\.\d+">', f'<chain id="chain0" out="{dur_str}">', content)

    # Zastąpienie pociętej ścieżki audio w playlist0 jedną ciągłą ścieżką do końca nagrania
    old_playlist0_pat = r'<playlist id="playlist0">.*?</playlist>'
    new_playlist0 = f'''<playlist id="playlist0">
   <property name="kdenlive:audio_track">1</property>
   <entry in="00:00:00.000" out="{dur_str}" producer="chain0">
    <property name="kdenlive:id">6</property>
   </entry>
  </playlist>'''
    content = re.sub(old_playlist0_pat, new_playlist0, content, flags=re.DOTALL)

    for t_id in ["tractor0", "tractor2", "tractor3", "tractor4", seq_uuid, "tractor5"]:
        escaped_id = re.escape(t_id)
        content = re.sub(rf'<tractor id="{escaped_id}" in="00:00:00\.000" out="00:00:30\.\d+">', f'<tractor id="{t_id}" in="00:00:00.000" out="{dur_str}">', content)

    content = re.sub(r'<entry in="00:00:00\.000" out="00:00:30\.\d+" producer="chain0"/>', f'<entry in="00:00:00.000" out="{dur_str}" producer="chain0"/>', content)
    content = re.sub(rf'<entry in="00:00:00\.000" out="00:00:30\.\d+" producer="{re.escape(seq_uuid)}"/>', f'<entry in="00:00:00.000" out="{dur_str}" producer="{seq_uuid}"/>', content)
    content = re.sub(rf'<track in="00:00:00\.000" out="00:00:30\.\d+" producer="{re.escape(seq_uuid)}"/>', f'<track in="00:00:00.000" out="{dur_str}" producer="{seq_uuid}"/>', content)

    # Rozciągnięcie ostatniego klipu wideo (Scena 5) na ścieżkach V1 i V2 do końca audio
    content = re.sub(
        r'(<playlist id="playlist[46]".*?<entry [^>]*? out=")00:00:30\.\d+(")',
        rf'\g<1>{dur_str}\g<2>',
        content,
        flags=re.DOTALL
    )

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

    # Dynamiczne dopasowanie grafik kadrów (JPG/PNG) wygenerowanych w assets/
    image_files = sorted([
        p for p in assets_dir.glob("*")
        if p.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp"]
    ])
    default_img_refs = [
        "assets/kadr1_agentic_sysadmin.jpg",
        "assets/kadr2_config_chaos.jpg",
        "assets/kadr3_macos_desktop.jpg"
    ]
    for idx, default_ref in enumerate(default_img_refs):
        if idx < len(image_files):
            img_rel = f"assets/{image_files[idx].name}"
            content = content.replace(default_ref, img_rel)

    # Obsługa napisów Karaoke ASS (włączana tylko przy fladze --with-karaoke lub podaniu --ref-ass)
    attach_subs = with_karaoke or bool(ref_ass_path)
    karaoke_file = workspace / "assets" / f"{name}_Karaoke.ass"

    if attach_subs:
        old_sub_prop = f"<property name=\"av.filename\">EP002_Short_Agentic_SysAdmin.kdenlive{seq_uuid}-1.ass</property>"
        new_sub_prop = f"<property name=\"av.filename\">{target_sidecar.resolve()}</property>"
        content = content.replace(old_sub_prop, new_sub_prop)

        if ref_ass_path and ref_ass_path.exists():
            shutil.copy(ref_ass_path, target_sidecar)
            print(f"[OK] Skopiowano podany plik ASS: {ref_ass_path} -> {target_sidecar.name}")
        elif karaoke_file.exists():
            shutil.copy(karaoke_file, target_sidecar)
            print(f"[OK] Podpięto wygenerowane napisy Karaoke: {karaoke_file.name}")
        else:
            print(f"[Karaoke] Brak pliku {karaoke_file.name}. Uruchom generate_karaoke.py aby wygenerować napisy.", file=sys.stderr)
    else:
        # Domyślnie: czysty projekt Kdenlive BEZ napisów (napisy generowane i podpinane w Kroku 5)
        for old_ass in workspace.glob(f"{name}.kdenlive*.ass"):
            try:
                old_ass.unlink()
            except OSError:
                pass

        # Usunięcie filtru avfilter.subtitles z traktora
        content = re.sub(
            r'\s*<filter id="[^"]+">\s*<property name="mlt_service">avfilter\.subtitles</property>.*?</filter>',
            '',
            content,
            flags=re.DOTALL
        )
        # Wyczyszczenie listy napisów w sequenceproperties
        content = re.sub(
            r'<property name="kdenlive:sequenceproperties\.subtitlesList">.*?</property>',
            '<property name="kdenlive:sequenceproperties.subtitlesList">[]\n</property>',
            content,
            flags=re.DOTALL
        )
        content = re.sub(
            r'<property name="kdenlive:sequenceproperties\.kdenlive:activeSubtitleIndex">\d+</property>',
            '<property name="kdenlive:sequenceproperties.kdenlive:activeSubtitleIndex">-1</property>',
            content
        )
        print("[Kdenlive] Zmontowano czystą oś czasu (ścieżki A1, V1, V2, V3) BEZ napisów karaoke.")

    target_kdenlive.write_text(content, encoding="utf-8")
    print(f"[OK] Zapisano projekt Kdenlive: {target_kdenlive} (czas osi: {dur_str})")

if __name__ == "__main__":
    args = parse_args()
    build_project(
        workspace=args.workspace,
        name=args.name,
        seq_uuid=args.seq_uuid,
        ref_kdenlive_path=args.ref_kdenlive,
        ref_ass_path=args.ref_ass,
        with_karaoke=args.with_karaoke
    )
