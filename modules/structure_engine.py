# modules/structure_engine.py
import config

def build_shorts_timeline_plan(clip_info, total_video_duration: float, *args, **kwargs):
    struct_type = clip_info.get("recommended_structure", "Structure_C")
    climax_start = float(clip_info.get("climax_start", 0.0))
    climax_end = float(clip_info.get("climax_end", climax_start + 4.0))
    context_start = float(clip_info.get("context_start", max(0.0, climax_start - 2.0)))
    context_end = float(clip_info.get("context_end", min(total_video_duration, climax_end + 3.0)))
    score = float(clip_info.get("score", 0.8))

    hook_dur = min(config.HOOK_MAX_DURATION, max(config.HOOK_MIN_DURATION, climax_end - climax_start))
    segments_plan = []

    if struct_type == "Structure_C" and config.ENABLE_HOOK and score >= config.HIGHLIGHT_THRESHOLD:
        segments_plan.append({
            "type": "HOOK",
            "source_start": climax_start,
            "source_end": climax_start + hook_dur,
            "label": "🔥 초반 후크"
        })
        segments_plan.append({
            "type": "BUILDUP",
            "source_start": context_start,
            "source_end": climax_start,
            "label": "🎬 상황 빌드업"
        })
        segments_plan.append({
            "type": "CLIMAX",
            "source_start": climax_start,
            "source_end": context_end,
            "label": "💥 클라이맥스 & 결말"
        })
    elif struct_type == "Structure_A":
        lead_in = max(0.0, context_start - 8.0)
        segments_plan.append({
            "type": "INTRO_CLIMAX",
            "source_start": climax_start,
            "source_end": climax_end,
            "label": "⚡ 선제 하이라이트"
        })
        segments_plan.append({
            "type": "CONTEXT",
            "source_start": lead_in,
            "source_end": climax_start,
            "label": "📖 상황 전개"
        })
        segments_plan.append({
            "type": "OUTRO_CLIMAX",
            "source_start": climax_start,
            "source_end": context_end,
            "label": "🏆 최종 클라이맥스"
        })
    else:
        lead_in = max(0.0, climax_start - 20.0)
        segments_plan.append({
            "type": "FULL_STORY",
            "source_start": lead_in,
            "source_end": context_end,
            "label": "🎬 완성형 스토리"
        })

    total_dur = sum(s["source_end"] - s["source_start"] for s in segments_plan)
    if total_dur > config.TARGET_SHORTS_DURATION:
        excess = total_dur - config.TARGET_SHORTS_DURATION
        for s in segments_plan:
            if s["type"] in ["BUILDUP", "CONTEXT", "FULL_STORY"]:
                curr_len = s["source_end"] - s["source_start"]
                trim_amt = min(excess, max(0.0, curr_len - 10.0))
                s["source_start"] += trim_amt
                excess -= trim_amt
                if excess <= 0:
                    break

    return segments_plan