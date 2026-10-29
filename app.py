import os
import shutil
import subprocess
import requests
import streamlit as st
from PIL import Image, ImageDraw, ImageFont
import imageio_ffmpeg
import arabic_reshaper
from bidi.algorithm import get_display

# =========================================================
# Quran Reels Studio
# =========================================================

st.set_page_config(
    page_title="Quran Reels Studio | Belal A Eisa",
    page_icon="🕌",
    layout="centered",
)

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
    "ناصر القطامي": "Nasser_Alqatami_128kbps",
}

FONT_URLS = {
    QURAN_FONT_PATH: (
        "https://github.com/quran/quran.com-frontend-next/raw/"
        "production/public/fonts/quran/hafs/uthmanic_hafs/"
        "UthmanicHafs1Ver18.ttf"
    ),
    UI_FONT_PATH: (
        "https://github.com/google/fonts/raw/main/"
        "ofl/amiri/Amiri-Bold.ttf"
    ),
}

# Preserve Arabic diacritics when reshaping.
ARABIC_RESHAPER = arabic_reshaper.ArabicReshaper(
    configuration={
        "delete_harakat": False,
        "shift_harakat_position": True,
        "support_ligatures": True,
    }
)


# =========================================================
# Fonts
# =========================================================

def download_file_if_missing(path, url):
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return

    response = requests.get(url, timeout=30)
    response.raise_for_status()

    if not response.content:
        raise RuntimeError(f"ملف الخط فارغ: {path}")

    with open(path, "wb") as file:
        file.write(response.content)


@st.cache_resource
def prepare_fonts():
    for path, url in FONT_URLS.items():
        download_file_if_missing(path, url)

    # Verify that the font files can actually be opened.
    ImageFont.truetype(QURAN_FONT_PATH, 40)
    ImageFont.truetype(UI_FONT_PATH, 30)
    return True


try:
    prepare_fonts()
except Exception as exc:
    st.error(f"تعذر تجهيز الخطوط: {exc}")
    st.stop()


def make_font(path, size):
    return ImageFont.truetype(path, size)


# =========================================================
# Arabic text processing
# =========================================================

def prepare_display_text(text, direction=None):
    """
    Prepare Arabic text for Pillow without libraqm.
    Keep the original text intact for API/audio purposes.
    """
    if direction == "rtl":
        return get_display(ARABIC_RESHAPER.reshape(text))
    return text


def draw_centered_text(
    draw,
    xy,
    text,
    font,
    fill,
    shadow=True,
    direction=None,
):
    x, y = xy
    display_text = prepare_display_text(text, direction)

    if shadow:
        draw.text(
            (x + 2, y + 3),
            display_text,
            font=font,
            fill=(0, 0, 0, 220),
            anchor="mm",
        )

    draw.text(
        (x, y),
        display_text,
        font=font,
        fill=fill,
        anchor="mm",
    )


def wrap_text_by_pixel_width(
    text,
    font,
    draw,
    max_width,
    direction=None,
):
    """Wrap text according to rendered pixel width."""
    words = text.split()
    lines = []
    current = ""

    for word in words:
        candidate = f"{current} {word}".strip()
        display_candidate = prepare_display_text(
            candidate, direction
        )

        bbox = draw.textbbox(
            (0, 0),
            display_candidate,
            font=font,
        )

        width = bbox[2] - bbox[0]

        if width <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word

    if current:
        lines.append(current)

    return lines


# =========================================================
# Quran API and audio
# =========================================================

def get_ayah_full_data(surah, ayah, include_en=True):
    url = (
        f"https://api.alquran.cloud/v1/ayah/"
        f"{surah}:{ayah}/editions/quran-uthmani,en.sahih"
    )

    try:
        response = requests.get(url, timeout=20)
        response.raise_for_status()
        payload = response.json()

        if payload.get("code") == 200:
            data = payload["data"]

            return (
                data[0]["text"],
                data[0]["surah"]["name"],
                data[0]["surah"]["englishName"],
                data[1]["text"] if include_en else "",
            )

    except Exception:
        pass

    # Arabic-only fallback.
    fallback_url = (
        f"https://api.alquran.cloud/v1/ayah/"
        f"{surah}:{ayah}/quran-uthmani"
    )

    response = requests.get(fallback_url, timeout=20)
    response.raise_for_status()
    payload = response.json()

    if payload.get("code") == 200:
        data = payload["data"]

        return (
            data["text"],
            data["surah"]["name"],
            data["surah"]["englishName"],
            "Translation unavailable." if include_en else "",
        )

    raise RuntimeError(
        f"تعذر جلب الآية {surah}:{ayah}"
    )


def download_audio(surah, ayah, reciter_id, out_path):
    url = (
        f"https://everyayah.com/data/{reciter_id}/"
        f"{surah:03d}{ayah:03d}.mp3"
    )

    response = requests.get(
        url,
        stream=True,
        timeout=30,
    )
    response.raise_for_status()

    total_bytes = 0

    with open(out_path, "wb") as audio_file:
        for chunk in response.iter_content(
            chunk_size=65536
        ):
            if chunk:
                audio_file.write(chunk)
                total_bytes += len(chunk)

    if total_bytes < 1000:
        raise RuntimeError(
            f"ملف صوت الآية {surah}:{ayah} غير صالح "
            "أو غير متوفر للقارئ المختار."
        )


# =========================================================
# Overlay design
# =========================================================

def create_pro_overlay(
    ar_text,
    surah_ar,
    surah_en,
    ayah_num,
    surah_num,
    en_text,
    reciter_name,
    progress_ratio,
    watermark,
    out_png,
):
    img = Image.new(
        "RGBA",
        (WIDTH, HEIGHT),
        (0, 0, 0, 0),
    )

    dark_layer = Image.new(
        "RGBA",
        (WIDTH, HEIGHT),
        (0, 0, 0, 125),
    )

    img = Image.alpha_composite(img, dark_layer)

    card_layer = Image.new(
        "RGBA",
        (WIDTH, HEIGHT),
        (0, 0, 0, 0),
    )

    card_draw = ImageDraw.Draw(card_layer)

    card_margin_x = 55
    card_top = 190
    card_bottom = HEIGHT - 185

    card_draw.rounded_rectangle(
        [
            card_margin_x,
            card_top,
            WIDTH - card_margin_x,
            card_bottom,
        ],
        radius=40,
        fill=(10, 15, 25, 160),
        outline=(212, 175, 55, 120),
        width=2,
    )

    # Watermark frame
    if watermark:
        wm_box_w = 340
        wm_box_h = 58
        wm_x1 = (WIDTH - wm_box_w) // 2
        wm_y1 = HEIGHT - 155

        card_draw.rounded_rectangle(
            [
                wm_x1,
                wm_y1,
                wm_x1 + wm_box_w,
                wm_y1 + wm_box_h,
            ],
            radius=28,
            fill=(10, 15, 25, 200),
            outline=(212, 175, 55, 140),
            width=2,
        )

        card_draw.ellipse(
            [
                wm_x1 + 22,
                wm_y1 + 22,
                wm_x1 + 32,
                wm_y1 + 32,
            ],
            fill=(212, 175, 55, 240),
        )

        card_draw.ellipse(
            [
                wm_x1 + wm_box_w - 32,
                wm_y1 + 22,
                wm_x1 + wm_box_w - 22,
                wm_y1 + 32,
            ],
            fill=(212, 175, 55, 240),
        )

    img = Image.alpha_composite(img, card_layer)
    draw = ImageDraw.Draw(img)

    # Use the Quran font for Quran text to retain its intended style.
    font_ar = make_font(QURAN_FONT_PATH, 52)
    font_header = make_font(UI_FONT_PATH, 42)
    font_en = make_font(UI_FONT_PATH, 26)
    font_footer = make_font(UI_FONT_PATH, 26)
    font_watermark = make_font(UI_FONT_PATH, 26)

    # Surah heading
    draw_centered_text(
        draw,
        (WIDTH // 2, card_top + 65),
        f"✦ {surah_ar} ✦",
        font_header,
        (212, 175, 55, 255),
        direction="rtl",
    )

    draw_centered_text(
        draw,
        (WIDTH // 2, card_top + 115),
        f"Surah {surah_en} • Ayah {ayah_num}",
        font_footer,
        (200, 200, 200, 210),
        shadow=False,
        direction="ltr",
    )

    draw.line(
        [
            (WIDTH // 2 - 150, card_top + 145),
            (WIDTH // 2 + 150, card_top + 145),
        ],
        fill=(212, 175, 55, 120),
        width=2,
    )

    # The basmala is displayed separately for surahs that
    # conventionally begin with it, except Al-Fatiha and At-Tawbah.
    show_bismillah = (
        int(ayah_num) == 1
        and int(surah_num) not in (1, 9)
    )

    bismillah = "بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ"

    if show_bismillah:
        draw_centered_text(
            draw,
            (WIDTH // 2, card_top + 220),
            bismillah,
            font_ar,
            (255, 255, 255, 255),
            direction="rtl",
        )

    # The API ayah text remains untouched. For most surahs,
    # the basmala is not part of ayah 1 in the API response.
    display_ar_text = ar_text

    max_text_width = WIDTH - 180

    ar_lines = wrap_text_by_pixel_width(
        display_ar_text,
        font_ar,
        draw,
        max_text_width,
        direction="rtl",
    )

    en_lines = (
        wrap_text_by_pixel_width(
            en_text,
            font_en,
            draw,
            WIDTH - 180,
            direction="ltr",
        )
        if en_text
        else []
    )

    # Leave space below the separate basmala.
    content_top = (
        card_top + 310
        if show_bismillah
        else card_top + 175
    )

    content_bottom = card_bottom - 125
    available_height = content_bottom - content_top

    ar_line_h = 82
    en_line_h = 38
    language_gap = 28 if en_lines else 0

    total_text_height = (
        len(ar_lines) * ar_line_h
        + len(en_lines) * en_line_h
        + language_gap
    )

    # Reduce font size for longer ayahs.
    if total_text_height > available_height:
        font_ar = make_font(QURAN_FONT_PATH, 44)
        ar_line_h = 70

        ar_lines = wrap_text_by_pixel_width(
            display_ar_text,
            font_ar,
            draw,
            max_text_width,
            direction="rtl",
        )

        total_text_height = (
            len(ar_lines) * ar_line_h
            + len(en_lines) * en_line_h
            + language_gap
        )

    current_y = (
        content_top
        + max(
            0,
            (available_height - total_text_height) // 2,
        )
    )

    arabic_digits = str(ayah_num).translate(
        str.maketrans(
            "0123456789",
            "٠١٢٣٤٥٦٧٨٩",
        )
    )

    # Draw Arabic ayah lines without reversing word order.
    for index, line in enumerate(ar_lines):
        if index == len(ar_lines) - 1:
            line = f"{line} ﴿{arabic_digits}﴾"

        draw_centered_text(
            draw,
            (WIDTH // 2, current_y),
            line,
            font_ar,
            (255, 255, 255, 255),
            direction="rtl",
        )

        current_y += ar_line_h

    # English translation
    if en_lines:
        current_y += language_gap

        for line in en_lines:
            draw_centered_text(
                draw,
                (WIDTH // 2, current_y),
                line,
                font_en,
                (210, 220, 235, 240),
                direction="ltr",
            )

            current_y += en_line_h

    # Progress bar
    bar_w = WIDTH - (card_margin_x * 2) - 120
    bar_x1 = (WIDTH - bar_w) // 2
    bar_y = card_bottom - 95

    draw.rounded_rectangle(
        [
            bar_x1,
            bar_y,
            bar_x1 + bar_w,
            bar_y + 6,
        ],
        radius=3,
        fill=(255, 255, 255, 45),
    )

    fill_w = max(
        10,
        min(bar_w, int(bar_w * progress_ratio)),
    )

    draw.rounded_rectangle(
        [
            bar_x1,
            bar_y,
            bar_x1 + fill_w,
            bar_y + 6,
        ],
        radius=3,
        fill=(212, 175, 55, 255),
    )

    # Reciter
    draw_centered_text(
        draw,
        (WIDTH // 2, card_bottom - 55),
        f"القارئ: {reciter_name}",
        font_footer,
        (212, 175, 55, 235),
        direction="rtl",
    )

    # Watermark
    if watermark:
        draw_centered_text(
            draw,
            (WIDTH // 2, HEIGHT - 125),
            watermark,
            font_watermark,
            (245, 245, 245, 245),
            shadow=False,
            direction="ltr",
        )

    img.save(out_png)


# =========================================================
# FFmpeg video rendering
# =========================================================

def build_segment_ffmpeg(
    bg_path,
    overlay_png,
    audio_mp3,
    out_mp4,
):
    cmd = [
        FFMPEG_PATH,
        "-y",
        "-loop", "1",
        "-i", bg_path,
        "-i", overlay_png,
        "-i", audio_mp3,
        "-filter_complex",
        (
            "[0:v]scale=1200:2134:"
            "force_original_aspect_ratio=increase,"
            "crop=1200:2134,"
            "zoompan=z='min(zoom+0.0005,1.15)':d=1:"
            f"x='iw/2-(iw/zoom/2)':"
            f"y='ih/2-(ih/zoom/2)':"
            f"s={WIDTH}x{HEIGHT}:fps=25,"
            "setsar=1[bg];"
            "[bg][1:v]overlay=0:0[outv]"
        ),
        "-map", "[outv]",
        "-map", "2:a",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-c:a", "aac",
        "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-shortest",
        out_mp4,
    ]

    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "فشل FFmpeg في إنشاء مقطع الفيديو:\n"
            + (
                result.stderr[-2500:]
                if result.stderr
                else "سبب غير معروف"
            )
        )


# =========================================================
# Validate surah and ayah range
# =========================================================

AYAH_COUNTS = [
    7, 286, 200, 176, 120, 165, 206, 75, 129, 109,
    123, 111, 43, 52, 99, 128, 111, 110, 98, 135,
    112, 78, 118, 64, 77, 227, 93, 88, 69, 60,
    34, 30, 73, 54, 45, 83, 182, 88, 75, 85,
    54, 53, 89, 59, 37, 35, 38, 29, 18, 45,
    60, 49, 62, 55, 78, 96, 29, 22, 24, 13,
    14, 11, 11, 18, 12, 12, 30, 52, 52, 44,
    28, 28, 20, 56, 40, 31, 50, 40, 46, 42,
    29, 19, 36, 25, 22, 17, 19, 26, 30, 20,
    15, 21, 11, 8, 8, 19, 5, 8, 8, 11,
    11, 8, 3, 9, 5, 4, 7, 3, 6, 3,
    5, 4, 5, 6,
]


def validate_inputs(surah_num, start_ayah, end_ayah):
    if start_ayah > end_ayah:
        st.error(
            "رقم الآية الأولى يجب ألا يتجاوز رقم الآية الأخيرة."
        )
        return False

    max_ayah = AYAH_COUNTS[surah_num - 1]

    if end_ayah > max_ayah:
        st.error(
            f"السورة رقم {surah_num} عدد آياتها "
            f"{max_ayah} فقط."
        )
        return False

    return True


# =========================================================
# Streamlit interface
# =========================================================

st.title("🕌 استوديو ريلز القرآن الكريم")

st.markdown(
    f"### تصميم وإخراج: **{DEFAULT_WATERMARK}**"
)

st.write(
    "إنشاء فيديوهات ريلز قرآنية بالتلاوة، والرسم العثماني، "
    "والترجمة الإنجليزية، والعلامة المائية."
)

surah_num = st.number_input(
    "رقم السورة (من 1 إلى 114):",
    min_value=1,
    max_value=114,
    value=18,
    step=1,
)

col1, col2 = st.columns(2)

with col1:
    start_ayah = st.number_input(
        "من الآية رقم:",
        min_value=1,
        max_value=286,
        value=1,
        step=1,
    )

with col2:
    end_ayah = st.number_input(
        "إلى الآية رقم:",
        min_value=1,
        max_value=286,
        value=3,
        step=1,
    )

selected_reciter_name = st.selectbox(
    "اختر القارئ:",
    list(RECITERS.keys()),
)

include_english = st.checkbox(
    "إضافة الترجمة الإنجليزية تحت الآية",
    value=True,
)

watermark_text = st.text_input(
    "العلامة المائية:",
    value=DEFAULT_WATERMARK,
)


if st.button("🎬 ابدأ إنشاء الريل الآن", type="primary"):

    if not validate_inputs(
        int(surah_num),
        int(start_ayah),
        int(end_ayah),
    ):
        st.stop()

    shutil.rmtree(TEMP_DIR, ignore_errors=True)
    os.makedirs(TEMP_DIR, exist_ok=True)

    out_name = (
        f"Quran_PRO_S{int(surah_num)}_"
        f"A{int(start_ayah)}-{int(end_ayah)}.mp4"
    )

    try:
        reciter_id = RECITERS[selected_reciter_name]

        bg_path = os.path.join(
            TEMP_DIR, "grad_bg.png"
        )

        bg = Image.new("RGB", (WIDTH, HEIGHT))
        bg_draw = ImageDraw.Draw(bg)

        for y in range(HEIGHT):
            r = int(8 + (y / HEIGHT) * 10)
            g = int(18 + (y / HEIGHT) * 28)
            b = int(28 + (y / HEIGHT) * 35)

            bg_draw.line(
                [(0, y), (WIDTH, y)],
                fill=(r, g, b),
            )

        bg.save(bg_path)

        ayah_list = list(
            range(
                int(start_ayah),
                int(end_ayah) + 1,
            )
        )

        segment_files = []
        total = len(ayah_list)
        progress = st.progress(0)
        status = st.empty()

        with st.spinner("⏳ جاري إنشاء الفيديو..."):

            for index, ayah in enumerate(
                ayah_list, start=1
            ):
                status.info(
                    f"جاري تجهيز الآية {ayah} من {end_ayah}..."
                )

                (
                    ar_text,
                    surah_ar,
                    surah_en,
                    en_text,
                ) = get_ayah_full_data(
                    int(surah_num),
                    ayah,
                    include_english,
                )

                audio_path = os.path.join(
                    TEMP_DIR, f"aud_{ayah}.mp3"
                )

                overlay_path = os.path.join(
                    TEMP_DIR, f"ovr_{ayah}.png"
                )

                segment_path = os.path.join(
                    TEMP_DIR, f"seg_{ayah}.mp4"
                )

                download_audio(
                    int(surah_num),
                    ayah,
                    reciter_id,
                    audio_path,
                )

                create_pro_overlay(
                    ar_text=ar_text,
                    surah_ar=surah_ar,
                    surah_en=surah_en,
                    ayah_num=ayah,
                    surah_num=int(surah_num),
                    en_text=en_text,
                    reciter_name=selected_reciter_name,
                    progress_ratio=index / total,
                    watermark=watermark_text.strip(),
                    out_png=overlay_path,
                )
if index == 1:
    st.image(
        overlay_path,
        caption="معاينة التصميم قبل دمجه مع الفيديو",
        use_container_width=True,
    )