# modules/transcription.py
from faster_whisper import WhisperModel
import config

_whisper_cache = None

def get_whisper():
    global _whisper_cache
    if _whisper_cache is None:
        model_name = getattr(config, "WHISPER_MODEL_NAME", "small")
        _whisper_cache = WhisperModel(model_name, device="cpu", compute_type="int8")
    return _whisper_cache

def transcribe_audio_with_word_timestamps(video_path: str):
    model = get_whisper()
    segments, _ = model.transcribe(
        video_path,
        language="ko",
        word_timestamps=True,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=400),
        initial_prompt="한국어 예능 토크 일상 대화, 유튜브 방송 하이라이트 자막, 정확한 맞춤법과 띄어쓰기"
    )
    
    raw_segments = []
    precise_words = []
    
    for segment in segments:
        txt = segment.text.strip()
        if not txt:
            continue
        raw_segments.append({
            "start": float(segment.start),
            "end": float(segment.end),
            "text": txt
        })
        if segment.words:
            for w in segment.words:
                cleaned_word = w.word.strip()
                if cleaned_word:
                    precise_words.append({
                        "word": cleaned_word,
                        "start": float(w.start),
                        "end": float(w.end),
                        "prob": float(w.probability)
                    })

    subtitle_chunks = chunk_words_into_subtitles(precise_words)
    return raw_segments, precise_words, subtitle_chunks

def chunk_words_into_subtitles(precise_words):
    if not precise_words:
        return []

    chunks = []
    curr_words = []
    c_start = 0.0
    
    max_words = getattr(config, "MAX_WORDS_PER_SUBTITLE", 4)
    max_chars = getattr(config, "MAX_CHARS_PER_SUBTITLE", 16)
    
    for i, item in enumerate(precise_words):
        if not curr_words:
            c_start = item["start"]
            
        curr_words.append(item["word"])
        curr_text = " ".join(curr_words)
        
        is_last_word = (i == len(precise_words) - 1)
        long_pause_after = False
        if not is_last_word:
            pause = precise_words[i+1]["start"] - item["end"]
            if pause >= 0.5:
                long_pause_after = True
                
        if len(curr_words) >= max_words or \
           len(curr_text) >= max_chars or \
           long_pause_after or is_last_word:
            
            chunks.append({
                "start": c_start,
                "end": item["end"],
                "text": curr_text,
                "duration": item["end"] - c_start
            })
            curr_words = []

    return chunks