"""
pipeline/pillow.py — Incrustation sous-titres via Pillow + rawvideo pipe — Subvox
"""

import subprocess
import threading
import os
from pathlib import Path
from typing import Optional

from core.logging_setup import get_logger
from core.utils import format_duration_human
from core.pipeline.ffmpeg import (
    _ffmpeg_path,
    _get_video_dims,
    _get_video_fps,
    _get_video_duration,
)
from core.pipeline.srt import _parse_srt

logger = get_logger(__name__)


def _burn_subtitles_pillow(
    video_path: Path,
    srt_path: Path,
    output_path: Path,
    wm_path: Optional[Path] = None,
) -> bool:
    """
    Incrustation sous-titres via Pillow + rawvideo pipe vers ffmpeg.
    Fonctionne avec N'IMPORTE QUEL ffmpeg (pas de libass requis).
    """
    try:
        from PIL import Image, ImageDraw, ImageFont  # type: ignore
    except ImportError:
        logger.error("Pillow non installe -- copie video sans sous-titres")
        import shutil

        shutil.copy2(video_path, output_path)
        return output_path.exists()

    ffmpeg = _ffmpeg_path()
    vid_w, vid_h = _get_video_dims(video_path)
    fps = _get_video_fps(video_path)
    duration = _get_video_duration(video_path)
    total_frames = int(fps * duration) + 5

    blocks = _parse_srt(srt_path.read_text(encoding="utf-8"))
    frame_to_text: dict[int, str] = {}
    for block in blocks:
        parts = block["timecode"].split(" --> ")
        if len(parts) != 2:
            continue

        def _ts(ts: str) -> float:
            ts = ts.strip().replace(",", ".")
            p = ts.split(":")
            if len(p) == 2:
                m, s = p
                return int(m) * 60 + float(s)
            h, m, s = p
            return int(h) * 3600 + int(m) * 60 + float(s)

        start_f = int(_ts(parts[0]) * fps)
        end_f = int(_ts(parts[1]) * fps)
        text = block["text"].replace("\n", " ").strip()
        if text:
            for f in range(start_f, min(end_f, total_frames)):
                frame_to_text[f] = text

    if not frame_to_text:
        import shutil

        shutil.copy2(video_path, output_path)
        return output_path.exists()

    # Police Unicode
    font_candidates = [
        "/System/Library/Fonts/Supplemental/Arial Unicode MS.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/noto/NotoSans-Regular.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf",
        "/usr/share/fonts/truetype/msttcorefonts/Arial.ttf",
    ]
    font_file = next((p for p in font_candidates if os.path.isfile(p)), None)
    if font_file:
        logger.info(f"Police Unicode trouvee: {font_file}")
    else:
        logger.warning("Aucune police TTF trouvee -- fallback bitmap 8px")

    is_vertical = vid_h > vid_w * 1.4

    if is_vertical:
        base_size = int(vid_w * 0.070)
        fontsize = max(28, min(base_size, 55))
    else:
        base_size = int(vid_h * 0.050)
        fontsize = max(22, min(base_size, 55))

    orientation = "VERTICAL" if is_vertical else "HORIZONTAL"
    logger.info(
        f"Pillow config: {vid_w}x{vid_h} -> {orientation}",
        extra={"fontsize": fontsize, "base_size": base_size},
    )

    def _load_font(fs: int):
        if font_file:
            try:
                return ImageFont.truetype(font_file, fs)
            except Exception:
                pass
        try:
            return ImageFont.load_default(size=fs)
        except TypeError:
            return ImageFont.load_default()

    _load_font(fontsize)
    pad_h = 10
    pad_v = 8
    max_w = int(vid_w * 0.80)
    TRANSPARENT = bytes(vid_w * vid_h * 4)
    text_bytes: dict[str, bytes] = {}

    _mimg = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    _mdraw = ImageDraw.Draw(_mimg)

    unique_texts = set(frame_to_text.values())

    # Adaptation police par texte
    text_fontsize: dict[str, int] = {}
    for text in unique_texts:
        fs = fontsize
        for _ in range(5):
            import textwrap as _tw

            test_lines = _tw.wrap(text, width=max(20, int(max_w / (fs * 0.55))))
            n_lines = len(test_lines) if test_lines else 1
            estimated_height = n_lines * (fs * 1.35) + (n_lines - 1) * max(
                4, int(fs * 0.12)
            )
            if estimated_height <= vid_h * 0.30 or fs <= 16:
                break
            fs -= 2
        text_fontsize[text] = max(16, fs)
        if fs < fontsize:
            logger.debug(
                f"Texte long ({len(text)} chars) -> fontsize reduit {fontsize}->{fs}px"
            )

    for text in unique_texts:
        fs = text_fontsize[text]
        import textwrap as _tw

        wrapped_lines = _tw.wrap(text, width=max(20, int(max_w / (fs * 0.55))))
        if not wrapped_lines:
            wrapped_lines = [text]

        current_font = _load_font(fs)
        img = Image.new("RGBA", (vid_w, vid_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        line_sizes = [
            draw.textbbox((0, 0), l, font=current_font) for l in wrapped_lines
        ]
        line_widths = [b[2] - b[0] for b in line_sizes]
        line_heights = [b[3] - b[1] for b in line_sizes]
        line_gap = max(4, int(fs * 0.12))
        total_h = sum(line_heights) + line_gap * (len(wrapped_lines) - 1)
        box_w = min(max(line_widths) + pad_h * 2, vid_w - 10)
        box_h = total_h + pad_v * 2
        x = (vid_w - box_w) // 2
        margin_bot = int(vid_h * 0.05)
        y = vid_h - box_h - margin_bot

        opacity_str = os.environ.get("SUBTITLE_OPACITY", "100")
        try:
            opacity = int(opacity_str.split("#")[0].strip())
            opacity = max(0, min(100, opacity))
            alpha = int(opacity * 255 / 100)
        except ValueError:
            alpha = 230

        draw.rectangle([x, y, x + box_w, y + box_h], fill=(0, 0, 0, alpha))

        cur_y = y + pad_v
        for line, lw, lh in zip(wrapped_lines, line_widths, line_heights):
            tx = x + (box_w - lw) // 2
            draw.text((tx, cur_y), line, fill=(255, 255, 255, 255), font=current_font)
            cur_y += lh + line_gap

        text_bytes[text] = img.tobytes()

    logger.info(
        f"Pillow rendering: {len(unique_texts)} sous-titres, "
        f"{total_frames} frames @ {fps:.1f}fps ({vid_w}x{vid_h})"
    )

    # La vidéo source est l'input 1 (0 = rawvideo pipe des sous-titres)
    filter_bg = "[1:v]format=yuv420p[bg]"
    filter_fg = "[0:v]format=rgba[fg]"
    filter_base_overlay = "[bg][fg]overlay=0:0[base]"

    cmd = [
        ffmpeg,
        "-y",
        "-f",
        "rawvideo",
        "-vcodec",
        "rawvideo",
        "-s",
        f"{vid_w}x{vid_h}",
        "-pix_fmt",
        "rgba",
        "-r",
        str(fps),
        "-i",
        "-",
        "-i",
        str(video_path),
    ]

    if wm_path and wm_path.exists():
        cmd.extend(["-i", str(wm_path)])
        filter_wm = (
            f"[2:v]format=rgba,scale={vid_w}:{vid_h}:"
            f"force_original_aspect_ratio=decrease[wm]"
        )
        filter_complex = f"{filter_bg};{filter_fg};{filter_base_overlay};{filter_wm};[base][wm]overlay=0:0[out]"
        cmd.extend(["-filter_complex", filter_complex])
        cmd.extend(["-map", "[out]"])
    else:
        filter_complex = f"{filter_bg};{filter_fg};{filter_base_overlay}"
        cmd.extend(["-filter_complex", filter_complex])
        cmd.extend(["-map", "[base]"])

    cmd.extend(
        [
            "-map",
            "1:a?",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "20",
            "-g",
            "60",
            "-bf",
            "2",
            "-profile:v",
            "high",
            "-level",
            "4.2",
            "-movflags",
            "+faststart",
            "-pix_fmt",
            "yuv420p",
            "-threads",
            "0",
        ]
    )

    cmd.append(str(output_path))

    multiplier = float(os.environ.get("PILLOW_TIMEOUT_MULTIPLIER", "3.0"))
    writer_timeout = min(7200, max(600, int(duration * multiplier)))
    hum_duration = format_duration_human(duration)
    hum_writer = format_duration_human(writer_timeout)
    logger.debug(
        f"Writer timeout: {hum_writer} (video={hum_duration}, multiplier={multiplier}x)"
    )

    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)

    write_ok = threading.Event()

    def _write_frames():
        try:
            i = 0
            while i < total_frames:
                txt = frame_to_text.get(i, "")
                data = text_bytes.get(txt, TRANSPARENT)
                proc.stdin.write(data)  # type: ignore
                i += 1
            proc.stdin.close()  # type: ignore
            write_ok.set()
        except BrokenPipeError:
            write_ok.set()

    wt = threading.Thread(target=_write_frames, daemon=True)
    wt.start()

    try:
        stdout, stderr = proc.communicate(timeout=writer_timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        logger.error(
            f"Timeout stdin apres {writer_timeout}s -> process killed",
            extra={"writer_timeout": writer_timeout},
        )
        return False

    wt.join(timeout=5)
    write_ok.set()

    if proc.returncode == 0 and output_path.exists():
        mode = "pillow+WM" if (wm_path and wm_path.exists()) else "pillow"
        logger.info(
            "Pillow burn RESULT: "
            f"video={video_path.name} "
            f"size={output_path.stat().st_size // 1024}KB "
            f"mode={mode} "
            f"vid={vid_w}x{vid_h} "
            f"fontsize={fontsize} "
            f"fps={fps:.1f} "
            f"total_frames={total_frames} "
            f"subtitle_count={len(unique_texts)} "
            f"opacity={opacity}% "
        )
        # Vérifier la commande ffmpeg finale
        cmd_str = " ".join(str(c) for c in cmd)
        logger.info(f"Pillow ffmpeg cmd: {cmd_str[:500]}...")
        return True
    else:
        err = stderr.decode("utf-8", errors="replace") if stderr else ""
        logger.error(
            f"Pillow burn failed: returncode={proc.returncode}",
            extra={"stderr": err[-400:]},
        )
        return False
