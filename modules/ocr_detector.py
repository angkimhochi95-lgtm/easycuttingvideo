# modules/ocr_detector.py
import cv2
import numpy as np
from difflib import SequenceMatcher
import easyocr

_reader = None

def get_ocr_reader():
    global _reader
    if _reader is None:
        # 한국어 및 영어 인식기 로드 (CPU 모드)
        _reader = easyocr.Reader(['ko', 'en'], gpu=False)
    return _reader

def is_subtitle_overlapping(target_text, frame_bgr, crop_ratio_bottom=0.35, threshold=0.40):
    """영상 하단 영역의 기존 자막과 생성할 자막의 중복 여부를 판정하여 겹치면 True 반환"""
    try:
        h, w, _ = frame_bgr.shape
        crop_y = int(h * (1.0 - crop_ratio_bottom))
        roi = frame_bgr[crop_y:h, 0:w]
        
        reader = get_ocr_reader()
        results = reader.readtext(roi, detail=0)
        screen_text = "".join(results).replace(" ", "")
        
        if not screen_text:
            return False
            
        clean_target = target_text.replace(" ", "")
        similarity = SequenceMatcher(None, clean_target, screen_text).ratio()
        
        if similarity >= threshold or clean_target in screen_text or screen_text in clean_target:
            return True
        return False
    except Exception:
        return False