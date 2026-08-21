# modules/youtube_service.py
import re
import isodate
import streamlit as st
from datetime import datetime, timedelta, timezone
from googleapiclient.discovery import build
import config

DEFAULT_YOUTUBE_API_KEY = getattr(config, "DEFAULT_YOUTUBE_API_KEY", "AIzaSyAcMm3MsrdaHGL3rvRkKgSkDtNLxgPVC3A")

SPAM_KEYWORDS = [
    "슬롯", "바카라", "카지노", "홀덤", "토토", "리니지클래식", "레어서버", "프리서버", 
    "먹튀", "머니상", "릴게임", "텔레그램", "telegram", "텔레", "카톡문의", "총판", 
    "가족방", "수익인증", "입장코드", "고정댓글확인", "성인용품", "출장", "조건"
]

CATEGORY_QUERY_MAP = {
    "🔥 전체 종합": {"kr": "인기 하이라이트", "en": "trending highlights"},
    "🎬 엔터테인먼트 (예능/토크)": {"kr": "예능 명장면", "en": "entertainment highlights"},
    "🤣 코미디 / 스케치": {"kr": "코미디 웃긴영상", "en": "comedy scenes"},
    "💪 운동 / 피트니스 / 헬스": {"kr": "운동 헬스 명장면", "en": "workout fitness highlights"},
    "🎥 영화 & 애니메이션": {"kr": "영화 명장면 결말포함", "en": "movie best scenes"},
    "📰 뉴스 & 이슈 / 썰": {"kr": "이슈 썰 하이라이트", "en": "news issue stories"},
    "🐕 동물 & 반려동물": {"kr": "귀여운 동물 힐링", "en": "cute animals moments"},
    "🎮 게임": {"kr": "게임 명장면 하이라이트", "en": "gameplay highlights"}
}

def extract_youtube_video_id(url: str):
    patterns = [
        r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',
        r'youtu\.be\/([0-9A-Za-z_-]{11})',
        r'shorts\/([0-9A-Za-z_-]{11})'
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None

def is_spam_video(title, channel, views=0):
    if views > 0 and views < 50:
        return True
    target_text = f"{title} {channel}".lower()
    if any(kw in target_text for kw in SPAM_KEYWORDS):
        return True
    if re.search(r'(@[a-zA-Z0-9_]+|t\.me\/|bit\.ly\/|open\.kakao)', target_text):
        return True
    return False

def fetch_real_video_comments(api_key: str, video_id: str, max_count: int = 40):
    if not api_key or not video_id:
        return []
    try:
        youtube = build("youtube", "v3", developerKey=api_key)
        res = youtube.commentThreads().list(
            part="snippet",
            videoId=video_id,
            order="relevance",
            maxResults=min(100, max_count)
        ).execute()

        comments = []
        for item in res.get("items", []):
            top_c = item.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
            text = top_c.get("textDisplay", "").replace("\n", " ").strip()
            author = top_c.get("authorDisplayName", "").replace("@", "").strip()
            likes = int(top_c.get("likeCount", 0))

            clean_text = re.sub(r'<[^>]+>', '', text).strip()
            if not clean_text or is_spam_video(clean_text, author):
                continue

            like_str = f"{likes/10000:.1f}만" if likes >= 10000 else (f"{likes/1000:.1f}천" if likes >= 1000 else f"{likes}")
            comments.append({
                "author": author if author else "시청자",
                "text": clean_text[:60],
                "likes": like_str,
                "raw_likes": likes
            })

        comments.sort(key=lambda x: x["raw_likes"], reverse=True)
        return comments[:max_count]
    except Exception:
        return []

def format_duration(seconds):
    m = seconds // 60
    s = seconds % 60
    return f"{m}:{s:02d}" if m > 0 else f"{s}초"

def parse_duration_iso(duration_str):
    try:
        return int(isodate.parse_duration(duration_str).total_seconds())
    except Exception:
        return 0

def calculate_time_window(period_type, selected_year=None, selected_month=None):
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
        end_dt = datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=timezone.utc) if month == 12 else datetime(year, month + 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        return start_dt.strftime('%Y-%m-%dT%H:%M:%SZ'), end_dt.strftime('%Y-%m-%dT%H:%M:%SZ')
    return None, None

def fetch_videos_with_details(youtube, video_ids):
    if not video_ids:
        return []
    items = []
    for i in range(0, len(video_ids), 50):
        chunk = video_ids[i:i + 50]
        res = youtube.videos().list(
            part="snippet,statistics,contentDetails,status",
            id=",".join(chunk)
        ).execute()
        
        for item in res.get("items", []):
            dur_sec = parse_duration_iso(item.get("contentDetails", {}).get("duration", "PT0S"))
            status_info = item.get("status", {})
            pub_at = item.get("snippet", {}).get("publishedAt", "")[:10]
            thumbs = item.get("snippet", {}).get("thumbnails", {})
            medium_thumb = thumbs.get("medium", {}) or thumbs.get("high", {}) or thumbs.get("default", {})
            view_cnt = int(item.get("statistics", {}).get("viewCount", 0))
            
            items.append({
                "id": item["id"],
                "url": f"https://www.youtube.com/watch?v={item['id']}",
                "title": item["snippet"]["title"],
                "channel": item["snippet"]["channelTitle"],
                "published_at": pub_at if pub_at else "날짜 정보 없음",
                "thumb": medium_thumb.get("url", ""),
                "views": view_cnt,
                "likes": int(item.get("statistics", {}).get("likeCount", 0)),
                "duration": dur_sec,
                "is_cc": status_info.get("license") == "creativeCommon"
            })
    return items

@st.cache_data(ttl=1800, show_spinner=False)
def get_official_trending_videos(api_key, category_name="🔥 전체 종합", region_mode="🇰🇷 국내만 (KR)", only_cc=False, length_type="전체", max_results=30):
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
        target_regions = ["US"] if region_mode == "🌐 해외만 (US/글로벌)" else (["KR", "US", "JP"] if region_mode == "🌍 국내 + 해외 전체" else ["KR"])

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
                dur_sec = parse_duration_iso(item.get("contentDetails", {}).get("duration", "PT0S"))
                is_cc = item.get("status", {}).get("license") == "creativeCommon"
                title = item["snippet"]["title"]
                channel = item["snippet"]["channelTitle"]
                pub_at = item.get("snippet", {}).get("publishedAt", "")[:10]
                thumbs = item.get("snippet", {}).get("thumbnails", {})
                medium_thumb = thumbs.get("medium", {}) or thumbs.get("high", {}) or thumbs.get("default", {})
                views = int(item.get("statistics", {}).get("viewCount", 0))

                if is_spam_video(title, channel, views) or (only_cc and not is_cc):
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
                    "thumb": medium_thumb.get("url", ""),
                    "views": views,
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
    if not api_key:
        return []
    try:
        youtube = build("youtube", "v3", developerKey=api_key)
        is_overseas = "해외" in region_mode
        user_kw = keyword.strip()
        final_query = user_kw if user_kw else CATEGORY_QUERY_MAP.get(category_name, {}).get("en" if is_overseas else "kr", "인기 하이라이트")

        all_v_ids = []
        search_params = {
            "q": final_query,
            "part": "snippet",
            "type": "video",
            "order": "relevance",
            "maxResults": 50
        }

        if length_type == "⚡ 숏폼만 (60초 이하)":
            search_params["videoDuration"] = "short"
        elif length_type == "🎬 롱폼만 (70초 초과)":
            search_params["videoDuration"] = "medium"
        
        pub_after, pub_before = calculate_time_window(period_type, selected_year, selected_month)
        if pub_after: search_params["publishedAfter"] = pub_after
        if pub_before: search_params["publishedBefore"] = pub_before
        
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
        if next_token and len(all_v_ids) < 50:
            search_params["pageToken"] = next_token
            s_res2 = youtube.search().list(**search_params).execute()
            all_v_ids.extend([it["id"]["videoId"] for it in s_res2.get("items", []) if "videoId" in it.get("id", {})])

        if not all_v_ids:
            return []
            
        detailed_items = fetch_videos_with_details(youtube, all_v_ids)
        filtered = []
        for v in detailed_items:
            if is_spam_video(v["title"], v["channel"], v["views"]):
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