# -*- coding: utf-8 -*-
"""
engine/visual_director.py
Stage 4: Hybrid Visual Director (AGY Calls #2 and #3, effort="medium").
"""

import json
from typing import List, Dict, Any
from engine.config import CONFIG
from engine.telemetry import log
from engine.agy_client import AGY_CLIENT

VALID_ENGINES = [
    "BLENDER_WIREFRAME_HUD",
    "BLENDER_25D_PARALLAX",
    "BLENDER_TERRAIN_MAP",
    "REMOTION_VECTOR_MAP",
    "REMOTION_DOSSIER_GRID",
    "REMOTION_TIMELINE_FLOW",
    "EVIDENCE_MACRO_SCANNER",
]


class VisualDirector:
    def load_models_catalog(self) -> Dict[str, Any]:
        if CONFIG.models_catalog_path.exists():
            with open(CONFIG.models_catalog_path, "r", encoding="utf-8") as f:
                return json.load(f).get("models", {})
        return {}

    def direct_scenes(
        self,
        shots: List[Dict[str, Any]],
        evidence_manifest: Dict[str, Any],
        script_data: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        log("🎬 [المرحلة 4] بدء الإخراج البصري الهجين وتوزيع المشاهد (AGY Calls #2 & #3)...")
        models_catalog = self.load_models_catalog()
        evidence_items = evidence_manifest.get("evidence", [])
        evidence_ids = [e["evidence_id"] for e in evidence_items] or ["EV_001"]
        model_ids = list(models_catalog.keys()) or ["commercial_airliner"]

        models_summary = "\n".join([
            f"- {m_id}: {m_info.get('description', '')} | sub_parts={m_info.get('sub_parts', [])}"
            for m_id, m_info in models_catalog.items()
        ])
        evidence_summary = "\n".join([
            f"- {e['evidence_id']}: {e['title']} ({e['source']})"
            for e in evidence_items[:20]
        ])

        mid = max(1, (len(shots) + 1) // 2)
        batches = [shots[:mid], shots[mid:]] if len(shots) > 1 else [shots]

        directed_shots: List[Dict[str, Any]] = []

        for b_idx, batch in enumerate(batches, start=1):
            if not batch:
                continue
            shots_digest = "\n".join([
                f"- {s['shot_id']} (frames={s['exact_frames']}, ch={s.get('chapter_number', 1)}): {s['text']}"
                for s in batch
            ])

            prompt = f"""You are the Visual Director for a LEMMiNO-style investigative documentary engine.
Do NOT write any code. Return ONLY a valid JSON object mapping each shot_id to its visual engine and parameters.

TARGET DISTRIBUTION ACROSS THE EPISODE:
- ~30% 3D Hybrid scenes:
  * "BLENDER_WIREFRAME_HUD" (select `model_id` and `highlight_part` from MODELS CATALOG below, plus `style`: "wireframe" or "clay", and `hud_label`)
  * "BLENDER_25D_PARALLAX" (select `evidence_id` from EVIDENCE MANIFEST below, plus `particles`: "dust", "snow", or "embers")
  * "BLENDER_TERRAIN_MAP" (`terrain_mode`: "terrain" or "ocean", `coordinates`: "{evidence_manifest.get('primary_coordinates', '45.92° N, 122.28° W')}")
- ~60% Motion Graphics & GIS Data scenes:
  * "REMOTION_VECTOR_MAP" (`map_title`, `coordinates`, `sector_code`)
  * "REMOTION_DOSSIER_GRID" (`dossier_mode`: "suspect" or "grid", `evidence_id`, `subject_name`)
  * "REMOTION_TIMELINE_FLOW" (`timeline_mode`: "flowchart" or "comparison", `era_label`)
- ~10% Focal Archival Evidence Scanner:
  * "EVIDENCE_MACRO_SCANNER" (`evidence_id`, `highlighted_quote`, `exhibit_code`)

AVAILABLE 3D MODELS CATALOG (`assets/models/models_catalog.json`):
{models_summary}

AVAILABLE FORENSIC EVIDENCE MANIFEST (`workspace/evidence_manifest.json`):
{evidence_summary}

SHOTS BATCH #{b_idx}:
{shots_digest}

Return ONLY valid JSON:
{{
  "SHOT_001": {{
    "engine": "BLENDER_WIREFRAME_HUD",
    "model_id": "commercial_airliner",
    "highlight_part": "aft_stairs",
    "style": "wireframe",
    "evidence_id": "EV_001",
    "hud_label": "BOEING 727-100 // VENTRAL AIRSTAIRS",
    "highlighted_quote": "FLIGHT 305 // 20:13 PST"
  }}
}}"""

            ai_plan = AGY_CLIENT.call_json(
                prompt=prompt,
                effort_level="medium",
                purpose=f"stage4_visual_director_batch_{b_idx}",
            )
            if not isinstance(ai_plan, dict):
                ai_plan = {}

            for s in batch:
                sid = s["shot_id"]
                idx0 = s["index"] - 1
                raw_cfg = ai_plan.get(sid) if isinstance(ai_plan.get(sid), dict) else {}
                normalized_shot = self._normalize_shot_directive(
                    shot=s,
                    raw_cfg=raw_cfg,
                    idx0=idx0,
                    models_catalog=models_catalog,
                    model_ids=model_ids,
                    evidence_ids=evidence_ids,
                    primary_coords=evidence_manifest.get("primary_coordinates", "45.9214° N, 122.2819° W"),
                )
                directed_shots.append(normalized_shot)

        with open(CONFIG.visual_plan_path, "w", encoding="utf-8") as f:
            json.dump(
                {"total_shots": len(directed_shots), "shots": directed_shots},
                f,
                indent=2,
                ensure_ascii=False,
            )

        self._log_distribution(directed_shots)
        return directed_shots

    def _normalize_shot_directive(
        self,
        shot: Dict[str, Any],
        raw_cfg: Dict[str, Any],
        idx0: int,
        models_catalog: Dict[str, Any],
        model_ids: List[str],
        evidence_ids: List[str],
        primary_coords: str,
    ) -> Dict[str, Any]:
        pattern_10 = [
            "BLENDER_WIREFRAME_HUD",
            "REMOTION_VECTOR_MAP",
            "REMOTION_DOSSIER_GRID",
            "BLENDER_25D_PARALLAX",
            "REMOTION_TIMELINE_FLOW",
            "REMOTION_VECTOR_MAP",
            "BLENDER_TERRAIN_MAP",
            "REMOTION_DOSSIER_GRID",
            "REMOTION_TIMELINE_FLOW",
            "EVIDENCE_MACRO_SCANNER",
        ]

        engine = str(raw_cfg.get("engine", "")).strip().upper()
        if engine not in VALID_ENGINES:
            engine = pattern_10[idx0 % len(pattern_10)]

        default_models_cycle = [
            ("commercial_airliner", "aft_stairs"),
            ("briefcase_cash", "cash_bundles"),
            ("parachute_rig", "canopy_dome"),
            ("radar_station", "parabolic_dish"),
            ("investigation_dossier", "red_stamp_tab"),
            ("helicopter", "searchlight"),
            ("pocket_watch", "hour_hand"),
            ("forensic_microscope", "objective_turret"),
        ]
        def_m, def_part = default_models_cycle[idx0 % len(default_models_cycle)]

        model_id = str(raw_cfg.get("model_id", "")).strip()
        if model_id not in models_catalog:
            model_id = def_m if def_m in models_catalog else model_ids[idx0 % len(model_ids)]

        sub_parts = models_catalog.get(model_id, {}).get("sub_parts", [])
        highlight_part = str(raw_cfg.get("highlight_part", "")).strip()
        if highlight_part not in sub_parts:
            highlight_part = def_part if def_part in sub_parts else (sub_parts[0] if sub_parts else "body")

        ev_id = str(raw_cfg.get("evidence_id", "")).strip()
        if ev_id not in evidence_ids:
            ev_id = evidence_ids[idx0 % len(evidence_ids)]

        enriched = dict(shot)
        enriched.update({
            "engine": engine,
            "model_id": model_id,
            "highlight_part": highlight_part,
            "style": "clay" if idx0 % 3 == 1 else "wireframe",
            "evidence_id": ev_id,
            "particles": ["dust", "snow", "embers"][idx0 % 3],
            "terrain_mode": "ocean" if idx0 % 2 == 1 else "terrain",
            "coordinates": str(raw_cfg.get("coordinates") or primary_coords),
            "dossier_mode": "grid" if idx0 % 2 == 1 else "suspect",
            "timeline_mode": "comparison" if idx0 % 2 == 1 else "flowchart",
            "hud_label": str(raw_cfg.get("hud_label") or f"{model_id.upper()} // {highlight_part.upper()}"),
            "highlighted_quote": str(raw_cfg.get("highlighted_quote") or "DECLASSIFIED FORENSIC TELETYPE RECORD"),
        })
        return enriched

    def _log_distribution(self, shots: List[Dict[str, Any]]):
        total = max(1, len(shots))
        c_3d = sum(1 for s in shots if s["engine"].startswith("BLENDER_"))
        c_rem = sum(1 for s in shots if s["engine"].startswith("REMOTION_"))
        c_scan = sum(1 for s in shots if s["engine"] == "EVIDENCE_MACRO_SCANNER")
        log(
            f"📊 توزيع المشاهد الهجين ({len(shots)} مشهد): "
            f"3D={c_3d} ({c_3d*100/total:.0f}%) | "
            f"Remotion={c_rem} ({c_rem*100/total:.0f}%) | "
            f"Evidence Scanner={c_scan} ({c_scan*100/total:.0f}%)"
        )
