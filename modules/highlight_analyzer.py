# modules/highlight_analyzer.py
import json
import google.generativeai as genai
import config

def call_gemini_auto(prompt: str, api_key: str):
    genai.configure(api_key=api_key)
    models = ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-2.5-flash", "gemini-3.6-flash"]
    last_error = None
    for m_name in models:
        try:
            m = genai.GenerativeModel(m_name)
            res = m.generate_content(prompt)
            return res.text.strip()
        except Exception as e:
            last_error = e
            continue
    raise Exception(f"Gemini API 호출 실패: {last_error}")

def analyze_video_highlights(
    gemini_api_key: str,
    video_title: str,
    transcript_text: str,
    duration: float,
    target_count: int = 3,
    real_comments: list = None,
    *args,
    **kwargs
):
    comments_context = ""
    if real_comments and len(real_comments) > 0:
        c_lines = [f"- @{c.get('author', '시청자')} (👍 {c.get('likes', '0')}): \"{c.get('text', '')}\"" for c in real_comments[:30]]
        comments_context = f"\n[실제 유튜브 시청자 베스트 댓글 목록]\n" + "\n".join(c_lines) + "\n\n지시사항: 반드시 제공된 '실제 유튜브 댓글' 중에서 해당 하이라이트 상황에 가장 잘 맞는 댓글을 선택해 matched_comment로 매칭하세요."

    prompt = f"""
    [영상 정보]
    - 제목: {video_title}
    - 전체 길이: {duration:.1f}초

    [음성 인식 대본(타임스탬프 포함)]
    {transcript_text}
    {comments_context}

    당신은 1,000만 조회수를 만드는 숏폼 전문 수석 PD입니다.
    대사의 흥미도, 극적 반전, 감정 변화, 리액션을 종합 평가하여 가장 몰입도 높은 하이라이트 {target_count}개를 선정하세요.

    [자막 생성 특별 지시사항]
    - 모든 말소리를 다 자막으로 달지 마세요 (조잡해짐 방지).
    - 시청자의 웃음을 터뜨리거나 상황을 이해시키는 데 꼭 필요한 **핵심 펀치라인/결정적 대사(3~5개만)**를 선별하여 key_subtitles에 넣으세요.
    - 각 자막은 짧고 강렬하게 다듬으세요.

    반드시 아래 JSON 포맷으로만 응답하세요:
    {{
        "real_source": "추적된 방송/프로그램명 또는 빈 문자열",
        "clips": [
            {{
                "climax_start": 32.5,
                "climax_end": 35.8,
                "score": 0.94,
                "recommended_structure": "Structure_C",
                "title": "시청자를 끌어당길 초대형 후킹 타이틀",
                "ai_note": "핵심 하이라이트 설명 1줄",
                "special_event": {{
                    "event_start": 33.0,
                    "event_end": 35.2,
                    "description": "갑작스러운 반전 리액션"
                }},
                "matched_comment": {{
                    "author": "알고리즘장인",
                    "text": "아 여기서 표정 변하는 거 진짜 레전드 ㅋㅋㅋ",
                    "likes": "2.4만",
                    "relevance_score": 0.95
                }},
                "key_subtitles": [
                    {{"start": 30.5, "end": 32.8, "text": "방금 한 말 진심이야?!"}},
                    {{"start": 33.0, "end": 35.5, "text": "이게 바로 알파메일의 매력이지 ㅋㅋㅋ"}}
                ]
            }}
        ]
    }}
    """
    
    raw_text = call_gemini_auto(prompt, gemini_api_key)
    
    if "```json" in raw_text:
        clean_json = raw_text.split("```json")[1].split("```")[0].strip()
    elif "```" in raw_text:
        clean_json = raw_text.split("```")[1].split("```")[0].strip()
    else:
        clean_json = raw_text
        
    data = json.loads(clean_json)
    clips = data.get("clips", [])
    
    for c in clips:
        c_start = float(c.get("climax_start", 0.0))
        c_end = float(c.get("climax_end", c_start + 5.0))
        
        c["context_start"] = max(0.0, c_start - config.CONTEXT_PADDING_BEFORE)
        c["context_end"] = min(duration, c_end + config.CONTEXT_PADDING_AFTER)
        c["source"] = data.get("real_source", "")

    return clips, data.get("real_source", "")