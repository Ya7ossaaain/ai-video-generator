import os
import sys
import glob
import json
import struct
import zlib
import subprocess

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

def analyze_png_image(filepath):
    """تحليل سريع لملف PNG باستخدام مكتبات بايثون القياسية أو Pillow إن توفرت."""
    try:
        from PIL import Image
        img = Image.open(filepath).convert("RGB")
        w, h = img.size
        pixels = list(img.getdata())
        total = len(pixels)
        bright_white = sum(1 for r, g, b in pixels if r > 180 and g > 180 and b > 180)
        cooper_red   = sum(1 for r, g, b in pixels if r > 150 and g < 70 and b < 70)
        non_black    = sum(1 for r, g, b in pixels if (r + g + b) > 45)
        return {
            "valid": True,
            "width": w,
            "height": h,
            "white_ratio": round(bright_white / total, 5),
            "red_ratio": round(cooper_red / total, 5),
            "non_black_ratio": round(non_black / total, 5),
            "is_black_frame": (non_black / total) < 0.0005
        }
    except ImportError:
        # في حال عدم تثبيت Pillow نتحقق من أبعاد وهيدر PNG عبر struct
        with open(filepath, "rb") as f:
            data = f.read(32)
        if len(data) < 24 or data[:8] != b'\x89PNG\r\n\x1a\n':
            return {"valid": False, "is_black_frame": True}
        w, h = struct.unpack(">II", data[16:24])
        fsize = os.path.getsize(filepath)
        return {
            "valid": True,
            "width": w,
            "height": h,
            "file_size_bytes": fsize,
            "is_black_frame": fsize < 4500
        }

def assemble_video_ffmpeg(frames_dir, output_mp4, fps=24):
    """تجميع الإطارات المصيرة إلى ملف MP4 متوافق مع جميع المشغلات، وإنشاء Contact Sheet."""
    frame_files = sorted(glob.glob(os.path.join(frames_dir, "frame_*.png")))
    if not frame_files:
        print("[Verifier] No rendered animation frames found in", frames_dir)
        return False

    os.makedirs(os.path.dirname(output_mp4), exist_ok=True)
    # استخدام glob/concat لضمان العمل حتى لو كان frame_step > 1 أثناء الاختبار السريع
    concat_list_path = os.path.join(frames_dir, "ffmpeg_frames.txt")
    frame_duration = 1.0 / fps
    if len(frame_files) > 1:
        # حساب الفرق بين أرقام الإطارات لتعويض frame_step تلقائيًا والحفاظ على مدة 36 ثانية
        f1 = int(os.path.basename(frame_files[0]).split("_")[1].split(".")[0])
        f2 = int(os.path.basename(frame_files[1]).split("_")[1].split(".")[0])
        step = max(1, f2 - f1)
        frame_duration = step / float(fps)

    with open(concat_list_path, "w", encoding="utf-8") as f:
        for fp in frame_files:
            f.write(f"file '{os.path.abspath(fp)}'\n")
            f.write(f"duration {frame_duration:.6f}\n")
        f.write(f"file '{os.path.abspath(frame_files[-1])}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", concat_list_path,
        "-vf", f"fps={fps},format=yuv420p",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-movflags", "+faststart",
        output_mp4
    ]
    print("[Verifier] Encoding MP4 via FFmpeg...")
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        print("[Verifier] FFmpeg Error:", res.stderr)
        return False
    return os.path.isfile(output_mp4) and os.path.getsize(output_mp4) > 10000

def build_contact_sheet(samples_dir):
    sample_files = sorted(glob.glob(os.path.join(samples_dir, "sample_*.png")))
    if len(sample_files) < 4:
        return None
    sheet_path = os.path.join(samples_dir, "contact_sheet.png")
    inputs = []
    for s in sample_files[:8]:
        inputs.extend(["-i", s])
    n = min(8, len(sample_files))
    filter_str = "".join([f"[{i}:v]scale=640:360[v{i}];" for i in range(n)])
    filter_str += "".join([f"[v{i}]" for i in range(n)]) + f"xstack=inputs={n}:layout=0_0|w0_0|0_h0|w0_h0|0_h0+h0|w0_h0+h0|0_h0+h0+h0|w0_h0+h0+h0[out]"
    cmd = ["ffmpeg", "-y"] + inputs + ["-filter_complex", filter_str, "-map", "[out]", sheet_path]
    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return sheet_path if os.path.isfile(sheet_path) else None

def main():
    with open(os.path.join(PROJECT_ROOT, "config.json"), "r", encoding="utf-8") as f:
        config = json.load(f)

    samples_dir = os.path.join(PROJECT_ROOT, config["paths"]["samples_dir"])
    frames_dir  = os.path.join(PROJECT_ROOT, config["paths"]["frames_dir"])
    output_mp4  = os.path.join(PROJECT_ROOT, config["paths"]["final_video"])
    report_path = os.path.join(PROJECT_ROOT, config["paths"]["report_file"])

    report = {"samples": {}, "black_frames_detected": [], "video_assembled": False, "status": "PENDING"}

    for s_file in sorted(glob.glob(os.path.join(samples_dir, "sample_*.png"))):
        name = os.path.basename(s_file)
        stats = analyze_png_image(s_file)
        report["samples"][name] = stats
        if stats.get("is_black_frame"):
            report["black_frames_detected"].append(name)

    contact_sheet = build_contact_sheet(samples_dir)
    if contact_sheet:
        report["contact_sheet"] = contact_sheet

    if glob.glob(os.path.join(frames_dir, "frame_*.png")):
        ok = assemble_video_ffmpeg(frames_dir, output_mp4, fps=config["profiles"][config["active_profile"]]["fps"])
        report["video_assembled"] = ok
        report["final_video_path"] = output_mp4 if ok else None

    report["status"] = "PASSED" if not report["black_frames_detected"] else "WARNING_BLACK_FRAMES"
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(json.dumps(report, indent=2))
    if report["status"] != "PASSED":
        sys.exit(1)

if __name__ == "__main__":
    main()