import os
import shutil
import random
import subprocess
import textwrap
import requests
import streamlit as st
from PIL import Image, ImageDraw, ImageFont
import arabic_reshaper
from bidi.algorithm import get_display
import imageio_ffmpeg

# إعدادات الصفحة والتصميم
st.set_page_config(page_title="Quran Reels Studio | Belal A Eisa", page_icon="🕌", layout="centered")

WIDTH, HEIGHT = 1080, 1920
QURAN_FONT_PATH = "UthmanicHafs.ttf"
UI_FONT_PATH = "Amiri-Bold.ttf"
TEMP_DIR = "temp_quran_pro"
DEFAULT_WATERMARK = "Belal A Eisa"

FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()

RECITERS = {
    "مشاري العفاسي": "Alafasy_128kbps",
    "محمد صديق المنشاوي (مجود)": "Minshawy_Mujawwad_192kbps",
    "محمد صديق المنشاوي (مرتل)": "Minshawy_Murattal_128kbps",
    "محمود خليل الحصري": "Husary_128kbps",
    "عبد الباسط عبد الصمد (مرتل)": "Abdul_Basit_Murattal_192kbps",
    "ماهر المعيقلي": "MaherAlMuaiqly128kbps",
    "ياسر الدوسري": "Yasser_Ad-Dussary_128kbps",
    "سعود الشريم": "Saood_ash-Shuraym_128kbps",
    "محمود علي البنا": "Mahmoud_Ali_Al_Banna_32kbps",
    "ناصر القطامي": "Nasser_Alqatami_128kbps"
}

@st.cache_resource
def download_files():
    if not os.path.exists(QURAN_FONT_PATH):
        r = requests.get("https://github.com/quran/quran.com-frontend-next/raw/production/public/fonts/quran/hafs/uthmanic_hafs/UthmanicHafs1Ver18.ttf")
        open(QURAN_FONT_PATH, "wb").write(r.content)
    if not os.path.exists(UI_FONT_PATH):
        r = requests.get("https://github.com/google/fonts/raw/main/ofl/amiri/Amiri-Bold.ttf")
        open(UI_FONT_PATH, "wb").write(r.content)

download_files()

def format_arabic(text):
    return get_display(arabic_reshaper.reshape(text))

def get_ayah_full_data(surah, ayah, include_en=True):
    url = f"http://api.alquran.cloud/v1/ayah/{surah}:{ayah}/editions/quran-uthmani,en.sahih"
    try:
        res = requests.get(url, timeout=15).json()
        if res.get("code") == 200:
            data = res["data"]
            return data[0]["text"], data[0]["surah"]["name"], data[0]["surah"]["englishName"], (data[1]["text"] if include_en else "")
    except Exception:
        pass
    
    url_alt = f"http://api.alquran.cloud/v1/ayah/{surah}:{ayah}/quran-uthmani"
    res_alt = requests.get(url_alt, timeout=15).json()
    if res_alt.get("code") == 200:
        d = res_alt["data"]
        return d["text"], d["surah"]["name"], d["surah"]["englishName"], "Translation unavailable."
    raise Exception(f"تعذر جلب الآية {surah}:{ayah}")

def download_audio(surah, ayah, reciter_id, out_path):
    url = f"https://everyayah.com/data/{reciter_id}/{surah:03d}{ayah:03d}.mp3"
    res = requests.get(url, stream=True, timeout=15)
    if res.status_code == 200:
        with open(out_path, "wb") as f:
            for chunk in res.iter_content(1024):
                f.write(chunk)

def draw_arabic_text(draw, pos, text, font, fill, shadow_fill=(0, 0, 0, 220)):
    x, y = pos
    formatted_text = format_arabic(text)
    if shadow_fill:
        draw.text((x + 2, y + 3), formatted_text, font=font, fill=shadow_fill, anchor="mm")
    draw.text((x, y), formatted_text, font=font, fill=fill, anchor="mm")

def create_pro_overlay(ar_text, surah_ar, surah_en, ayah_num, en_text, reciter_name, progress_ratio, watermark, out_png):
    img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    dark_layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 125))
    img = Image.alpha_composite(img, dark_layer)

    card_layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    card_draw = ImageDraw.Draw(card_layer)
    card_margin_x = 55
    card_top, card_bottom = 190, HEIGHT - 185
    
    # الكارت الزجاجي الفاخر
    card_draw.rounded_rectangle([card_margin_x, card_top, WIDTH - card_margin_x, card_bottom], radius=40, fill=(10, 15, 25, 160), outline=(212, 175, 55, 120), width=2)

    # كبسولة العلامة المائية في الأسفل
    if watermark:
        wm_box_w, wm_box_h = 340, 58
        wm_x1, wm_y1 = (WIDTH - wm_box_w) // 2, HEIGHT - 155
        card_draw.rounded_rectangle([wm_x1, wm_y1, wm_x1 + wm_box_w, wm_y1 + wm_box_h], radius=28, fill=(10, 15, 25, 200), outline=(212, 175, 55, 140), width=2)
        card_draw.ellipse([wm_x1 + 22, wm_y1 + 22, wm_x1 + 32, wm_y1 + 32], fill=(212, 175, 55, 240))
        card_draw.ellipse([wm_x1 + wm_box_w - 32, wm_y1 + 22, wm_x1 + wm_box_w - 22, wm_y1 + 32], fill=(212, 175, 55, 240))

    img = Image.alpha_composite(img, card_layer)
    draw = ImageDraw.Draw(img)

    font_header = ImageFont.truetype(UI_FONT_PATH, 42)
    font_en = ImageFont.truetype(UI_FONT_PATH, 26)
    font_footer = ImageFont.truetype(UI_FONT_PATH, 26)
    font_wm = ImageFont.truetype(UI_FONT_PATH, 26)

    # رأس الكارت (اسم السورة ورقمها)
    draw_arabic_text(draw, (WIDTH // 2, card_top + 65), f"✦ {surah_ar} ✦", font_header, (212, 175, 55, 255))
    draw.text((WIDTH // 2, card_top + 115), f"Surah {surah_en} • Ayah {ayah_num}", font=font_footer, fill=(200, 200, 200, 210), anchor="mm")
    draw.line([(WIDTH // 2 - 150, card_top + 145), (WIDTH // 2 + 150, card_top + 145)], fill=(212, 175, 55, 120), width=2)

    # نظام التصغير التلقائي الذكي لمقاس خط الآية حسب طول النص
    text_len = len(ar_text)
    if text_len > 300:
        font_ar_size, wrap_w, line_h = 42, 36, 68
    elif text_len > 150:
        font_ar_size, wrap_w, line_h = 48, 32, 78
    else:
        font_ar_size, wrap_w, line_h = 56, 28, 90

    font_ar = ImageFont.truetype(QURAN_FONT_PATH, font_ar_size)

    ar_lines = textwrap.wrap(ar_text, width=wrap_w)
    en_lines = textwrap.wrap(en_text, width=55) if en_text else []
    en_line_h = 36
    
    total_text_h = (len(ar_lines) * line_h) + (len(en_lines) * en_line_h) + (30 if en_lines else 0)
    
    # حساب نقطة البداية للمنتصف بدقة شديدة لتفادي أي تداخل مع الاسم أو العلامة
    available_space = (card_bottom - 120) - (card_top + 175)
    current_y = card_top + 175 + max(10, (available_space - total_text_h) // 2)
    arabic_digits = str(ayah_num).translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩"))

    for i, line in enumerate(ar_lines):
        if i == len(ar_lines) - 1:
            line = f"{line} ﴿{arabic_digits}﴾"
        draw_arabic_text(draw, (WIDTH // 2, current_y), line, font_ar, (255, 255, 255, 255))
        current_y += line_h

    if en_lines:
        current_y += 15
        for line in en_lines:
            draw.text((WIDTH // 2 + 1, current_y + 1), line, font=font_en, fill=(0, 0, 0, 220), anchor="mm")
            draw.text((WIDTH // 2, current_y), line, font=font_en, fill=(210, 220, 235, 240), anchor="mm")
            current_y += en_line_h

    # شريط التقدم (Progress Bar) وقارئ الآية
    bar_w = WIDTH - (card_margin_x * 2) - 120
    bar_x1, bar_y = (WIDTH - bar_w) // 2, card_bottom - 95
    draw.rounded_rectangle([bar_x1, bar_y, bar_x1 + bar_w, bar_y + 6], radius=3, fill=(255, 255, 255, 45))
    fill_w = max(10, int(bar_w * progress_ratio))
    draw.rounded_rectangle([bar_x1, bar_y, bar_x1 + fill_w, bar_y + 6], radius=3, fill=(212, 175, 55, 255))

    draw_arabic_text(draw, (WIDTH // 2, card_bottom - 55), f"القارئ: {reciter_name}", font_footer, (212, 175, 55, 235))
    if watermark:
        draw.text((WIDTH // 2, HEIGHT - 125), watermark, font=font_wm, fill=(245, 245, 245, 245), anchor="mm")

    img.save(out_png)

def build_segment_ffmpeg(bg_path, overlay_png, audio_mp3, out_mp4):
    cmd = [FFMPEG_PATH, "-y", "-loop", "1", "-i", bg_path, "-i", overlay_png, "-i", audio_mp3,
           "-filter_complex", f"[0:v]scale=1200:2134:force_original_aspect_ratio=increase,crop=1200:2134,zoompan=z='min(zoom+0.0005,1.15)':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={WIDTH}x{HEIGHT}:fps=25,setsar=1[bg];[bg][1:v]overlay=0:0[outv]",
           "-map", "[outv]", "-map", "2:a", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-b:a", "192k", "-pix_fmt", "yuv420p", "-shortest", out_mp4]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

# واجهة Streamlit المرئية
st.title("🕌 استوديو ريلز القرآن الكريم")
st.markdown(f"### تصميم وإخراج: **{DEFAULT_WATERMARK}**")
st.write("أنشئ فيديوهات ريلز قرآنية احترافية بدقة عالية مع التلاوة، الرسم العثماني، الترجمة، والعلامة المائية بضغطة زر واحدة.")

surah_num = st.number_input("رقم السورة (من 1 إلى 114):", min_value=1, max_value=114, value=67)
col1, col2 = st.columns(2)
with col1:
    start_ayah = st.number_input("من الآية رقم:", min_value=1, value=1)
with col2:
    end_ayah = st.number_input("إلى الآية رقم:", min_value=1, value=5)

selected_reciter_name = st.selectbox("اختر القارئ:", list(RECITERS.keys()))
include_english = st.checkbox("إضافة الترجمة الإنجليزية تحت الآية", value=True)

if st.button("🎬 ابدأ إنشاء الريل الآن"):
    with st.spinner("⏳ جاري معالجة الصوت والآيات ورندر الفيديو... انتظر قليلاً"):
        os.makedirs(TEMP_DIR, exist_ok=True)
        reciter_id = RECITERS[selected_reciter_name]
        
        bg_path = os.path.join(TEMP_DIR, "grad_bg.png")
        img = Image.new("RGB", (WIDTH, HEIGHT))
        draw = ImageDraw.Draw(img)
        for y in range(HEIGHT):
            r, g, b_val = int(8 + (y/HEIGHT)*10), int(18 + (y/HEIGHT)*28), int(28 + (y/HEIGHT)*35)
            draw.line([(0, y), (WIDTH, y)], fill=(r, g, b_val))
        img.save(bg_path)

        segment_files = []
        ayah_list = list(range(start_ayah, end_ayah + 1))
        total = len(ayah_list)

        for idx, ayah in enumerate(ayah_list, 1):
            ar_text, surah_ar, surah_en, en_text = get_ayah_full_data(surah_num, ayah, include_english)
            aud = os.path.join(TEMP_DIR, f"aud_{ayah}.mp3")
            ovr = os.path.join(TEMP_DIR, f"ovr_{ayah}.png")
            seg = os.path.join(TEMP_DIR, f"seg_{ayah}.mp4")

            download_audio(surah_num, ayah, reciter_id, aud)
            create_pro_overlay(ar_text, surah_ar, surah_en, ayah, en_text, selected_reciter_name, idx/total, DEFAULT_WATERMARK, ovr)
            build_segment_ffmpeg(bg_path, ovr, aud, seg)
            segment_files.append(seg)

        concat_txt = os.path.join(TEMP_DIR, "concat.txt")
        with open(concat_txt, "w", encoding="utf-8") as f:
            for seg in segment_files:
                f.write(f"file '{os.path.abspath(seg)}'\n")

        out_name = f"Quran_PRO_S{surah_num}_A{start_ayah}-{end_ayah}.mp4"
        concat_cmd = [FFMPEG_PATH, "-y", "-f", "concat", "-safe", "0", "-i", concat_txt, "-c", "copy", out_name]
        subprocess.run(concat_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        
        if os.path.exists(out_name):
            st.success("✅ تم إنشاء الفيديو بنجاح وبأعلى جودة!")
            with open(out_name, "rb") as f:
                video_bytes = f.read()
                st.video(video_bytes)
                st.download_button(
                    label="📥 تحميل الفيديو على جهازك (مباشر)",
                    data=video_bytes,
                    file_name=out_name,
                    mime="video/mp4"
                )
        else:
            st.error("❌ حدث خطأ أثناء دمج الفيديو النهائي، يرجى المحاولة مرة أخرى.")
        
        shutil.rmtree(TEMP_DIR, ignore_errors=True)
