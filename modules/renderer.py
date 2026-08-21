# modules/renderer.py
import os
import re
import cv2
import numpy as np
from PIL import Image, ImageDraw
import config
from modules.comment_engine import get_system_font, render_crisp_comment_card
from modules.ocr_detector import is_subtitle_overlapping

try:
    from moviepy.editor import VideoFileClip, ImageClip, CompositeVideoClip, concatenate_videoclips
except ImportError:
    from moviepy import VideoFileClip, ImageClip, CompositeVideoClip, concatenate_videoclips

def safe_set_pos(clip, pos):
    if hasattr(clip, "with_position"):
        return clip.with_position(pos)
    return clip.set_position(pos)

def safe_set_dur(clip, dur):
    if hasattr(clip, "with_duration"):
        return clip.with_duration(dur)
    return clip.set_duration(dur)

def safe_set_start(clip, start_t):
    if hasattr(clip, "with_start"):
        return clip.with_start(start_t)
    return clip.set_start(start_t)

def safe_subclip(clip, st_t, et_t):
    if hasattr(clip, "subclipped"):
        return clip.subclipped(st_t, et_t)
    return clip.subclip(st_t, et_t)

def safe_resize(clip, size):
    if hasattr(clip, "resized"):
        return clip.resized(size)
    return clip.resize(size)

def wrap_text(text, font, max_width, draw):
    lines = []
    words = text.split(" ")
    curr_line = ""
    for w in words:
        test_line = curr_line + (" " if curr_line else "") + w
        bbox = draw.textbbox((0, 0), test_line, font=font)
        if (bbox[2] - bbox[0]) <= max_width:
            curr_line = test_line
        else:
            if curr_line:
                lines.append(curr_line)
            curr_line = w
    if curr_line:
        lines.append(curr_line)
    return lines

def auto_detect_video_boundary(clip, duration, *args, **kwargs):
    try:
        sample_times = [duration * 0.2, duration * 0.5, duration * 0.8]
        top_candidates, bottom_candidates = [], []
        for t in sample_times:
            frame = clip.get_frame(t)
            h, _, _ = frame.shape
            gray = np.dot(frame[..., :3], [0.2989, 0.5870, 0.1140])
            row_means = np.mean(gray, axis=1)
            row_diffs = np.abs(np.diff(row_means))
            
            search_top_start, search_top_end = int(h * 0.15), int(h * 0.45)
            peak_top = search_top_start + np.argmax(row_diffs[search_top_start:search_top_end])
            top_candidates.append(int(peak_top * (1920 / h)))
            
            search_bot_start, search_bot_end = int(h * 0.65), int(h * 0.90)
            peak_bot = search_bot_start + np.argmax(row_diffs[search_bot_start:search_bot_end])
            bottom_candidates.append(int(peak_bot * (1920 / h)))
            
        final_top = max(350, min(650, int(np.median(top_candidates))))
        final_bottom = max(1250, min(1650, int(np.median(bottom_candidates))))
        return final_top, final_bottom
    except Exception:
        return 480, 1440

def generate_layout_preview_image(video_path, is_vertical=False, v_top=656, v_bottom=1264, zoom_factor=1.0, sample_time=10.0, out_path="layout_preview.png", *args, **kwargs):
    if not os.path.exists(video_path):
        return None
    try:
        clip = VideoFileClip(video_path)
        actual_t = min(sample_time, max(0.5, clip.duration - 1.0))
        frame = clip.get_frame(actual_t)
        clip.close()

        frame_h, frame_w, _ = frame.shape
        raw_img = Image.fromarray(frame).convert("RGBA")
        canvas = Image.new("RGBA", (1080, 1920), (14, 14, 16, 255))
        draw = ImageDraw.Draw(canvas)

        if not is_vertical:
            scaled_w = int(1080 * float(zoom_factor))
            scaled_h = int(frame_h * (1080 / frame_w) * float(zoom_factor))
            resized_frame = raw_img.resize((scaled_w, scaled_h))
            
            crop_x = max(0, (scaled_w - 1080) // 2)
            cropped_frame = resized_frame.crop((crop_x, 0, crop_x + 1080, scaled_h))
            y_offset = max(0, (1920 - scaled_h) // 2)
            canvas.paste(cropped_frame, (0, y_offset))

            draw.rectangle([0, 0, 1080, v_top], fill=(14, 14, 16, 245))
            font_title = get_system_font(42, bold=True)
            draw.text((60, v_top // 2 - 25), "🔥 [상단 가림막] 초대형 후킹 타이틀", fill=(255, 220, 40, 255), font=font_title)
            draw.line([(0, v_top), (1080, v_top)], fill=(0, 255, 150, 255), width=4)

            sub_y = v_bottom - 95
            draw.rounded_rectangle([120, sub_y, 960, sub_y + 60], radius=14, fill=(0, 0, 0, 190))
            font_sub = get_system_font(30, bold=True)
            draw.text((150, sub_y + 12), "💬 [OCR 연동] 기존 자막 피해서 펀치라인 출력", fill=(255, 235, 40, 255), font=font_sub)

            draw.rectangle([0, v_bottom, 1080, 1920], fill=(14, 14, 16, 245))
            draw.line([(0, v_bottom), (1080, v_bottom)], fill=(0, 255, 150, 255), width=4)
            
            bottom_h = 1920 - v_bottom
            card_prev_y = v_bottom + max(15, (bottom_h - 190) // 2)
            draw.rounded_rectangle([120, card_prev_y, 960, card_prev_y + 190], radius=18, fill=(28, 28, 32, 240), outline=(255, 255, 255, 40), width=2)
            font_cmt = get_system_font(28, bold=True)
            draw.text((160, card_prev_y + 75), "💬 [하단 가림막] 유튜브 베스트 댓글", fill=(240, 240, 240, 255), font=font_cmt)
        else:
            resized_frame = raw_img.resize((1080, 1920))
            canvas.paste(resized_frame, (0, 0))
            draw.rectangle([0, 0, 1080, v_top], fill=(14, 14, 16, 230))
            draw.rectangle([0, v_bottom, 1080, 1920], fill=(14, 14, 16, 230))

        img_disp = canvas.resize((360, 640))
        img_disp.save(out_path)
        return out_path
    except Exception:
        return None

def create_base_overlay(title: str, source: str, is_white: bool, is_vertical: bool, v_top: int, v_bottom: int, out_path: str = "base_banner.png", *args, **kwargs):
    w, h = config.SHORTS_WIDTH, config.SHORTS_HEIGHT
    mask_bg = (248, 248, 250, 255) if is_white else (14, 14, 16, 255)
    highlight_color = (220, 38, 38, 255) if is_white else (255, 220, 40, 255)
    outline_c = (255, 255, 255, 255) if is_white else (0, 0, 0, 255)

    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, w, v_top], fill=mask_bg)
    draw.rectangle([0, v_bottom, w, h], fill=mask_bg)

    font_title = get_system_font(74, bold=True)
    lines = wrap_text(title, font_title, 960, draw)
    line_h = 86
    total_h = len(lines) * line_h
    start_y = max(35, (v_top - total_h) // 2 - 15)

    for line in lines:
        txt_w = draw.textbbox((0, 0), line, font=font_title)[2]
        tx = (w - txt_w) // 2
        for ox in range(-3, 4):
            for oy in range(-3, 4):
                if ox*ox + oy*oy <= 9:
                    draw.text((tx + ox, start_y + oy), line, fill=outline_c, font=font_title)
        draw.text((tx, start_y), line, fill=highlight_color, font=font_title)
        start_y += line_h

    if source and source.strip():
        font_src = get_system_font(24, bold=True)
        draw.text((60, v_top - 42), f"출처: {source.strip()}", fill=(150, 150, 150, 255), font=font_src)

    img.save(out_path)
    return out_path

def render_final_shorts_video(
    source_video_path: str,
    segments_plan: list,
    subtitle_chunks: list,
    clip_info: dict,
    real_source: str,
    template_name: str,
    accel_engine: str,
    out_dir: str,
    index: int,
    is_vertical: bool = False,
    v_top: int = 656,
    v_bottom: int = 1264,
    zoom_factor: float = 1.0,
    custom_sub_text: str = None,
    *args,
    **kwargs
):
    raw_video = VideoFileClip(source_video_path)
    is_white = "화이트" in template_name
    
    video_clips = []
    timeline_offset = 0.0
    segment_mappings = []

    for seg in segments_plan:
        st_t = seg["source_start"]
        en_t = seg["source_end"]
        sub_clip = safe_subclip(raw_video, st_t, en_t)
        try:
            sub_clip = sub_clip.audio_fadein(0.05).audio_fadeout(0.05)
        except Exception:
            pass
        video_clips.append(sub_clip)
        
        seg_dur = en_t - st_t
        segment_mappings.append((st_t, en_t, timeline_offset, timeline_offset + seg_dur))
        timeline_offset += seg_dur

    assembled_video = concatenate_videoclips(video_clips, method="compose")
    total_dur = assembled_video.duration

    if not is_vertical:
        scaled_w = int(1080 * float(zoom_factor))
        scaled_h = int(assembled_video.size[1] * (1080 / assembled_video.size[0]) * float(zoom_factor))
        resized_v = safe_resize(assembled_video, (scaled_w, scaled_h))
        
        if float(zoom_factor) > 1.001:
            crop_x1 = max(0, (scaled_w - 1080) // 2)
            try:
                resized_v = resized_v.cropped(x1=crop_x1, y1=0, x2=crop_x1 + 1080, y2=scaled_h)
            except Exception:
                resized_v = resized_v.crop(x1=crop_x1, y1=0, x2=crop_x1 + 1080, y2=scaled_h)
                
        y_offset = (1920 - scaled_h) // 2
        positioned_video = safe_set_pos(resized_v, (0, y_offset))
    else:
        positioned_video = safe_set_pos(safe_resize(assembled_video, (1080, 1920)), (0, 0))

    base_bg_path = os.path.join(out_dir, f"base_bg_{index}.png")
    create_base_overlay(
        title=clip_info.get("title", "하이라이트"),
        source=real_source,
        is_white=is_white,
        is_vertical=is_vertical,
        v_top=v_top,
        v_bottom=v_bottom,
        out_path=base_bg_path
    )
    bg_clip = safe_set_dur(safe_set_pos(ImageClip(base_bg_path), (0, 0)), total_dur)
    layers = [positioned_video, bg_clip]

    # 1. 실제 유튜브 베스트 댓글 카드 (하단 가림막 영역 정중앙 단독 배치)
    matched_comment = clip_info.get("matched_comment", {})
    special_event = clip_info.get("special_event", {})
    if config.ENABLE_COMMENTS and matched_comment:
        event_src_end = float(special_event.get("event_end", clip_info.get("climax_end", 0.0)))
        target_comment_time = None
        for src_s, src_e, tgt_s, tgt_e in segment_mappings:
            if src_s <= event_src_end <= src_e:
                offset = event_src_end - src_s
                target_comment_time = tgt_s + offset + config.COMMENT_DELAY_AFTER_EVENT
                break
                
        if target_comment_time is None or target_comment_time >= total_dur:
            target_comment_time = 0.5

        raw_card_file = os.path.join(out_dir, f"raw_card_{index}.png")
        render_crisp_comment_card(
            author=matched_comment.get("author", "베플러"),
            text=matched_comment.get("text", "대박 ㅋㅋㅋ"),
            likes=str(matched_comment.get("likes", "1.2만")),
            is_white=is_white,
            out_path=raw_card_file
        )
        
        card_img = Image.open(raw_card_file).convert("RGBA")
        full_comment_canvas = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
        
        bottom_area_h = 1920 - v_bottom
        safe_comment_y = v_bottom + max(15, (bottom_area_h - 190) // 2)
        safe_comment_y = min(1920 - 200, safe_comment_y)
        
        full_comment_canvas.paste(card_img, (120, safe_comment_y), card_img)
        
        c_full_file = os.path.join(out_dir, f"comment_full_{index}.png")
        full_comment_canvas.save(c_full_file)
        
        c_dur = min(config.COMMENT_MAX_DURATION, total_dur - target_comment_time)
        c_clip = safe_set_dur(safe_set_start(safe_set_pos(ImageClip(c_full_file), (0, 0)), target_comment_time), c_dur)
        layers.append(c_clip)

    # 2. 핵심 펀치라인 자막 (OCR 연동: 기존 자막과 겹치면 자동 스킵)
    font_sub = get_system_font(46, bold=True)
    key_subs = clip_info.get("key_subtitles", [])

    if custom_sub_text and custom_sub_text.strip():
        lines_custom = [l.strip() for l in custom_sub_text.strip().splitlines() if l.strip()]
        if lines_custom:
            dur_per_line = max(1.8, total_dur / len(lines_custom))
            for l_idx, txt in enumerate(lines_custom):
                mapped_start = l_idx * dur_per_line
                if mapped_start >= total_dur:
                    break
                dur = min(dur_per_line, total_dur - mapped_start)
                
                # 원본 영상 프레임 샘플링 후 OCR로 기존 자막 겹침 검사
                check_t = min(raw_video.duration - 0.1, segments_plan[0]["source_start"] + mapped_start + 0.3)
                sample_frame = raw_video.get_frame(check_t)
                frame_bgr = cv2.cvtColor(sample_frame, cv2.COLOR_RGB2BGR)
                
                if is_subtitle_overlapping(txt, frame_bgr):
                    continue  # 기존 방송/유튜브 자막과 겹치면 우리 자막 스킵!

                sub_img = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
                draw_sub = ImageDraw.Draw(sub_img)
                lines = wrap_text(txt, font_sub, 900, draw_sub)
                
                sy = max(v_top + 80, v_bottom - 110 - (len(lines) - 1) * 60)
                for ln in lines:
                    txt_w = draw_sub.textbbox((0, 0), ln, font=font_sub)[2]
                    sx = (1080 - txt_w) // 2
                    draw_sub.rounded_rectangle([sx - 18, sy - 8, sx + txt_w + 18, sy + 54], radius=12, fill=(0, 0, 0, 185))
                    for ox in range(-3, 4):
                        for oy in range(-3, 4):
                            if ox*ox + oy*oy <= 9:
                                draw_sub.text((sx + ox, sy + oy), ln, fill=(0, 0, 0, 255), font=font_sub)
                    draw_sub.text((sx, sy), ln, fill=(255, 235, 40, 255), font=font_sub)
                    sy += 60
                    
                s_file = os.path.join(out_dir, f"sub_c_{index}_{l_idx}.png")
                sub_img.save(s_file)
                layers.append(safe_set_dur(safe_set_start(safe_set_pos(ImageClip(s_file), (0, 0)), mapped_start), dur))

    elif key_subs and len(key_subs) > 0:
        for k_idx, k_sub in enumerate(key_subs):
            k_st, k_et, k_txt = float(k_sub.get("start", 0)), float(k_sub.get("end", 0)), k_sub.get("text", "").strip()
            if not k_txt:
                continue
                
            for src_s, src_e, tgt_s, tgt_e in segment_mappings:
                if not (k_et <= src_s or k_st >= src_e):
                    rel_s = max(0.0, k_st - src_s)
                    dur = min(k_et, src_e) - max(k_st, src_s)
                    if dur > 0.3:
                        mapped_start = tgt_s + rel_s
                        
                        check_t = min(raw_video.duration - 0.1, k_st + 0.3)
                        sample_frame = raw_video.get_frame(check_t)
                        frame_bgr = cv2.cvtColor(sample_frame, cv2.COLOR_RGB2BGR)
                        
                        if is_subtitle_overlapping(k_txt, frame_bgr):
                            continue # 기존 자막과 겹치면 스킵

                        sub_img = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
                        draw_sub = ImageDraw.Draw(sub_img)
                        lines = wrap_text(k_txt, font_sub, 900, draw_sub)
                        
                        sy = max(v_top + 80, v_bottom - 110 - (len(lines) - 1) * 60)
                        for ln in lines:
                            txt_w = draw_sub.textbbox((0, 0), ln, font=font_sub)[2]
                            sx = (1080 - txt_w) // 2
                            draw_sub.rounded_rectangle([sx - 18, sy - 8, sx + txt_w + 18, sy + 54], radius=12, fill=(0, 0, 0, 185))
                            for ox in range(-3, 4):
                                for oy in range(-3, 4):
                                    if ox*ox + oy*oy <= 9:
                                        draw_sub.text((sx + ox, sy + oy), ln, fill=(0, 0, 0, 255), font=font_sub)
                            draw_sub.text((sx, sy), ln, fill=(255, 235, 40, 255), font=font_sub)
                            sy += 60
                            
                        s_file = os.path.join(out_dir, f"sub_k_{index}_{k_idx}.png")
                        sub_img.save(s_file)
                        layers.append(safe_set_dur(safe_set_start(safe_set_pos(ImageClip(s_file), (0, 0)), mapped_start), dur))

    final_comp = CompositeVideoClip(layers, size=(1080, 1920))
    final_output_path = os.path.join(out_dir, f"shorts_master_{index}.mp4")

    if "NVIDIA" in accel_engine:
        codec = "h264_nvenc"
        ffmpeg_params = ["-preset", "p5", "-cq", "19", "-pix_fmt", "yuv420p"]
    elif "Intel" in accel_engine:
        codec = "h264_qsv"
        ffmpeg_params = ["-preset", "veryfast", "-global_quality", "20", "-pix_fmt", "yuv420p"]
    elif "AMD" in accel_engine:
        codec = "h264_amf"
        ffmpeg_params = ["-quality", "quality", "-rc", "cbr", "-pix_fmt", "yuv420p"]
    else:
        codec = "libx264"
        ffmpeg_params = ["-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p"]

    try:
        final_comp.write_videofile(
            final_output_path,
            codec=codec,
            audio_codec="aac",
            fps=config.TARGET_FPS,
            threads=4,
            ffmpeg_params=ffmpeg_params
        )
    except Exception:
        final_comp.write_videofile(
            final_output_path,
            codec="libx264",
            audio_codec="aac",
            fps=config.TARGET_FPS,
            threads=4,
            preset="ultrafast"
        )

    raw_video.close()
    return final_output_path