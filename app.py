# app.py
import streamlit as st
import os
import io
import json
import zipfile
import shutil
import importlib
from datetime import datetime
import yt_dlp
import config

# 모듈 핫 리로드 (캐시 충돌 방지)
import modules.transcription
import modules.highlight_analyzer
import modules.structure_engine
import modules.comment_engine
import modules.renderer
import modules.youtube_service

importlib.reload(modules.transcription)
importlib.reload(modules.highlight_analyzer)
importlib.reload(modules.structure_engine)
importlib.reload(modules.comment_engine)
importlib.reload(modules.renderer)
importlib.reload(modules.youtube_service)

from modules.transcription import transcribe_audio_with_word_timestamps
from modules.highlight_analyzer import analyze_video_highlights
from modules.structure_engine import build_shorts_timeline_plan
from modules.renderer import render_final_shorts_video, generate_layout_preview_image, auto_detect_video_boundary

from modules.youtube_service import (
    DEFAULT_YOUTUBE_API_KEY,
    CATEGORY_QUERY_MAP,
    get_official_trending_videos,
    search_custom_videos,
    fetch_real_video_comments,
    extract_youtube_video_id,
    format_duration
)

try:
    from moviepy.editor import VideoFileClip
except ImportError:
    from moviepy import VideoFileClip

st.set_page_config(page_title="이지컷(EasyCut) AI 올인원 숏폼 스튜디오", layout="wide")

PROJECTS_DIR = "saved_projects"
ACTIVE_SESSION_FILE = "active_session_cache.json"
os.makedirs(PROJECTS_DIR, exist_ok=True)

# 작업 상태 자동 저장 및 복원 엔진
def save_active_session_to_disk():
    state_to_save = {
        "gemini_key_input": st.session_state.get("gemini_key_input", ""),
        "youtube_url_input": st.session_state.get("youtube_url_input", ""),
        "stage_video_title": st.session_state.get("stage_video_title", ""),
        "source_video_duration": st.session_state.get("source_video_duration", 0.0),
        "is_source_vertical": st.session_state.get("is_source_vertical", False),
        "detected_v_top": st.session_state.get("detected_v_top", 656),
        "detected_v_bottom": st.session_state.get("detected_v_bottom", 1264),
        "raw_transcript_segments": st.session_state.get("raw_transcript_segments", []),
        "subtitle_chunks": st.session_state.get("subtitle_chunks", []),
        "real_comments_pool": st.session_state.get("real_comments_pool", []),
        "staged_clips": st.session_state.get("staged_clips", None),
        "real_source": st.session_state.get("real_source", ""),
        "generated_results": st.session_state.get("generated_results", []),
        "current_project_id": st.session_state.get("current_project_id", None)
    }
    try:
        with open(ACTIVE_SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump(state_to_save, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def load_active_session_from_disk():
    if os.path.exists(ACTIVE_SESSION_FILE):
        try:
            with open(ACTIVE_SESSION_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                for k, v in saved.items():
                    if k not in st.session_state or not st.session_state[k]:
                        st.session_state[k] = v
        except Exception:
            pass

def clear_active_session():
    if os.path.exists(ACTIVE_SESSION_FILE):
        try:
            os.remove(ACTIVE_SESSION_FILE)
        except Exception:
            pass
    st.session_state["staged_clips"] = None
    st.session_state["generated_results"] = []
    st.session_state["raw_transcript_segments"] = []
    st.session_state["subtitle_chunks"] = []
    st.session_state["real_comments_pool"] = []
    st.session_state["source_video_duration"] = 0.0
    st.session_state["current_project_id"] = None

if "session_initialized" not in st.session_state:
    st.session_state["session_initialized"] = True
    load_active_session_from_disk()

if "generated_results" not in st.session_state:
    st.session_state["generated_results"] = []
if "raw_transcript_segments" not in st.session_state:
    st.session_state["raw_transcript_segments"] = []
if "subtitle_chunks" not in st.session_state:
    st.session_state["subtitle_chunks"] = []
if "real_comments_pool" not in st.session_state:
    st.session_state["real_comments_pool"] = []
if "source_video_duration" not in st.session_state:
    st.session_state["source_video_duration"] = 0.0
if "is_source_vertical" not in st.session_state:
    st.session_state["is_source_vertical"] = False
if "detected_v_top" not in st.session_state:
    st.session_state["detected_v_top"] = 656
if "detected_v_bottom" not in st.session_state:
    st.session_state["detected_v_bottom"] = 1264
if "current_project_id" not in st.session_state:
    st.session_state["current_project_id"] = None
if "staged_clips" not in st.session_state:
    st.session_state["staged_clips"] = None
if "stage_video_title" not in st.session_state:
    st.session_state["stage_video_title"] = ""
if "nav_selection" not in st.session_state:
    st.session_state["nav_selection"] = "🎬 AI 숏폼 제작 스튜디오"
if "gemini_key_input" not in st.session_state:
    st.session_state["gemini_key_input"] = ""
if "youtube_url_input" not in st.session_state:
    st.session_state["youtube_url_input"] = ""

def format_time(seconds):
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m:02d}:{s:02d}"

def save_project_to_disk(project_id, title_text, results, transcript_segments, duration, is_vertical=False):
    p_path = os.path.join(PROJECTS_DIR, project_id)
    os.makedirs(p_path, exist_ok=True)
    meta = {
        "id": project_id,
        "title": title_text,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "duration": duration,
        "is_vertical": is_vertical,
        "results": results,
        "transcript_segments": transcript_segments
    }
    with open(os.path.join(p_path, "project.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

def load_all_saved_projects():
    projects = []
    if not os.path.exists(PROJECTS_DIR):
        return []
    for p_id in sorted(os.listdir(PROJECTS_DIR), reverse=True):
        meta_file = os.path.join(PROJECTS_DIR, p_id, "project.json")
        if os.path.exists(meta_file):
            try:
                with open(meta_file, "r", encoding="utf-8") as f:
                    projects.append(json.load(f))
            except Exception:
                continue
    return projects

# =========================================================================
# 사이드바 공통 내비게이션 (양방향 동기화)
# =========================================================================
st.sidebar.title("🎛️ 워크스페이스 내비게이션")
nav_options = ["🎬 AI 숏폼 제작 스튜디오", "🔥 실시간 인기 & 맞춤 탐색기"]

if "main_sidebar_menu_radio" not in st.session_state:
    st.session_state["main_sidebar_menu_radio"] = st.session_state["nav_selection"]

menu_choice = st.sidebar.radio(
    "메뉴 이동:",
    nav_options,
    index=0 if st.session_state["nav_selection"] == nav_options[0] else 1,
    key="main_sidebar_menu_radio"
)
st.session_state["nav_selection"] = menu_choice

st.sidebar.markdown("---")
st.sidebar.subheader("📚 지난 프로젝트 보관함")
saved_list = load_all_saved_projects()
if saved_list:
    options = [f"[{p.get('date', '')[:16]}] {p.get('title', '제목 없음')[:20]}" for p in saved_list]
    selected_idx = st.sidebar.selectbox("보관함 프로젝트:", range(len(options)), format_func=lambda x: options[x], key="sb_project_selector")
    
    col_sb1, col_sb2 = st.sidebar.columns(2)
    with col_sb1:
        if st.button("📂 불러오기", use_container_width=True, key="btn_sb_load_project"):
            p_data = saved_list[selected_idx]
            st.session_state["current_project_id"] = p_data.get("id")
            st.session_state["generated_results"] = p_data.get("results", [])
            st.session_state["raw_transcript_segments"] = p_data.get("transcript_segments", [])
            st.session_state["source_video_duration"] = p_data.get("duration", 0.0)
            st.session_state["is_source_vertical"] = p_data.get("is_vertical", False)
            st.session_state["staged_clips"] = None
            st.session_state["nav_selection"] = nav_options[0]
            st.session_state["main_sidebar_menu_radio"] = nav_options[0]
            save_active_session_to_disk()
            st.rerun()
    with col_sb2:
        if st.button("🗑️ 삭제하기", use_container_width=True, key="btn_sb_delete_project"):
            p_id = saved_list[selected_idx].get("id")
            target_p = os.path.join(PROJECTS_DIR, p_id)
            if os.path.exists(target_p):
                shutil.rmtree(target_p)
            if st.session_state.get("current_project_id") == p_id:
                st.session_state["generated_results"] = []
            st.rerun()
else:
    st.sidebar.info("보관된 지난 프로젝트가 없습니다.")

# =========================================================================
# 화면 1: 🔥 실시간 인기 & 맞춤 탐색기
# =========================================================================
if st.session_state["nav_selection"] == "🔥 실시간 인기 & 맞춤 탐색기":
    st.markdown("## 🔥 유튜브 실시간 인기 & 맞춤 탐색기")
    st.caption("⚡ 인기 급상승 차트와 카테고리별 대량 고속 탐색 · 클릭 한 번으로 숏폼 제작대로 즉시 전송")

    category_list = list(CATEGORY_QUERY_MAP.keys())
    region_options = ["🇰🇷 국내만 (KR)", "🌐 해외만 (US/글로벌)", "🌍 국내 + 해외 전체"]
    period_options = ["전체 기간", "📅 일간 (최근 24시간)", "📅 주간 (최근 7일)", "📅 월간 (최근 30일)", "🗓️ 특정 연·월 지정"]
    length_options = ["전체", "🎬 롱폼만 (70초 초과)", "⚡ 숏폼만 (60초 이하)"]

    tab_trend, tab_search = st.tabs(["📈 유튜브 실시간 급상승 차트", "🔍 키워드 & 카테고리/기간 정밀 탐색"])

    with tab_trend:
        t_col1, t_col2, t_col3, t_col4, t_col5 = st.columns([1.8, 1.4, 1.8, 1.1, 0.9])
        with t_col1:
            trend_cat_name = st.selectbox("카테고리 선택:", category_list, key="trend_cat")
        with t_col2:
            trend_region = st.selectbox("국가/지역 범위:", region_options, key="trend_region")
        with t_col3:
            trend_len = st.selectbox("영상 길이:", length_options, key="trend_len")
        with t_col4:
            st.write("")
            trend_cc = st.checkbox("재사용(CC)만", value=False, key="trend_cc")
        with t_col5:
            st.write("")
            btn_trend = st.button("🔄 차트 갱신", use_container_width=True, key="btn_trend")

        if btn_trend:
            get_official_trending_videos.clear()

        with st.spinner("실시간 유튜브 공식 인기 급상승 차트 불러오는 중..."):
            trend_list = get_official_trending_videos(
                DEFAULT_YOUTUBE_API_KEY,
                category_name=trend_cat_name,
                region_mode=trend_region,
                only_cc=trend_cc,
                length_type=trend_len
            )

        if trend_list:
            cols = st.columns(3)
            for idx, vid in enumerate(trend_list):
                with cols[idx % 3]:
                    st.image(vid["thumb"], use_container_width=True)
                    badge = "⚡ 숏폼" if vid["duration"] <= 60 else f"🎬 {format_duration(vid['duration'])}"
                    cc_badge = " · 🟢 CC재사용" if vid["is_cc"] else ""
                    st.markdown(f"**{vid['title'][:28]}...**" if len(vid['title']) > 28 else f"**{vid['title']}**")
                    st.caption(f"📺 {vid['channel']} · 👁️ {vid['views']:,}회\n📅 {vid['published_at']} [{badge}{cc_badge}]")
                    if st.button("🎬 이 영상으로 숏폼 만들기", key=f"sel_t_{vid['id']}_{idx}", use_container_width=True):
                        st.session_state["youtube_url_input"] = vid["url"]
                        st.session_state["nav_selection"] = "🎬 AI 숏폼 제작 스튜디오"
                        st.session_state["main_sidebar_menu_radio"] = "🎬 AI 숏폼 제작 스튜디오"
                        save_active_session_to_disk()
                        st.rerun()
        else:
            st.info("조건에 맞는 급상승 영상이 없습니다. CC 필터를 끄거나 길이를 '전체'로 설정해보세요.")

    with tab_search:
        s_col1, s_col2 = st.columns([2, 1])
        with s_col1:
            search_kw = st.text_input("검색 키워드:", placeholder="예: 무한도전, 침착맨, 피지컬갤러리, 런닝맨", key="s_kw")
        with s_col2:
            search_cat_name = st.selectbox("카테고리 필터:", category_list, key="s_cat")

        f_col1, f_col2, f_col3, f_col4, f_col5 = st.columns([1.2, 1.2, 1.6, 1.1, 0.9])
        with f_col1:
            search_region = st.selectbox("국가/지역 범위:", region_options, key="s_region")
        with f_col2:
            search_period = st.selectbox("기간 설정:", period_options, index=0, key="s_period")
        with f_col3:
            search_len = st.selectbox("영상 길이:", length_options, index=1, key="s_len")
        with f_col4:
            st.write("")
            search_cc = st.checkbox("재사용(CC)만 보기", value=False, key="s_cc")
        with f_col5:
            st.write("")
            btn_search = st.button("🔍 탐색 실행", use_container_width=True, key="btn_s")

        sel_year, sel_month = None, None
        if search_period == "🗓️ 특정 연·월 지정":
            y_col, m_col, _ = st.columns([1, 1, 2])
            with y_col:
                sel_year = st.selectbox("연도 선택:", [str(y) for y in range(2026, 2019, -1)], key="sel_y")
            with m_col:
                sel_month = st.selectbox("월 선택:", [f"{m:02d}" for m in range(1, 13)], key="sel_m")

        if btn_search or "search_data_cache" not in st.session_state:
            with st.spinner(f"[{search_period}] 기준 인기 영상 탐색 중..."):
                st.session_state["search_data_cache"] = search_custom_videos(
                    DEFAULT_YOUTUBE_API_KEY,
                    keyword=search_kw,
                    category_name=search_cat_name,
                    region_mode=search_region,
                    period_type=search_period,
                    selected_year=sel_year,
                    selected_month=sel_month,
                    only_cc=search_cc,
                    length_type=search_len
                )

        search_list = st.session_state.get("search_data_cache", [])
        if search_list:
            cols = st.columns(3)
            for idx, vid in enumerate(search_list):
                with cols[idx % 3]:
                    st.image(vid["thumb"], use_container_width=True)
                    badge = "⚡ 숏폼" if vid["duration"] <= 60 else f"🎬 {format_duration(vid['duration'])}"
                    cc_badge = " · 🟢 CC재사용" if vid["is_cc"] else ""
                    st.markdown(f"**{vid['title'][:28]}...**" if len(vid['title']) > 28 else f"**{vid['title']}**")
                    st.caption(f"📺 {vid['channel']} · 👁️ {vid['views']:,}회\n📅 {vid['published_at']} [{badge}{cc_badge}]")
                    if st.button("🎬 이 영상으로 숏폼 만들기", key=f"sel_s_{vid['id']}_{idx}", use_container_width=True):
                        st.session_state["youtube_url_input"] = vid["url"]
                        st.session_state["nav_selection"] = "🎬 AI 숏폼 제작 스튜디오"
                        st.session_state["main_sidebar_menu_radio"] = "🎬 AI 숏폼 제작 스튜디오"
                        save_active_session_to_disk()
                        st.rerun()
        else:
            st.info(f"선택한 조건([{search_period}])에 맞는 영상이 없습니다. CC 필터를 해제하거나 기간을 완화해보세요.")

# =========================================================================
# 화면 2: 🎬 AI 숏폼 제작 스튜디오
# =========================================================================
else:
    head_col1, head_col2 = st.columns([4, 1])
    with head_col1:
        st.title("🎬 이지컷(EasyCut) AI 정밀 숏폼 제작기")
        st.caption("1차 롱폼 화각 조절 & 2차 숏츠 마스킹 · 실제 유튜브 베스트 댓글 연동 · 영상 내부 핵심 펀치라인 자막")
    with head_col2:
        st.write("")
        if st.button("🧹 새 작업 시작 (초기화)", use_container_width=True, key="btn_clear_main_session"):
            clear_active_session()
            st.rerun()

    if st.session_state.get("staged_clips") or st.session_state.get("generated_results"):
        st.info("💾 **이전 작업 상태가 안전하게 복원되었습니다.** (새로운 영상으로 작업하시려면 우측 상단 '새 작업 시작'을 누르세요)")

    st.markdown("### ⚙️ 1. 영상 입력 및 AI 설정")
    col_in1, col_in2 = st.columns([1, 1])
    with col_in1:
        gemini_api_key = st.text_input(
            "🔑 Gemini API 키 입력",
            type="password",
            value=st.session_state.get("gemini_key_input", ""),
            key="gemini_key_input",
            placeholder="AIzaSy..."
        )
    with col_in2:
        video_url = st.text_input(
            "🔗 유튜브 영상 URL (롱폼 16:9 또는 숏츠 9:16 URL)",
            value=st.session_state.get("youtube_url_input", ""),
            key="youtube_url_input",
            placeholder="https://www.youtube.com/watch?v=... 또는 https://youtube.com/shorts/..."
        )

    is_shorts_url = "/shorts/" in video_url if video_url else False

    col_opt1, col_opt2, col_opt3 = st.columns(3)
    with col_opt1:
        if is_shorts_url:
            st.info("💡 **숏츠 감지**: 원본 길이를 유지하며 상하단 렉카 자막 영역을 100% 마스킹합니다.")
            video_count = 1
        else:
            video_count = st.slider("🎞️ 생성할 쇼츠 개수", 1, 5, 3, key="slider_video_count")
    with col_opt2:
        design_template = st.selectbox("🎨 디자인 템플릿", ["댓글 캡처 (다크)", "댓글 캡처 (화이트)", "심플 다크", "심플 화이트"], key="sel_design_template")
    with col_opt3:
        accel_choice = st.selectbox("⚡ 렌더링 가속 엔진", ["⚡ NVIDIA GPU 가속 (h264_nvenc)", "⚡ Intel QuickSync 가속 (h264_qsv)", "💻 CPU 초고속 멀티스레드 (libx264)"], key="sel_accel_choice")

    if st.button("🔍 1단계: 실제 베스트 댓글 수집 & Whisper 정밀 분석 시작", type="primary", use_container_width=True, key="btn_start_analysis_step1"):
        if not gemini_api_key or not video_url:
            st.error("API 키와 유튜브 주소를 입력해주세요.")
        else:
            try:
                with st.spinner("1/4 유튜브 원본 영상 다운로드 중..."):
                    download_success = False
                    video_title = "신규 숏폼 프로젝트"
                    configs = [
                        {'format': 'best[ext=mp4]/best', 'outtmpl': 'input_video.mp4', 'overwrites': True, 'extractor_args': {'youtube': {'player_client': ['android', 'web']}}},
                        {'format': 'best[ext=mp4]/best', 'outtmpl': 'input_video.mp4', 'overwrites': True, 'extractor_args': {'youtube': {'player_client': ['ios', 'web']}}},
                        {'format': 'best[ext=mp4]/best', 'outtmpl': 'input_video.mp4', 'overwrites': True, 'cookiesfrombrowser': ('chrome', )}
                    ]
                    for cfg in configs:
                        try:
                            if os.path.exists("input_video.mp4"):
                                os.remove("input_video.mp4")
                            with yt_dlp.YoutubeDL(cfg) as ydl:
                                info = ydl.extract_info(video_url, download=True)
                                video_title = info.get('title', '신규 숏폼 프로젝트')
                            if os.path.exists("input_video.mp4") and os.path.getsize("input_video.mp4") > 10000:
                                download_success = True
                                break
                        except Exception:
                            continue
                    if not download_success:
                        raise Exception("유튜브 서버에서 다운로드를 차단했습니다. 다른 공개 영상 링크로 시도해 주세요.")

                    st.session_state["stage_video_title"] = video_title

                with st.spinner("2/4 실제 유튜브 시청자 베스트 댓글 수집 중..."):
                    v_id = extract_youtube_video_id(video_url)
                    real_comments = fetch_real_video_comments(DEFAULT_YOUTUBE_API_KEY, v_id, max_count=40)
                    st.session_state["real_comments_pool"] = real_comments

                with st.spinner("3/4 Whisper small 고정밀 음성 인식 중 (단어 단위 싱크)..."):
                    raw_segs, words, sub_chunks = transcribe_audio_with_word_timestamps("input_video.mp4")
                    st.session_state["raw_transcript_segments"] = raw_segs
                    st.session_state["subtitle_chunks"] = sub_chunks
                    transcript_full = "\n".join([f"[{s['start']:.1f}s ~ {s['end']:.1f}s] {s['text']}" for s in raw_segs])

                with st.spinner("4/4 AI 하이라이트 분석 & 핵심 펀치라인 자막 선별 중..."):
                    temp_v = VideoFileClip("input_video.mp4")
                    duration = temp_v.duration
                    is_vert = temp_v.size[1] > temp_v.size[0]
                    st.session_state["source_video_duration"] = duration
                    st.session_state["is_source_vertical"] = is_vert

                    if is_vert:
                        detected_top, detected_bottom = auto_detect_video_boundary(temp_v, duration)
                    else:
                        detected_top, detected_bottom = 656, 1264

                    st.session_state["detected_v_top"] = detected_top
                    st.session_state["detected_v_bottom"] = detected_bottom
                    temp_v.close()

                    clips, real_src = analyze_video_highlights(
                        gemini_api_key=gemini_api_key,
                        video_title=video_title,
                        transcript_text=transcript_full,
                        duration=duration,
                        target_count=video_count,
                        real_comments=real_comments
                    )

                    st.session_state["staged_clips"] = clips
                    st.session_state["real_source"] = real_src
                    save_active_session_to_disk()
                    st.success("✅ 분석 완료! 아래 2단계에서 핵심 자막 대본과 레이아웃을 확인하세요.")
                    st.rerun()

            except Exception as e:
                st.error(f"오류 발생: {e}")

    # =========================================================================
    # 2단계: 정밀 검토 및 자막/댓글/화각 조절
    # =========================================================================
    if st.session_state.get("staged_clips"):
        st.markdown("---")
        st.markdown("### ✍️ 2단계: 영상 화각(줌) & 상하단 가림막 & 핵심 펀치라인 자막 검토")
        
        v_dur = st.session_state.get("source_video_duration", 600.0)
        is_vert_src = st.session_state.get("is_source_vertical", False)

        st.markdown("#### 📐 영상 화각(줌) 및 상·하단 가림막 조절")
        col_ctrl1, col_ctrl2, col_ctrl3 = st.columns(3)
        
        with col_ctrl1:
            if not is_vert_src:
                zoom_choice = st.select_slider(
                    "🔍 롱폼 화면 확대 줌(Zoom)",
                    options=[1.0, 1.15, 1.25, 1.35, 1.5],
                    value=1.0,
                    format_func=lambda x: f"{x}x ({'원본 비율 100% 온전 보존' if x==1.0 else '인물/중심 몰입 확대'})",
                    key="slider_zoom_choice"
                )
            else:
                zoom_choice = 1.0
                st.info("📱 세로 숏츠 영상: 1080x1920 풀화면 유지")

        with col_ctrl2:
            custom_v_top = st.slider("📐 상단 배너 위치 (px)", min_value=250, max_value=750, value=st.session_state.get("detected_v_top", 656), step=10, key="slider_custom_v_top")
        with col_ctrl3:
            custom_v_bottom = st.slider("📐 하단 댓글 위치 (px)", min_value=1150, max_value=1700, value=st.session_state.get("detected_v_bottom", 1264), step=10, key="slider_custom_v_bottom")

        first_clip = st.session_state["staged_clips"][0]
        sample_t = float(first_clip.get("climax_start", 10.0))
        prev_path = generate_layout_preview_image(
            video_path="input_video.mp4",
            is_vertical=is_vert_src,
            v_top=custom_v_top,
            v_bottom=custom_v_bottom,
            zoom_factor=zoom_choice,
            sample_time=sample_t,
            out_path="live_preview.png"
        )

        col_prv1, col_prv2 = st.columns([1, 2])
        with col_prv1:
            if prev_path and os.path.exists(prev_path):
                st.image(prev_path, caption="👁️ 1080x1920 캔버스 실시간 레이아웃 예상도", use_container_width=True)
        with col_prv2:
            st.success(f"""
            **✨ 최적화된 레이아웃 배치 구조**
            * **상단 배너 (`0 ~ {custom_v_top}px`)**: 초대형 타이틀 & 프로그램 출처
            * **영상 내부 하단**: 핵심 펀치라인/리액션 자막 굵은 외곽선 노출 (시야 방해 0%)
            * **하단 배너 (`{custom_v_bottom} ~ 1920px`)**: 실제 유튜브 시청자 베스트 댓글 카드 전용 배치
            """)

        staged = st.session_state["staged_clips"]
        for idx, c in enumerate(staged):
            c_start = float(c.get("context_start", c.get("climax_start", 0.0)))
            c_end = float(c.get("context_end", c.get("climax_end", 30.0)))
            
            with st.expander(f"📌 쇼츠 #{idx+1}: {c.get('title')} [타임라인: {format_time(c_start)} ~ {format_time(c_end)}] (점수: {c.get('score')})", expanded=True):
                st.info(f"구조: **{c.get('recommended_structure')}** | AI 요약: {c.get('ai_note')}")
                
                col_e1, col_e2 = st.columns([1, 1])
                with col_e1:
                    c["title"] = st.text_input(f"후킹 타이틀 (#{idx+1})", value=c.get("title"), key=f"t_{idx}")
                    c["source"] = st.text_input(f"출처 (#{idx+1})", value=c.get("source", ""), key=f"s_{idx}")

                    st.markdown("**⏱️ 하이라이트 영상 타임라인 조절 (0.1초 단위)**")
                    t_col1, t_col2 = st.columns(2)
                    with t_col1:
                        new_c_start = st.number_input(
                            f"시작 시간 (초) #{idx+1}",
                            min_value=0.0,
                            max_value=max(0.0, float(v_dur - 3.0)),
                            value=float(c_start),
                            step=0.1,
                            key=f"st_num_{idx}"
                        )
                        c["context_start"] = new_c_start
                    with t_col2:
                        new_c_end = st.number_input(
                            f"종료 시간 (초) #{idx+1}",
                            min_value=float(new_c_start + 3.0),
                            max_value=float(v_dur),
                            value=float(min(v_dur, c_end)),
                            step=0.1,
                            key=f"et_num_{idx}"
                        )
                        c["context_end"] = new_c_end

                    st.caption(f"선택된 총 길이: **{new_c_end - new_c_start:.1f}초**")

                with col_e2:
                    evt = c.get("special_event", {})
                    cmt = c.get("matched_comment", {})
                    st.markdown(f"**⚡ 특이 상황 발생:** `{evt.get('event_start')}s ~ {evt.get('event_end')}s` ({evt.get('description')})")
                    
                    key_subs_lines = [k.get("text", "") for k in c.get("key_subtitles", [])]
                    default_punchlines = "\n".join(key_subs_lines) if key_subs_lines else c.get("ai_note", "")
                    
                    c["custom_script"] = st.text_area(
                        f"💬 [영상 내부] 핵심 펀치라인 자막 확인 및 수정 (#{idx+1}) - 줄바꿈 기준",
                        value=c.get("custom_script", default_punchlines),
                        height=90,
                        help="모든 말을 다 적지 말고, 시청자가 꼭 봐야 할 핵심 펀치라인 대사 2~4줄만 간결하게 유지하세요.",
                        key=f"script_area_{idx}"
                    )

                    st.markdown(f"**💬 [하단 배너] 매칭 베스트 댓글 (등장 시점: {evt.get('event_end', new_c_end - 2.0)+0.5:.1f}s):**")
                    cmt["author"] = st.text_input(f"작성자 (#{idx+1})", value=cmt.get("author", "베플러"), key=f"cmt_a_{idx}")
                    cmt["text"] = st.text_input(f"댓글 내용 (#{idx+1})", value=cmt.get("text", "대박 ㅋㅋㅋ"), key=f"cmt_t_{idx}")

        save_active_session_to_disk()

        if st.button("🎬 3단계: 검토 완료! 최적 레이아웃으로 최종 렌더링", type="primary", use_container_width=True, key="btn_start_render_step3"):
            try:
                results = []
                progress_bar = st.progress(0)
                timestamp_id = datetime.now().strftime("%Y%m%d_%H%M%S")
                project_save_path = os.path.join(PROJECTS_DIR, timestamp_id)
                os.makedirs(project_save_path, exist_ok=True)
                st.session_state["current_project_id"] = timestamp_id

                for i, c_info in enumerate(staged):
                    with st.spinner(f"[{i+1}/{len(staged)}] 번째 쇼츠 합성 중 ({accel_choice})..."):
                        timeline_plan = build_shorts_timeline_plan(c_info, v_dur)
                        out_file = render_final_shorts_video(
                            source_video_path="input_video.mp4",
                            segments_plan=timeline_plan,
                            subtitle_chunks=st.session_state.get("subtitle_chunks", []),
                            clip_info=c_info,
                            real_source=c_info.get("source", ""),
                            template_name=design_template,
                            accel_engine=accel_choice,
                            out_dir=project_save_path,
                            index=i+1,
                            is_vertical=is_vert_src,
                            v_top=custom_v_top,
                            v_bottom=custom_v_bottom,
                            zoom_factor=zoom_choice,
                            custom_sub_text=c_info.get("custom_script")
                        )
                        results.append({
                            "file": out_file,
                            "title": c_info.get("title"),
                            "start": c_info.get("context_start", 0.0),
                            "end": c_info.get("context_end", 30.0),
                            "source": c_info.get("source", ""),
                            "ai_note": c_info.get("ai_note", ""),
                            "script_text": c_info.get("custom_script", ""),
                            "template": design_template,
                            "v_top": custom_v_top,
                            "v_bottom": custom_v_bottom,
                            "zoom_factor": zoom_choice
                        })
                        progress_bar.progress((i + 1) / len(staged))

                st.session_state["generated_results"] = results
                save_project_to_disk(
                    project_id=timestamp_id,
                    title_text=st.session_state.get("stage_video_title", "신규 숏폼 프로젝트"),
                    results=results,
                    transcript_segments=st.session_state.get("raw_transcript_segments", []),
                    duration=v_dur,
                    is_vertical=is_vert_src
                )
                save_active_session_to_disk()
                st.success("🎉 모든 쇼츠 완성이 완료되었습니다!")
                st.rerun()

            except Exception as e:
                st.error(f"렌더링 중 오류 발생: {e}")

    # =========================================================================
    # 3단계: 결과 화면 및 0.1초 트리머
    # =========================================================================
    if st.session_state.get("generated_results"):
        st.markdown("---")
        res_list = st.session_state["generated_results"]
        top_col1, top_col2 = st.columns([3, 1])
        with top_col1:
            st.markdown(f"### 📂 완성된 쇼츠 결과물 (총 {len(res_list)}개)")
        with top_col2:
            if len(res_list) > 1:
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w") as zf:
                    for item in res_list:
                        if os.path.exists(item["file"]):
                            zf.write(item["file"], os.path.basename(item["file"]))
                zip_buffer.seek(0)
                st.download_button(
                    label="↓ 모든 쇼츠 일괄 다운로드",
                    data=zip_buffer,
                    file_name="easycut_all_shorts.zip",
                    mime="application/zip",
                    type="primary",
                    use_container_width=True,
                    key="btn_zip_download_all"
                )

        for idx, item in enumerate(res_list):
            st.markdown(f"#### #{idx+1} {item['title']}")
            card_col1, card_col2 = st.columns([1, 2])
            
            with card_col1:
                if os.path.exists(item["file"]):
                    st.video(item["file"])
                    with open(item["file"], "rb") as f:
                        st.download_button(
                            label=f"↓ 쇼츠 #{idx+1} 다운로드",
                            data=f,
                            file_name=f"shorts_{idx+1}.mp4",
                            mime="video/mp4",
                            key=f"dl_btn_{idx}",
                            use_container_width=True
                        )

            with card_col2:
                dur_sec = int(item['end'] - item['start'])
                st.caption(f"⏱️ 영상 길이: **{dur_sec}초** ({item['start']:.1f}s ~ {item['end']:.1f}s)")
                st.info(f"**✦ AI 하이라이트 요약:** {item.get('ai_note')}")
                
                with st.expander("✂️ 0.1초 단위 구간 미세 조정 및 즉시 재렌더링", expanded=False):
                    max_dur = st.session_state.get("source_video_duration", 600.0)
                    adj_col1, adj_col2 = st.columns(2)
                    with adj_col1:
                        re_start = st.number_input(f"시작 시간 (초) - #{idx+1}", min_value=0.0, max_value=max(0.0, float(item["end"] - 3.0)), value=float(item["start"]), step=0.1, key=f"re_st_{idx}")
                    with adj_col2:
                        re_end = st.number_input(f"종료 시간 (초) - #{idx+1}", min_value=float(re_start + 3.0), max_value=float(max_dur), value=float(item["end"]), step=0.1, key=f"re_et_{idx}")
                    
                    re_sub = st.text_area(f"자막 대본 수정 (#{idx+1})", value=item.get("script_text", ""), key=f"re_sub_{idx}")
                    
                    if st.button(f"🔄 #{idx+1} 재렌더링 적용", key=f"btn_re_{idx}"):
                        with st.spinner(f"#{idx+1} 숏폼 재렌더링 중..."):
                            cur_p_dir = os.path.dirname(item["file"]) if os.path.dirname(item["file"]) else "."
                            re_plan = [{"type": "CUSTOM", "source_start": re_start, "source_end": re_end, "label": "수정 컷"}]
                            
                            new_out = render_final_shorts_video(
                                source_video_path="input_video.mp4",
                                segments_plan=re_plan,
                                subtitle_chunks=st.session_state.get("subtitle_chunks", []),
                                clip_info=item,
                                real_source=item.get("source", ""),
                                template_name=item.get("template", "댓글 캡처 (다크)"),
                                accel_engine=accel_choice,
                                out_dir=cur_p_dir,
                                index=idx+1,
                                is_vertical=st.session_state.get("is_source_vertical", False),
                                v_top=item.get("v_top", 656),
                                v_bottom=item.get("v_bottom", 1264),
                                zoom_factor=item.get("zoom_factor", 1.0),
                                custom_sub_text=re_sub
                            )
                            st.session_state["generated_results"][idx]["file"] = new_out
                            st.session_state["generated_results"][idx]["start"] = re_start
                            st.session_state["generated_results"][idx]["end"] = re_end
                            st.session_state["generated_results"][idx]["script_text"] = re_sub
                            
                            if st.session_state.get("current_project_id"):
                                save_project_to_disk(
                                    project_id=st.session_state["current_project_id"],
                                    title_text=item["title"],
                                    results=st.session_state["generated_results"],
                                    transcript_segments=st.session_state.get("raw_transcript_segments", []),
                                    duration=max_dur,
                                    is_vertical=st.session_state.get("is_source_vertical", False)
                                )
                            save_active_session_to_disk()
                            st.success(f"#{idx+1} 재렌더링이 완료되었습니다!")
                            st.rerun()
            st.markdown("---")