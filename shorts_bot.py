import streamlit as st
from googleapiclient.discovery import build
import isodate
import re
from datetime import datetime, timedelta, timezone

DEFAULT_API_KEY = "AIzaSyAcMm3MsrdaHGL3rvRkKgSkDtNLxgPVC3A"

# 스팸/도박 키워드 필터링
SPAM_KEYWORDS = ["슬롯", "바카라", "카지노", "홀덤", "토토", "리니지클래식", "레어서버", "프리서버", "먹튀", "머니상", "릴게임"]

CATEGORY_QUERY_MAP = {
    "🔥 전체 종합": {"kr": "인기", "en": "trending"},
    "🎬 엔터테인먼트 (예능/토크)": {"kr": "예능 하이라이트", "en": "entertainment highlights"},
    "🤣 코미디 / 스케치": {"kr": "코미디", "en": "comedy"},
    "💪 운동 / 피트니스 / 헬스": {"kr": "운동 헬스", "en": "workout fitness"},
    "🎥 영화 & 애니메이션": {"kr": "영화 명장면", "en": "movie scenes"},
    "📰 뉴스 & 이슈 / 썰": {"kr": "이슈 썰", "en": "news issue"},
    "🐕 동물 & 반려동물": {"kr": "귀여운 동물", "en": "cute animals"},
    "🎮 게임": {"kr": "게임 명장면", "en": "gameplay highlights"}
}


def is_spam_video(title, channel):
    """도박/스팸 영상 차단"""
    target_text = f"{title} {channel}".lower()
    for kw in SPAM_KEYWORDS:
        if kw in target_text:
            return True
    return False


def parse_duration(duration_str):
    """ISO 8601 영상 길이 변환"""
    try:
        return int(isodate.parse_duration(duration_str).total_seconds())
    except:
        return 0


def calculate_time_window(period_type, selected_year=None, selected_month=None):
    """기간별 UTC RFC3339 시간 계산"""
    now = datetime.now(timezone.utc)
    if period_type == "📅 일간 (최근 24시간)":
        return (now - timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%SZ'), None
    elif period_type == "📅 주간 (최근 7일)":
        return (now - timedelta(days=7)).strftime('%Y-%m-%dT%H:%M:%SZ'), None
    elif period_type == "📅 월간 (최근 30일)":
        return (now - timedelta(days=30)).strftime('%Y-%m-%dT%H:%M:%SZ'), None
    elif period_type == "🗓️ 특정 연·월 지정" and selected_year and selected_month:
        year, month = int(selected_year), int(selected_month)
        start_dt = datetime(year, month, 1, 0, 0, 0, tzinfo=timezone.utc)
        if month == 12:
            end_dt = datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        else:
            end_dt = datetime(year, month + 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        return start_dt.strftime('%Y-%m-%dT%H:%M:%SZ'), end_dt.strftime('%Y-%m-%dT%H:%M:%SZ')
    return None, None


def fetch_videos_with_details(youtube, video_ids):
    """비디오 ID 목록을 50개씩 나누어 400 에러 없이 일괄 조회"""
    if not video_ids:
        return []
    
    items = []
    # 유튜브 API 제한(최대 50개) 준수를 위한 청크 분할
    for i in range(0, len(video_ids), 50):
        chunk = video_ids[i:i + 50]
        res = youtube.videos().list(
            part="snippet,statistics,contentDetails,status",
            id=",".join(chunk)
        ).execute()
        
        for item in res.get("items", []):
            dur_sec = parse_duration(item.get("contentDetails", {}).get("duration", "PT0S"))
            status_info = item.get("status", {})
            pub_at = item.get("snippet", {}).get("publishedAt", "")[:10]
            
            thumbs = item.get("snippet", {}).get("thumbnails", {})
            medium_thumb = thumbs.get("medium", {}) or thumbs.get("high", {}) or thumbs.get("default", {})
            thumb_url = medium_thumb.get("url", "")
            
            items.append({
                "id": item["id"],
                "url": f"https://www.youtube.com/watch?v={item['id']}",
                "title": item["snippet"]["title"],
                "channel": item["snippet"]["channelTitle"],
                "published_at": pub_at if pub_at else "날짜 정보 없음",
                "thumb": thumb_url,
                "views": int(item.get("statistics", {}).get("viewCount", 0)),
                "likes": int(item.get("statistics", {}).get("likeCount", 0)),
                "duration": dur_sec,
                "is_cc": status_info.get("license") == "creativeCommon"
            })
    return items


@st.cache_data(ttl=1800, show_spinner=False)
def get_official_trending_videos(api_key, category_name="🔥 전체 종합", region_mode="🇰🇷 국내만 (KR)", only_cc=False, length_type="전체", max_results=30):
    """[1번 탭] 유튜브 공식 실시간 급상승 차트"""
    if not api_key:
        return []
    try:
        youtube = build("youtube", "v3", developerKey=api_key)
        
        category_id_map = {
            "🔥 전체 종합": "0", "🎬 엔터테인먼트 (예능/토크)": "24", "🤣 코미디 / 스케치": "23",
            "💪 운동 / 피트니스 / 헬스": "17", "🎥 영화 & 애니메이션": "1", "📰 뉴스 & 이슈 / 썰": "25",
            "🐕 동물 & 반려동물": "15", "🎮 게임": "20"
        }
        cat_id = category_id_map.get(category_name, "0")

        target_regions = ["KR"]
        if region_mode == "🌐 해외만 (US/글로벌)":
            target_regions = ["US"]
        elif region_mode == "🌍 국내 + 해외 전체":
            target_regions = ["KR", "US", "JP"]

        all_items = []
        for r_code in target_regions:
            req_params = {
                "part": "snippet,statistics,contentDetails,status",
                "chart": "mostPopular",
                "regionCode": r_code,
                "maxResults": 50
            }
            if cat_id != "0":
                req_params["videoCategoryId"] = cat_id
                
            res = youtube.videos().list(**req_params).execute()
            
            for item in res.get("items", []):
                dur_sec = parse_duration(item.get("contentDetails", {}).get("duration", "PT0S"))
                is_cc = item.get("status", {}).get("license") == "creativeCommon"
                title = item["snippet"]["title"]
                channel = item["snippet"]["channelTitle"]
                pub_at = item.get("snippet", {}).get("publishedAt", "")[:10]
                
                thumbs = item.get("snippet", {}).get("thumbnails", {})
                medium_thumb = thumbs.get("medium", {}) or thumbs.get("high", {}) or thumbs.get("default", {})
                thumb_url = medium_thumb.get("url", "")

                if is_spam_video(title, channel):
                    continue
                if only_cc and not is_cc:
                    continue
                
                is_shorts_title = bool(re.search(r'(#shorts|#short|#쇼츠)', title, re.IGNORECASE))
                
                if length_type == "⚡ 숏폼만 (60초 이하)" and (dur_sec > 60 and not is_shorts_title):
                    continue
                elif length_type == "🎬 롱폼만 (70초 초과)" and (dur_sec <= 70 or is_shorts_title):
                    continue
                    
                all_items.append({
                    "id": item["id"],
                    "url": f"https://www.youtube.com/watch?v={item['id']}",
                    "title": title,
                    "channel": channel,
                    "published_at": pub_at if pub_at else "날짜 정보 없음",
                    "thumb": thumb_url,
                    "views": int(item.get("statistics", {}).get("viewCount", 0)),
                    "likes": int(item.get("statistics", {}).get("likeCount", 0)),
                    "duration": dur_sec,
                    "is_cc": is_cc
                })

        seen_ids = set()
        unique_items = []
        for it in all_items:
            if it["id"] not in seen_ids:
                seen_ids.add(it["id"])
                unique_items.append(it)
                
        return unique_items[:max_results]
    except Exception as e:
        st.error(f"인기 급상승 차트 로드 실패: {e}")
        return []


@st.cache_data(ttl=1800, show_spinner=False)
def search_custom_videos(api_key, keyword, category_name="🔥 전체 종합", region_mode="🇰🇷 국내만 (KR)", period_type="전체 기간", selected_year=None, selected_month=None, only_cc=False, length_type="전체", sort_order="viewCount", max_results=30):
    """[2번 탭] 400 에러 해결 및 대량 탐색 엔진"""
    if not api_key:
        return []
    try:
        youtube = build("youtube", "v3", developerKey=api_key)
        
        is_overseas = "해외" in region_mode
        user_kw = keyword.strip()

        if user_kw:
            final_query = user_kw
        else:
            final_query = CATEGORY_QUERY_MAP.get(category_name, {}).get("en" if is_overseas else "kr", "인기")

        all_v_ids = []
        search_params = {
            "q": final_query,
            "part": "snippet",
            "type": "video",
            "order": sort_order,
            "maxResults": 50
        }
        
        pub_after, pub_before = calculate_time_window(period_type, selected_year, selected_month)
        if pub_after:
            search_params["publishedAfter"] = pub_after
        if pub_before:
            search_params["publishedBefore"] = pub_before
        
        if region_mode == "🇰🇷 국내만 (KR)":
            search_params["regionCode"] = "KR"
            search_params["relevanceLanguage"] = "ko"
        elif region_mode == "🌐 해외만 (US/글로벌)":
            search_params["regionCode"] = "US"
            search_params["relevanceLanguage"] = "en"
        
        if only_cc:
            search_params["videoLicense"] = "creativeCommon"
            
        s_res = youtube.search().list(**search_params).execute()
        all_v_ids.extend([it["id"]["videoId"] for it in s_res.get("items", []) if "videoId" in it.get("id", {})])
        
        next_token = s_res.get("nextPageToken")
        if next_token:
            search_params["pageToken"] = next_token
            s_res2 = youtube.search().list(**search_params).execute()
            all_v_ids.extend([it["id"]["videoId"] for it in s_res2.get("items", []) if "videoId" in it.get("id", {})])

        if not all_v_ids:
            return []
            
        detailed_items = fetch_videos_with_details(youtube, all_v_ids)
        
        filtered = []
        for v in detailed_items:
            if is_spam_video(v["title"], v["channel"]):
                continue

            is_shorts_title = bool(re.search(r'(#shorts|#short|#쇼츠)', v["title"], re.IGNORECASE))
            
            if length_type == "⚡ 숏폼만 (60초 이하)" and (v["duration"] > 60 and not is_shorts_title):
                continue
            elif length_type == "🎬 롱폼만 (70초 초과)" and (v["duration"] <= 70 or is_shorts_title):
                continue
                
            filtered.append(v)
            
        if sort_order == "viewCount":
            filtered.sort(key=lambda x: x["views"], reverse=True)
            
        return filtered[:max_results]
    except Exception as e:
        st.error(f"맞춤 영상 탐색 실패: {e}")
        return []


def format_duration(seconds):
    m = seconds // 60
    s = seconds % 60
    return f"{m}:{s:02d}" if m > 0 else f"{s}초"


def render_popular_feed(api_key=None):
    used_api_key = api_key or DEFAULT_API_KEY
    st.markdown("## 🔥 유튜브 실시간 인기 & 맞춤 탐색기")
    st.caption("⚡ 50개 청크 분할 안정화 적용 · 대량 영상 고속 탐색")

    category_list = [
        "🔥 전체 종합", "🎬 엔터테인먼트 (예능/토크)", "🤣 코미디 / 스케치",
        "💪 운동 / 피트니스 / 헬스", "🎥 영화 & 애니메이션", "📰 뉴스 & 이슈 / 썰",
        "🐕 동물 & 반려동물", "🎮 게임"
    ]
    
    region_options = ["🇰🇷 국내만 (KR)", "🌐 해외만 (US/글로벌)", "🌍 국내 + 해외 전체"]
    period_options = ["전체 기간", "📅 일간 (최근 24시간)", "📅 주간 (최근 7일)", "📅 월간 (최근 30일)", "🗓️ 특정 연·월 지정"]
    length_options = ["전체", "🎬 롱폼만 (70초 초과)", "⚡ 숏폼만 (60초 이하)"]

    tab_trend, tab_search = st.tabs(["📈 유튜브 실시간 급상승 차트", "🔍 키워드 & 카테고리/기간 정밀 탐색"])

    # ---------------- 1. 유튜브 공식 실시간 급상승 차트 ----------------
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
            trend_cc = st.checkbox("재사용 가능(CC)만", value=False, key="trend_cc")
        with t_col5:
            st.write("")
            btn_trend = st.button("🔄 차트 갱신", use_container_width=True, key="btn_trend")

        if btn_trend:
            get_official_trending_videos.clear()

        with st.spinner("실시간 유튜브 공식 인기 급상승 차트 불러오는 중..."):
            trend_list = get_official_trending_videos(
                used_api_key,
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
                    if st.button("🎬 이 영상 선택하기", key=f"sel_t_{vid['id']}_{idx}", use_container_width=True):
                        st.session_state["selected_source_url"] = vid["url"]
                        st.success(f"선택 완료! URL: {vid['url']}")
        else:
            st.info("조건에 맞는 급상승 영상이 없습니다. CC 필터를 끄거나 길이를 '전체'로 설정해보세요.")

    # ---------------- 2. 키워드 & 카테고리/기간 정밀 탐색 ----------------
    with tab_search:
        s_col1, s_col2 = st.columns([2, 1])
        with s_col1:
            search_kw = st.text_input("검색 키워드 (비워두면 카테고리 인기 영상 자동 탐색):", placeholder="예: 말왕, 침착맨, 피지컬갤러리, 무한도전", key="s_kw")
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
            search_cc = st.checkbox("재사용 가능(CC)만 보기", value=True, key="s_cc")
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
                    used_api_key,
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
                    if st.button("🎬 이 영상 선택하기", key=f"sel_s_{vid['id']}_{idx}", use_container_width=True):
                        st.session_state["selected_source_url"] = vid["url"]
                        st.success(f"선택 완료! URL: {vid['url']}")
        else:
            st.info(f"선택한 조건([{search_period}])에 맞는 영상이 없습니다. CC 필터를 해제하거나 기간을 완화해보세요.")


if __name__ == "__main__":
    st.set_page_config(page_title="이지컷 인기 영상 피드 모듈", layout="wide")
    render_popular_feed()