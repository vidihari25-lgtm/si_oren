import streamlit as st
import os
import re
import time
import requests
import cv2
import numpy as np
import subprocess
import asyncio
import json
import random
import edge_tts 
import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

# --- IMPORT AI ---
import google.generativeai as genai

# --- IMPORT SELENIUM ---
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By 

# --- KONFIGURASI HALAMAN ---
st.set_page_config(page_title="Shopee Video Creator", page_icon="🛍️", layout="wide")

# --- CSS CUSTOM ---
st.markdown("""
<style>
    .stTextArea textarea {font-size: 16px !important;}
    div[data-testid="stImage"] img {border-radius: 10px;}
    .stButton button {background-color: #EE4D2D; color: white;}
</style>
""", unsafe_allow_html=True)

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Pengaturan")
    if "GEMINI_API_KEY" in st.secrets:
        api_key = st.secrets["GEMINI_API_KEY"]
        st.success("Status: API Key Terhubung ✅")
    else:
        api_key = st.text_input("Gemini API Key", type="password", help="Masukkan API Key Gemini Anda")

    st.caption("Tanpa API Key, sistem akan menggunakan template manual.")
    st.markdown("---")
    st.info("💡 Jika Scraper gagal, gunakan fitur **Upload Gambar Manual**.")

st.title("🛍️ Shopee Video Generator: Anti-Logo")
st.markdown("Otomatis memfilter logo bank/kurir dan mengambil gambar produk asli.")

# --- 1. FUNGSI SCRAPER (SMART FILTER) ---
def scrape_shopee_complete(url):
    chrome_options = Options()
    # Setting wajib Streamlit Cloud
    chrome_options.add_argument("--headless") 
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    # Anti-detect
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    # LOKASI BINARY SYSTEM (PENTING BUAT FIX ERROR VERSI)
    chrome_options.binary_location = "/usr/bin/chromium"
    
    driver = None
    data = {"images": [], "title": "", "description": []}
    error_message = None

    try:
        # GUNAKAN DRIVER SYSTEM, BUKAN WEBDRIVER MANAGER
        service = Service("/usr/bin/chromedriver")
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        st.toast("🕵️ Mengakses Shopee...")
        driver.get(url)
        time.sleep(2) 
        
        # --- SCROLLING AGRESIF AGAR PRODUK LOADING ---
        st.toast("⬇️ Sedang mencari gambar produk...")
        for _ in range(5):
            driver.execute_script("window.scrollBy(0, 500);")
            time.sleep(1)
        # Scroll balik ke atas jaga-jaga
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(1)

        # --- AMBIL JUDUL ---
        try:
            clean_url = url.split('?')[0]
            slug = clean_url.split('/')[-1]
            slug_clean = re.sub(r'\.i\.\d+\.\d+$', '', slug)
            final_title = slug_clean.replace('-', ' ')
            data["title"] = final_title if final_title else "Produk Shopee"
        except:
            data["title"] = "Produk Tanpa Nama"

        # --- AMBIL GAMBAR DENGAN FILTER LOGO ---
        found_urls = set()
        
        # Daftar kata kunci sampah (Logo Bank, Kurir, dll)
        BLACKLIST_KEYWORDS = [
            "bank", "bni", "bca", "bri", "mandiri", "cimb", 
            "jne", "jnt", "sicepat", "anteraja", "shopeepay", 
            "logo", "icon", "qr", "code", "linkedin", "facebook", 
            "twitter", "google", "playstore", "appstore"
        ]

        # Cara A: Tag IMG
        try:
            images = driver.find_elements(By.TAG_NAME, "img")
            for img in images:
                src = img.get_attribute("src")
                if src and ("cf.shopee" in src or "susercontent" in src):
                    # Filter URL Sampah
                    src_lower = src.lower()
                    if any(bad_word in src_lower for bad_word in BLACKLIST_KEYWORDS):
                        continue
                    # Filter Thumbnail kecil
                    if "_tn" in src or "width=20" in src:
                        continue
                        
                    found_urls.add(src)
        except: pass

        # Cara B: Background Image (Biasanya ini gambar produk utama Shopee)
        try:
            divs = driver.find_elements(By.CSS_SELECTOR, "div[style*='background-image']")
            for div in divs:
                style = div.get_attribute("style")
                url_match = re.search(r'url\s*\(\s*["\']?(.*?)["\']?\s*\)', style)
                if url_match:
                    bg_url = url_match.group(1)
                    if "cf.shopee" in bg_url or "susercontent" in bg_url:
                        hd_url = bg_url.replace("_tn", "")
                        
                        # Filter URL Sampah
                        if any(bad_word in hd_url.lower() for bad_word in BLACKLIST_KEYWORDS):
                            continue
                            
                        found_urls.add(hd_url)
        except: pass

        # Filter Lanjutan: Cek Ukuran Gambar (Optional tapi bagus)
        # Kita hanya simpan URL, nanti saat render baru diproses
        
        valid_images = []
        for img_url in found_urls:
            # Filter ganda: URL harus panjang (bukan icon pendek) & tidak mengandung svg
            if len(img_url) > 25 and ".svg" not in img_url and "data:image" not in img_url:
                valid_images.append(img_url)

        data["images"] = list(set(valid_images))

    except Exception as e:
        error_message = f"Error: {str(e)}"
    finally:
        if driver: driver.quit()
            
    return data, error_message

# --- 2. FUNGSI AI WRITER ---
def generate_ai_script(api_key, title, num_slides):
    if not api_key: return None
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-flash-latest')
        prompt = f"""
        Buatkan naskah voice-over TikTok 'Indonesian local look' untuk produk: "{title}"
        
        Target: {num_slides} slide.
        Gaya: Santai, receh, ala review TikTok.
        Format: JSON array of strings.
        Slide terakhir wajib ajakan cek keranjang kuning.
        """
        response = model.generate_content(prompt)
        text_resp = response.text.strip()
        if "```json" in text_resp:
            text_resp = text_resp.split("```json")[1].split("```")[0].strip()
        return json.loads(text_resp)
    except:
        return None

# --- 3. FUNGSI SUARA ---
async def generate_voice_gadis(text, output_file):
    communicate = edge_tts.Communicate(text, "id-ID-GadisNeural", rate="+10%")
    await communicate.save(output_file)

def get_audio_gadis(text, index):
    filename = f"audio_{index}.mp3"
    try:
        asyncio.run(generate_voice_gadis(text, filename))
        return filename
    except:
        return None

# --- 4. TEXT OVERLAY ---
def add_text_to_image(cv2_img, text):
    img_pil = Image.fromarray(cv2.cvtColor(cv2_img, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(img_pil)
    w, h = img_pil.size
    
    fontsize = int(h * 0.03) 
    try:
        font = ImageFont.truetype("arialbd.ttf", fontsize)
    except:
        font = ImageFont.load_default()

    max_width = w * 0.85 
    words = text.split()
    lines, current_line = [], []
    for word in words:
        current_line.append(word)
        bbox = draw.textbbox((0, 0), " ".join(current_line), font=font)
        if (bbox[2] - bbox[0]) > max_width:
            current_line.pop()
            lines.append(" ".join(current_line))
            current_line = [word]
    lines.append(" ".join(current_line))
    final_text = "\n".join(lines)

    bbox_multiline = draw.multiline_textbbox((0, 0), final_text, font=font, align='center', spacing=10)
    text_w = bbox_multiline[2] - bbox_multiline[0]
    
    pos_x = (w - text_w) // 2
    pos_y = int(h * 0.55) 

    shadow_offset = 3
    draw.multiline_text((pos_x + shadow_offset, pos_y + shadow_offset), final_text, font=font, fill=(0,0,0, 160), align='center', spacing=10)
    
    draw.multiline_text(
        (pos_x, pos_y), 
        final_text, 
        font=font, 
        fill=(255, 255, 255), 
        stroke_width=4,       
        stroke_fill=(0, 0, 0), 
        align='center',
        spacing=10
    )
    
    return cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)

# --- 5. RENDER ENGINE ---
def create_single_clip(img_data, text_narration, index, is_upload=False):
    try:
        if is_upload:
            file_bytes = np.asarray(bytearray(img_data.read()), dtype=np.uint8)
            img_original = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
            img_data.seek(0)
        else:
            res = requests.get(img_data)
            img_original = cv2.imdecode(np.frombuffer(res.content, np.uint8), cv2.IMREAD_COLOR)
            
        th, tw = 1920, 1080
        h_orig, w_orig, _ = img_original.shape
        scale_bg = max(tw/w_orig, th/h_orig)
        bg_w, bg_h = int(w_orig * scale_bg), int(h_orig * scale_bg)
        img_bg_resized = cv2.resize(img_original, (bg_w, bg_h))
        
        x_bg = (bg_w - tw) // 2
        y_bg = (bg_h - th) // 2
        background_base = img_bg_resized[y_bg:y_bg+th, x_bg:x_bg+tw]
        
        background_base = cv2.GaussianBlur(background_base, (99, 99), 0)
        background_base = cv2.addWeighted(background_base, 0.6, np.zeros_like(background_base), 0.4, -20)
        
        audio_path = get_audio_gadis(re.sub(r'[^\w\s,.]', '', text_narration), index)
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        res_ff = subprocess.run([ffmpeg, '-i', audio_path, '-hide_banner'], stderr=subprocess.PIPE, text=True)
        
        dur = 3.0
        for line in res_ff.stderr.split('\n'):
            if "Duration" in line:
                t = line.split("Duration:")[1].split(",")[0].strip()
                h_m, m_m, s_m = t.split(':')
                dur = float(h_m)*3600 + float(m_m)*60 + float(s_m) + 0.5
                break
        
        fps = 30
        total_frames = int(dur * fps)
        tmp_v = f"tmp_{index}.mp4"
        out = cv2.VideoWriter(tmp_v, cv2.VideoWriter_fourcc(*'mp4v'), fps, (tw, th))
        
        target_product_w = int(tw * 0.85) 
        scale_prod = target_product_w / w_orig
        prod_w, prod_h = int(w_orig * scale_prod), int(h_orig * scale_prod)
        img_product_static = cv2.resize(img_original, (prod_w, prod_h))

        for i in range(total_frames):
            frame = background_base.copy()
            zoom_factor = 1.0 + (0.08 * (i / total_frames))
            curr_w = int(prod_w * zoom_factor)
            curr_h = int(prod_h * zoom_factor)
            img_zoomed = cv2.resize(img_product_static, (curr_w, curr_h))
            
            y_offset = (th - curr_h) // 2 - 50 
            x_offset = (tw - curr_w) // 2
            
            y1, y2 = max(0, y_offset), min(th, y_offset + curr_h)
            x1, x2 = max(0, x_offset), min(tw, x_offset + curr_w)
            sy1, sy2 = max(0, -y_offset), min(curr_h, th - y_offset)
            sx1, sx2 = max(0, -x_offset), min(curr_w, tw - x_offset)
            
            if y2 > y1 and x2 > x1:
                frame[y1:y2, x1:x2] = img_zoomed[sy1:sy2, sx1:sx2]
                cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 255, 255), 3)

            frame = add_text_to_image(frame, text_narration)
            out.write(frame)
            
        out.release()
        
        final_v = f"clip_{index}.mp4"
        subprocess.run([ffmpeg, '-y', '-i', tmp_v, '-i', audio_path, '-c:v', 'libx264', '-c:a', 'aac', '-shortest', final_v], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        if os.path.exists(tmp_v): os.remove(tmp_v)
        if os.path.exists(audio_path): os.remove(audio_path)
        
        return final_v
    except Exception as e:
        print(f"Error frame: {e}")
        return None

# --- UI MAIN ---
col1, col2 = st.columns([2, 1])
with col1:
    url = st.text_input("🔗 Link Shopee:", placeholder="Tempel link produk di sini...")
with col2:
    st.write("")
    st.write("")
    scrape_btn = st.button("🚀 PROSES PRODUK", type="primary", use_container_width=True)

if 'shopee_data' not in st.session_state: st.session_state.shopee_data = None
if 'generated_script' not in st.session_state: st.session_state.generated_script = None
if 'is_manual_upload' not in st.session_state: st.session_state.is_manual_upload = False

# --- LOGIKA SCRAPING ---
if scrape_btn:
    if url:
        st.session_state.is_manual_upload = False
        data, err = scrape_shopee_complete(url)
        if data and data['images']:
            st.session_state.shopee_data = data
            st.session_state.generated_script = None
            st.success(f"✅ Berhasil mengambil {len(data['images'])} gambar produk (Logo dibuang)!")
        else: 
            st.error(f"❌ Gagal mengambil gambar produk. Cobalah opsi Upload Manual di bawah.")
    else:
        st.warning("Masukkan link dulu.")

# --- FITUR UPLOAD MANUAL ---
st.markdown("---")
with st.expander("📂 Opsi Cadangan: Upload Gambar Manual", expanded=False):
    uploaded_files = st.file_uploader("Upload Gambar Produk", type=['jpg', 'png', 'jpeg'], accept_multiple_files=True)
    product_name_manual = st.text_input("Nama Produk:", value="Produk Keren")
    
    if uploaded_files:
        if st.button("Gunakan Gambar Upload"):
            st.session_state.shopee_data = {
                "title": product_name_manual,
                "images": uploaded_files, 
                "description": ""
            }
            st.session_state.is_manual_upload = True
            st.session_state.generated_script = None
            st.success("✅ Gambar manual dimuat!")

# --- EDITOR ---
if st.session_state.shopee_data:
    data = st.session_state.shopee_data
    images_list = data['images']
    limit = min(len(images_list), 6)
    
    if st.session_state.generated_script is None:
        if api_key:
            res_ai = generate_ai_script(api_key, data['title'], limit)
            st.session_state.generated_script = res_ai if res_ai else [data['title']] * limit
        else:
            st.session_state.generated_script = [f"Produk: {data['title']}"] * limit

    st.subheader(f"🎬 Video Editor: {data['title']}")
    
    cols = st.columns(3)
    inputs = []
    
    for i in range(limit):
        with cols[i%3]:
            img_source = images_list[i]
            # Handle display image based on type (URL string vs UploadedFile object)
            if isinstance(img_source, str):
                st.image(img_source, use_container_width=True)
            else:
                st.image(img_source, use_container_width=True)
            
            txt = st.text_area(f"Narasi {i+1}", value=st.session_state.generated_script[i] if i < len(st.session_state.generated_script) else "Cek sekarang!", key=f"v_{i}")
            inputs.append({"img_source": img_source, "text": txt})

    if st.button("✨ MULAI RENDER VIDEO", use_container_width=True):
        clips = []
        progress = st.progress(0)
        st_status = st.empty()
        
        for i, item in enumerate(inputs):
            st_status.text(f"Merender slide {i+1} dari {len(inputs)}...")
            c = create_single_clip(
                item['img_source'], 
                item['text'], 
                i, 
                is_upload=st.session_state.is_manual_upload
            )
            if c: clips.append(c)
            progress.progress((i+1)/len(inputs))
        
        if clips:
            st_status.text("Menggabungkan video...")
            with open("list.txt", "w") as f:
                for c in clips: f.write(f"file '{c}'\n")
            final_name = "shopee_video_final.mp4"
            subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-y', '-f', 'concat', '-safe', '0', '-i', 'list.txt', '-c', 'copy', final_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            st.video(final_name)
            st.download_button("Download Video 📥", open(final_name, "rb"), "video.mp4")
            
            for c in clips: 
                if os.path.exists(c): os.remove(c)
            if os.path.exists("list.txt"): os.remove("list.txt")
            st_status.text("Selesai!")
