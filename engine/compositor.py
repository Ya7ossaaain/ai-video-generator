# -*- coding: utf-8 -*-
"""
engine/compositor.py
Hybrid Scene Compositor, ASS Arabic Subtitle Generator, Film Grain & Vignette Grading,
and Final Documentary Master Assembly.
"""

import os
import json
from pathlib import Path
from typing import List, Dict, Any
from PIL import Image, ImageDraw, ImageEnhance

from engine.config import CONFIG, TARGET_W, TARGET_H
from engine.telemetry import log, probe_duration, is_valid_media, run_cmd
from engine.blender_runner import BlenderRunner
from engine.remotion_runner import RemotionRunner


class HybridCompositor:
    def __init__(self):
        self.blender = BlenderRunner()
        self.remotion = RemotionRunner()

    def write_arabic_ass_subtitles(self, shots: List[Dict[str, Any]], out_ass: Path) -> Path:
        out_ass.parent.mkdir(parents=True, exist_ok=True)
        header = (
            "[Script Info]\n"
            "Title: LEMMiNO Hybrid Documentary Arabic Subtitles\n"
            "ScriptType: v4.00+\n"
            f"PlayResX: {TARGET_W}\n"
            f"PlayResY: {TARGET_H}\n"
            "WrapStyle: 0\n"
            "ScaledBorderAndShadow: yes\n\n"
            "[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
            "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding\n"
            "Style: Default,Noto Sans Arabic,54,&H00F8FAFC,&H00F8FAFC,&H00080A0F,&H96040508,"
            "-1,0,0,0,100,100,0,0,1,3,1.5,2,90,90,64,1\n\n"
            "[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        )

        def fmt_ass_time(sec: float) -> str:
            h = int(sec // 3600)
            m = int((sec % 3600) // 60)
            s = sec % 60
            return f"{h}:{m:02d}:{s:05.2f}"

        lines = [header]
        for s in shots:
            t_start = fmt_ass_time(float(s["start"]))
            t_end = fmt_ass_time(float(s["end"]))
            clean_text = str(s.get("text", "")).replace("\\", "").replace("{", "").replace("}", "").strip()
            if clean_text:
                lines.append(f"Dialogue: 0,{t_start},{t_end},Default,,0,0,0,,{{\\fad(100,100)}}{clean_text}\n")

        with open(out_ass, "w", encoding="utf-8") as f:
            f.writelines(lines)

        log(f"📝 تم إنشاء ملف الترجمة العربية الاحترافي: {out_ass} ({len(shots)} سطر)")
        return out_ass

    def render_hybrid_shot(
        self,
        shot: Dict[str, Any],
        evidence_lookup: Dict[str, Dict[str, Any]],
    ) -> Path:
        shot_id = shot["shot_id"]
        engine = shot.get("engine", "REMOTION_VECTOR_MAP")
        exact_frames = int(shot.get("exact_frames", 60))
        out_mp4 = CONFIG.rendered_shots_dir / f"{shot_id}_{engine}.mp4"

        ev_id = shot.get("evidence_id", "EV_001")
        ev_item = evidence_lookup.get(ev_id) or next(iter(evidence_lookup.values()), {})
        ev_path = CONFIG.repo_root / ev_item.get("local_path", "workspace/evidence_vault/EV_001.jpg")

        if engine == "BLENDER_WIREFRAME_HUD":
            raw_3d = CONFIG.rendered_shots_dir / f"_{shot_id}_3d_raw.mp4"
            anchors_json = CONFIG.rendered_shots_dir / f"_{shot_id}_anchors.json"
            self.blender.render_wireframe_turntable(
                model_id=shot.get("model_id", "commercial_airliner"),
                highlight_part=shot.get("highlight_part", "aft_stairs"),
                style=shot.get("style", "wireframe"),
                exact_frames=exact_frames,
                output_path=raw_3d,
                anchors_out=anchors_json,
            )
            anchors_data = []
            if anchors_json.exists():
                try:
                    anchors_data = json.loads(anchors_json.read_text(encoding="utf-8")).get("anchors", [])
                except Exception:
                    pass

            hud_props = {
                "modelName": f"{shot.get('model_id', 'commercial_airliner').upper()} // 3D WIREFRAME",
                "highlightPart": shot.get("highlight_part", "aft_stairs"),
                "hud_label": shot.get("hud_label", "3D FORENSIC TELEMETRY"),
                "arabicTitle": shot.get("text", "")[:55],
                "coordinates": shot.get("coordinates", "45.9214° N, 122.2819° W"),
                "anchors": anchors_data,
            }
            self.remotion.render_composition(
                composition_id="HudOverlay",
                props=hud_props,
                exact_frames=exact_frames,
                output_path=out_mp4,
                background_video=raw_3d,
            )
            raw_3d.unlink(missing_ok=True)
            anchors_json.unlink(missing_ok=True)

        elif engine == "BLENDER_25D_PARALLAX":
            self.blender.render_25d_parallax(
                image_path=ev_path,
                particles=shot.get("particles", "dust"),
                exact_frames=exact_frames,
                output_path=out_mp4,
            )

        elif engine == "BLENDER_TERRAIN_MAP":
            raw_topo = CONFIG.rendered_shots_dir / f"_{shot_id}_topo_raw.mp4"
            self.blender.render_terrain_ocean(
                mode=shot.get("terrain_mode", "terrain"),
                coords=shot.get("coordinates", "45.9214° N, 122.2819° W"),
                exact_frames=exact_frames,
                output_path=raw_topo,
            )
            hud_props = {
                "modelName": f"TOPOGRAPHIC RECON // {shot.get('terrain_mode', 'terrain').upper()}",
                "highlightPart": "SEARCH SECTOR TARGET",
                "hud_label": f"GIS SECTOR // {shot.get('coordinates', '45.92° N, 122.28° W')}",
                "arabicTitle": shot.get("text", "")[:55],
                "coordinates": shot.get("coordinates", "45.9214° N, 122.2819° W"),
                "anchors": [{"frame": i, "x": 960, "y": 500} for i in range(exact_frames)],
            }
            self.remotion.render_composition(
                composition_id="HudOverlay",
                props=hud_props,
                exact_frames=exact_frames,
                output_path=out_mp4,
                background_video=raw_topo,
            )
            raw_topo.unlink(missing_ok=True)

        elif engine == "REMOTION_VECTOR_MAP":
            self.remotion.render_composition(
                composition_id="VectorMapTracker",
                props={
                    "title": f"GIS VECTOR TRACKER // {shot_id}",
                    "arabicTitle": shot.get("text", "")[:55],
                    "coordinates": shot.get("coordinates", "45.9214° N, 122.2819° W"),
                },
                exact_frames=exact_frames,
                output_path=out_mp4,
            )

        elif engine == "REMOTION_DOSSIER_GRID":
            self.remotion.render_composition(
                composition_id="ForensicDossier",
                props={
                    "mode": shot.get("dossier_mode", "suspect"),
                    "arabicRole": shot.get("text", "")[:55],
                    "subjectName": f"EXHIBIT // {ev_id} ({ev_item.get('source', 'ARCHIVE')})",
                },
                exact_frames=exact_frames,
                output_path=out_mp4,
            )

        elif engine == "REMOTION_TIMELINE_FLOW":
            self.remotion.render_composition(
                composition_id="TimelineComparison",
                props={
                    "mode": shot.get("timeline_mode", "flowchart"),
                    "arabicHeader": shot.get("text", "")[:55],
                },
                exact_frames=exact_frames,
                output_path=out_mp4,
            )

        else:
            self.remotion.render_composition(
                composition_id="DocumentScanner",
                props={
                    "documentTitle": ev_item.get("title", "DECLASSIFIED ARCHIVAL DOCUMENT"),
                    "archiveSource": ev_item.get("source", "NATIONAL ARCHIVES"),
                    "exhibitCode": f"EXHIBIT // {ev_id}",
                    "highlightedQuote": shot.get("highlighted_quote", ev_item.get("title", "FORENSIC EVIDENCE")),
                    "arabicTranslation": shot.get("text", "")[:65],
                },
                exact_frames=exact_frames,
                output_path=out_mp4,
            )

        log(f"🎞️ [{shot_id}] تم رندر المشهد بنجاح عبر المحرك [{engine}] ({exact_frames} إطار -> {out_mp4.name})")
        return out_mp4

    def assemble_master_documentary(
        self,
        directed_shots: List[Dict[str, Any]],
        evidence_manifest: Dict[str, Any],
        master_audio_path: Path,
    ) -> Path:
        log("🎬 [المرحلة 5] بدء الرندر الهجين للمشاهد والتجميع السينمائي النهائي...")
        evidence_lookup = {
            item["evidence_id"]: item for item in evidence_manifest.get("evidence", [])
        }

        rendered_clips: List[Path] = []
        for shot in directed_shots:
            clip_path = self.render_hybrid_shot(shot, evidence_lookup)
            rendered_clips.append(clip_path)

        ass_path = self.write_arabic_ass_subtitles(directed_shots, CONFIG.subtitles_ass_path)

        concat_file = CONFIG.workspace_dir / "shots_concat.txt"
        with open(concat_file, "w", encoding="utf-8") as f:
            for c_path in rendered_clips:
                f.write(f"file '{c_path.resolve()}'\n")

        raw_concat_mp4 = CONFIG.workspace_dir / "concat_raw.mp4"
        run_cmd([
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(concat_file),
            "-c", "copy",
            str(raw_concat_mp4),
        ])

        ass_escaped = str(ass_path.resolve()).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
        vf_chain = (
            f"subtitles='{ass_escaped}',"
            "eq=contrast=1.08:brightness=-0.01:saturation=0.88,"
            "noise=alls=7:allf=t+u,"
            "vignette=PI/5"
        )

        CONFIG.final_video_path.parent.mkdir(parents=True, exist_ok=True)
        res = run_cmd([
            "ffmpeg", "-y",
            "-i", str(raw_concat_mp4),
            "-i", str(master_audio_path),
            "-vf", vf_chain,
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
            "-c:a", "aac", "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            "-shortest",
            str(CONFIG.final_video_path),
        ], timeout=1800)

        if res.returncode != 0 or not is_valid_media(CONFIG.final_video_path):
            log("⚠️ إعادة التجميع بدون فلتر subtitles المباشر (Fallback)...", "warning")
            run_cmd([
                "ffmpeg", "-y",
                "-i", str(raw_concat_mp4),
                "-i", str(master_audio_path),
                "-vf", "eq=contrast=1.08:saturation=0.88,noise=alls=7:allf=t+u,vignette=PI/5",
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
                "-c:a", "aac", "-b:a", "192k",
                "-pix_fmt", "yuv420p",
                "-shortest",
                str(CONFIG.final_video_path),
            ], timeout=1800)

        self.generate_thumbnail(evidence_manifest)
        dur = probe_duration(CONFIG.final_video_path)
        sz_mb = CONFIG.final_video_path.stat().st_size / (1024 * 1024)
        log(f"🎉 اكتمل إنتاج الفيلم الوثائقي النهائي: {CONFIG.final_video_path} ({dur:.2f}s | {sz_mb:.2f} MB)")
        return CONFIG.final_video_path

    def generate_thumbnail(self, evidence_manifest: Dict[str, Any]) -> Path:
        img = Image.new("RGB", (TARGET_W, TARGET_H), (8, 10, 14))
        ev_list = evidence_manifest.get("evidence", [])
        if ev_list:
            first_ev = CONFIG.repo_root / ev_list[0].get("local_path", "")
            if first_ev.exists():
                try:
                    bg = Image.open(first_ev).convert("RGB").resize((TARGET_W, TARGET_H))
                    bg = ImageEnhance.Contrast(bg).enhance(1.4)
                    bg = ImageEnhance.Brightness(bg).enhance(0.55)
                    img = bg
                except Exception:
                    pass

        draw = ImageDraw.Draw(img)
        draw.rectangle([0, TARGET_H - 220, TARGET_W, TARGET_H], fill=(6, 8, 12))
        draw.rectangle([0, TARGET_H - 226, TARGET_W, TARGET_H - 220], fill=(229, 37, 33))
        draw.text((90, TARGET_H - 165), f"LEMMiNO FORENSIC DOSSIER // {CONFIG.topic.upper()}", fill=(255, 255, 255))
        img.save(CONFIG.thumbnail_path, "JPEG", quality=92)
        return CONFIG.thumbnail_path
