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
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.os_manager import ChromeType # Wajib import ini

# --- KONFIGURASI HALAMAN ---
st.set_page_config(page_title="Shopee Video Creator", page_icon="🛍️", layout="wide")

# --- CSS CUSTOM ---
st.markdown("""
<style>
    .stTextArea textarea {font-size: 16px !important;}
    div[data-testid="stImage"] img {border-radius: 10px;}
</style>
""", unsafe_allow_html=True)

# --- SIDEBAR (Auto-Detect API Key) ---
with st.sidebar:
    st.header("⚙️ Pengaturan")
    
    # Cek apakah ada API Key di Secrets (Server)
    if "GEMINI_API_KEY" in st.secrets:
        api_key = st.secrets["GEMINI_API_KEY"]
        st.success("Status: API Key Terhubung ✅")
    else:
        # Jika tidak ada di secrets, minta input manual
        api_key = st.text_input("Gemini API Key", type="password", help="Masukkan API Key Gemini Anda")

    st.caption("Tanpa API Key, sistem akan menggunakan template manual dari Judul Produk.")
    st.markdown("---")
    st.info("Tips: Gunakan link produk Shopee yang gambarnya jelas.")

st.title("🛍️ Shopee Video Generator: Pro Style")
st.markdown("Ubah **Judul Produk** menjadi video promosi estetik (Blur Background & Zoom).")

# --- 1. FUNGSI SCRAPER (DIPERBAIKI UNTUK CHROMIUM 145) ---
def scrape_shopee_complete(url):
    chrome_options = Options()
    # Gunakan headless=new untuk kompatibilitas cloud terbaru
    chrome_options.add_argument("--headless=new") 
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    driver = None
    data = {"images": [], "title": "", "description": []}
    error_message = None

    try:
        # --- PERBAIKAN UTAMA DI SINI ---
        # Kita pakai ChromeType.CHROMIUM agar cocok dengan versi 145 di server
        service = Service(ChromeDriverManager(chrome_type=ChromeType.CHROMIUM).install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        st.toast("🕵️ Sedang membaca halaman produk...")
        driver.get(url)
        time.sleep(3) 
        
        page_source = driver.page_source

        # AMBIL JUDUL
        try:
            clean_url = url.split('?')[0]
            slug = clean_url.split('/')[-1]
            slug_clean = re.sub(r'\.i\.\d+\.\d+$', '', slug)
            final_title = slug_clean.replace('-', ' ')
            data["title"] = final_title if final_title else "Produk Shopee Tanpa Nama"
        except Exception as e:
            data["title"] = "Gagal mengambil judul dari URL"

        # AMBIL GAMBAR
        ids_found = []
        match = re.search(r'"images":\s*\[(.*?)\]', page_source)
        if match:
            content = match.group(1)
            ids_found = [x.strip('"').strip("'") for x in content.split(',')]
        
        if not ids_found:
            potential_ids = re.findall(r'[a-f0-9]{32}', page_source)
            ids_found = list(set(potential_ids))

        base_url = "https://down-id.img.susercontent.com/file/"
        for img_id in ids_found:
            if len(img_id) > 20 and " " not in img_id: 
                data["images"].append(f"{base_url}{img_id}")
        
        data["images"] = list(set(data["images"]))

    except Exception as e:
        error_message = f"Error Selenium: {str(e)}"
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

# --- 4. TEXT OVERLAY (FONT KECIL & POSISI NAIK) ---
def add_text_to_image(cv2_img, text):
    img_pil = Image.fromarray(cv2.cvtColor(cv2_img, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(img_pil)
    w, h = img_pil.size
    
    # --- PENGATURAN UKURAN FONT ---
    # 0.03 agar kecil tapi terbaca
    fontsize = int(h * 0.03) 
    
    try:
        font = ImageFont.truetype("arialbd.ttf", fontsize)
    except:
        font = ImageFont.load_default()

    # --- WORD WRAPPING ---
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

    # Hitung ukuran total teks
    bbox_multiline = draw.multiline_textbbox((0, 0), final_text, font=font, align='center', spacing=10)
    text_w = bbox_multiline[2] - bbox_multiline[0]
    
    # --- PENGATURAN POSISI TEKS ---
    # Posisi Horizontal: Center
    pos_x = (w - text_w) // 2
    
    # Posisi Vertikal: 55% dari atas (Sedikit di bawah tengah, tidak mepet bawah)
    pos_y = int(h * 0.55) 

    # --- EFEK TEXT ---
    shadow_offset = 3
    # Shadow
    draw.multiline_text((pos_x + shadow_offset, pos_y + shadow_offset), final_text, font=font, fill=(0,0,0, 160), align='center', spacing=10)
    
    # Text Utama (Putih Outline Hitam)
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

# --- 5. RENDER ENGINE (BLURRED BG + ZOOM) ---
def create_single_clip(img_url, text_narration, index):
    try:
        # Download Image
        res = requests.get(img_url)
        img_original = cv2.imdecode(np.frombuffer(res.content, np.uint8), cv2.IMREAD_COLOR)
        
        # Target Resolution
        th, tw = 1920, 1080
        
        # --- BACKGROUND BLUR ---
        h_orig, w_orig, _ = img_original.shape
        scale_bg = max(tw/w_orig, th/h_orig)
        bg_w, bg_h = int(w_orig * scale_bg), int(h_orig * scale_bg)
        img_bg_resized = cv2.resize(img_original, (bg_w, bg_h))
        
        x_bg = (bg_w - tw) // 2
        y_bg = (bg_h - th) // 2
        background_base = img_bg_resized[y_bg:y_bg+th, x_bg:x_bg+tw]
        
        # Blur & Darken
        background_base = cv2.GaussianBlur(background_base, (99, 99), 0)
        background_base = cv2.addWeighted(background_base, 0.6, np.zeros_like(background_base), 0.4, -20)
        
        # --- AUDIO ---
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
        
        # --- ZOOM LOGIC ---
        # Produk fit di tengah (85% lebar layar)
        target_product_w = int(tw * 0.85) 
        scale_prod = target_product_w / w_orig
        prod_w, prod_h = int(w_orig * scale_prod), int(h_orig * scale_prod)
        img_product_static = cv2.resize(img_original, (prod_w, prod_h))

        for i in range(total_frames):
            frame = background_base.copy()
            
            # Zoom Factor (1.0 -> 1.08)
            zoom_factor = 1.0 + (0.08 * (i / total_frames))
            
            curr_w = int(prod_w * zoom_factor)
            curr_h = int(prod_h * zoom_factor)
            img_zoomed = cv2.resize(img_product_static, (curr_w, curr_h))
            
            # Center Positioning
            y_offset = (th - curr_h) // 2 - 50 # Naikkan sedikit
            x_offset = (tw - curr_w) // 2
            
            # Overlay Logic
            y1, y2 = max(0, y_offset), min(th, y_offset + curr_h)
            x1, x2 = max(0, x_offset), min(tw, x_offset + curr_w)
            sy1, sy2 = max(0, -y_offset), min(curr_h, th - y_offset)
            sx1, sx2 = max(0, -x_offset), min(curr_w, tw - x_offset)
            
            if y2 > y1 and x2 > x1:
                frame[y1:y2, x1:x2] = img_zoomed[sy1:sy2, sx1:sx2]
                cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 255, 255), 3) # Border Putih

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
url = st.text_input("🔗 Link Shopee:", placeholder="Tempel link produk di sini...")

if 'shopee_data' not in st.session_state: st.session_state.shopee_data = None
if 'generated_script' not in st.session_state: st.session_state.generated_script = None

if st.button("🚀 PROSES PRODUK", type="primary"):
    if url:
        data, err = scrape_shopee_complete(url)
        if data and data['images']:
            st.session_state.shopee_data = data
            st.session_state.generated_script = None
            st.success("Data Berhasil Diambil!")
        else: st.error(f"Gagal: {err}")

# --- EDITOR ---
if st.session_state.shopee_data:
    data = st.session_state.shopee_data
    limit = min(len(data['images']), 6)
    
    if st.session_state.generated_script is None:
        if api_key:
            res_ai = generate_ai_script(api_key, data['title'], limit)
            st.session_state.generated_script = res_ai if res_ai else [data['title']] * limit
        else:
            st.session_state.generated_script = [f"Produk: {data['title']}"] * limit

    st.subheader(f"Video Editor: {data['title']}")
    
    cols = st.columns(3)
    inputs = []
    for i in range(limit):
        with cols[i%3]:
            st.image(data['images'][i], use_container_width=True)
            txt = st.text_area(f"Narasi {i+1}", value=st.session_state.generated_script[i] if i < len(st.session_state.generated_script) else "Cek sekarang!", key=f"v_{i}")
            inputs.append({"url": data['images'][i], "text": txt})

    if st.button("🎬 MULAI RENDER VIDEO", use_container_width=True):
        clips = []
        progress = st.progress(0)
        st_status = st.empty()
        
        for i, item in enumerate(inputs):
            st_status.text(f"Merender slide {i+1} dari {len(inputs)}...")
            c = create_single_clip(item['url'], item['text'], i)
            if c: clips.append(c)
            progress.progress((i+1)/len(inputs))
        
        if clips:
            st_status.text("Menggabungkan video...")
            with open("list.txt", "w") as f:
                for c in clips: f.write(f"file '{c}'\n")
            final_name = "shopee_video_final.mp4"
            subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-y', '-f', 'concat', '-safe', '0', '-i', 'list.txt', '-c', 'copy', final_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            st.video(final_name)
            st.download_button("Download Sekarang", open(final_name, "rb"), "video.mp4")
            
            # Cleanup
            for c in clips: 
                if os.path.exists(c): os.remove(c)
            if os.path.exists("list.txt"): os.remove("list.txt")
            st_status.text("Selesai!")
