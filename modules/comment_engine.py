# modules/comment_engine.py
import os
from PIL import Image, ImageDraw, ImageFont

def get_system_font(size: int, bold: bool = False):
    candidate_fonts = [
        "trendy_bold.ttf",
        "C:/Windows/Fonts/malgunbd.ttf",
        "C:/Windows/Fonts/malgun.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"
    ]
    for fp in candidate_fonts:
        if os.path.exists(fp):
            try:
                return ImageFont.truetype(fp, size)
            except Exception:
                continue
    return ImageFont.load_default()

def draw_crisp_heart_icon(draw: ImageDraw.Draw, x: int, y: int, size: int = 24, fill_color=(220, 38, 38, 255)):
    scale = size / 24.0
    points = [
        (x + 12 * scale, y + 21 * scale),
        (x + 3 * scale, y + 12 * scale),
        (x + 3 * scale, y + 6 * scale),
        (x + 8 * scale, y + 2 * scale),
        (x + 12 * scale, y + 6 * scale),
        (x + 16 * scale, y + 2 * scale),
        (x + 21 * scale, y + 6 * scale),
        (x + 21 * scale, y + 12 * scale)
    ]
    draw.polygon(points, fill=fill_color)
    draw.ellipse([x + 3*scale, y + 2*scale, x + 12*scale, y + 11*scale], fill=fill_color)
    draw.ellipse([x + 12*scale, y + 2*scale, x + 21*scale, y + 11*scale], fill=fill_color)

def draw_crisp_comment_bubble(draw: ImageDraw.Draw, x: int, y: int, size: int = 22, fill_color=(160, 160, 160, 255)):
    scale = size / 22.0
    draw.rounded_rectangle([x, y, x + 20 * scale, y + 15 * scale], radius=int(4 * scale), fill=fill_color)
    tail = [(x + 4 * scale, y + 14 * scale), (x + 2 * scale, y + 19 * scale), (x + 9 * scale, y + 14 * scale)]
    draw.polygon(tail, fill=fill_color)

def render_crisp_comment_card(author: str, text: str, likes: str, is_white: bool = False, out_path: str = "comment_card.png"):
    card_w = 840
    card_h = 190
    bg_color = (255, 255, 255, 245) if is_white else (28, 28, 32, 245)
    text_color = (20, 20, 20, 255) if is_white else (245, 245, 245, 255)
    meta_color = (110, 110, 110, 255) if is_white else (160, 160, 160, 255)
    
    img = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([0, 0, card_w, card_h], radius=18, fill=bg_color)
    
    avatar_colors = [(225, 29, 72), (37, 99, 235), (13, 148, 136), (217, 119, 6)]
    bg_avatar = avatar_colors[abs(hash(author)) % len(avatar_colors)]
    draw.ellipse([25, 25, 75, 75], fill=bg_avatar)
    initial = author[0].upper() if author else "U"
    draw.text((41, 33), initial, fill=(255, 255, 255, 255), font=get_system_font(26, bold=True))
    
    draw.text((90, 25), f"@{author}", fill=meta_color, font=get_system_font(20, bold=True))
    id_w = draw.textbbox((0, 0), f"@{author}", font=get_system_font(20, bold=True))[2]
    draw.text((90 + id_w + 12, 27), "· 방금 전", fill=meta_color, font=get_system_font(16))
    
    display_text = text if len(text) <= 32 else text[:30] + "..."
    draw.text((90, 64), display_text, fill=text_color, font=get_system_font(23, bold=True))
    
    draw_crisp_heart_icon(draw, x=90, y=130, size=20, fill_color=(225, 29, 72, 255))
    draw.text((118, 128), str(likes), fill=text_color, font=get_system_font(18, bold=True))
    
    draw_crisp_comment_bubble(draw, x=220, y=130, size=19, fill_color=meta_color)
    draw.text((246, 128), "답글", fill=meta_color, font=get_system_font(16))
    
    img.save(out_path)
    return out_path