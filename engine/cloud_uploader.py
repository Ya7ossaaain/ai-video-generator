# -*- coding: utf-8 -*-
"""
engine/cloud_uploader.py
Uploads the final documentary MP4 and thumbnail to Google Drive (into DRIVE_FOLDER_ID)
and YouTube (privacyStatus='private') with chapter timestamps in the description.
"""

from pathlib import Path
from typing import List, Dict, Any
from engine.config import CONFIG
from engine.telemetry import log


class CloudUploader:
    def __init__(self):
        self.client_id = CONFIG.google_client_id
        self.client_secret = CONFIG.google_client_secret
        self.refresh_token = CONFIG.google_refresh_token
        self.drive_folder_id = CONFIG.drive_folder_id

    def _build_credentials(self):
        if not (self.client_id and self.client_secret and self.refresh_token):
            return None
        from google.oauth2.credentials import Credentials
        return Credentials(
            None,
            refresh_token=self.refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self.client_id,
            client_secret=self.client_secret,
        )

    def format_chapter_timestamps(self, script_data: Dict[str, Any], shots: List[Dict[str, Any]]) -> str:
        chapter_starts: Dict[int, float] = {1: 0.0}
        for s in shots:
            ch = int(s.get("chapter_number", 1))
            if ch not in chapter_starts:
                chapter_starts[ch] = float(s.get("start", 0.0))

        lines = [
            f"تحقيق وثائقي استقصائي: {script_data.get('title_ar', CONFIG.topic)}",
            f"الحقبة الزمنية: {script_data.get('target_era', '1971')} | الإحداثيات: {script_data.get('primary_coordinates', '')}",
            "",
            "الفصول الزمنية (Chapters):",
        ]
        for ch in script_data.get("chapters", []):
            c_num = int(ch.get("chapter_number", 1))
            sec = int(chapter_starts.get(c_num, 0.0))
            mm, ss = divmod(sec, 60)
            hh, mm = divmod(mm, 60)
            ts = f"{hh:02d}:{mm:02d}:{ss:02d}" if hh > 0 else f"{mm:02d}:{ss:02d}"
            lines.append(f"{ts} - {ch.get('title_ar', f'الفصل {c_num}')}")

        lines.append("\n#وثائقي #تحقيقات_جنائية #LEMMiNO")
        return "\n".join(lines)

    def upload(
        self,
        video_path: Path,
        thumbnail_path: Path,
        script_data: Dict[str, Any],
        shots: List[Dict[str, Any]],
    ) -> Dict[str, str]:
        results = {"drive_url": "", "youtube_url": ""}
        creds = self._build_credentials()
        if not creds:
            log("ℹ️ بيانات اعتماد Google OAuth2 غير متوفرة في المتغيرات البيئية؛ تخطي الرفع السحابي.", "info")
            return results

        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload

        title = script_data.get("title_ar") or CONFIG.topic
        description = self.format_chapter_timestamps(script_data, shots)

        try:
            drive_service = build("drive", "v3", credentials=creds, cache_discovery=False)
            file_metadata: Dict[str, Any] = {"name": f"{CONFIG.topic_clean}.mp4"}
            if self.drive_folder_id:
                file_metadata["parents"] = [self.drive_folder_id]

            media = MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True)
            created = drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields="id",
            ).execute()
            file_id = created.get("id", "")
            if file_id:
                results["drive_url"] = f"https://drive.google.com/file/d/{file_id}/view"
                log(f"☁️ تم رفع الفيلم بنجاح إلى Google Drive: {results['drive_url']}")
        except Exception as exc:
            log(f"⚠️ تعذر الرفع إلى Google Drive: {exc}", "warning")

        try:
            yt_service = build("youtube", "v3", credentials=creds, cache_discovery=False)
            body = {
                "snippet": {
                    "title": title[:95],
                    "description": description,
                    "tags": ["وثائقي", "تحقيقات", "غموض", "أدلة جنائية", "LEMMiNO"],
                    "categoryId": "27",
                },
                "status": {
                    "privacyStatus": "private",
                    "selfDeclaredMadeForKids": False,
                },
            }
            media_yt = MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True)
            yt_resp = yt_service.videos().insert(
                part="snippet,status",
                body=body,
                media_body=media_yt,
            ).execute()
            vid_id = yt_resp.get("id", "")
            if vid_id:
                results["youtube_url"] = f"https://youtu.be/{vid_id}"
                log(f"📺 تم رفع الفيلم بنجاح إلى YouTube (Private): {results['youtube_url']}")

                if thumbnail_path.exists() and thumbnail_path.stat().st_size > 1024:
                    try:
                        yt_service.thumbnails().set(
                            videoId=vid_id,
                            media_body=MediaFileUpload(str(thumbnail_path), mimetype="image/jpeg"),
                        ).execute()
                        log("🖼️ تم تعيين الصورة المصغرة على YouTube بنجاح.")
                    except Exception as thumb_err:
                        log(f"⚠️ تعذر رفع الصورة المصغرة إلى YouTube: {thumb_err}", "warning")
        except Exception as exc:
            log(f"⚠️ تعذر الرفع إلى YouTube: {exc}", "warning")

        return results
