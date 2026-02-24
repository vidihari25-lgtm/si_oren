import streamlit as st
import subprocess
import tempfile
import os
import random
import google.generativeai as genai
from PIL import Image

# --- KONFIGURASI HALAMAN ---
st.set_page_config(page_title="Ultimate Affiliate Video & AI Script", page_icon="🛍️", layout="wide")

# --- SESSION STATE (DAYA INGAT APLIKASI) ---
if 'reset_counter' not in st.session_state:
    st.session_state.reset_counter = 0
    st.session_state.ai_generated = False
    st.session_state.judul_ai = ""
    st.session_state.naskah_ai = ""
    st.session_state.hashtag_ai = ""

# --- CSS CUSTOM ---
st.markdown("""
<style>
    .stButton>button {
        background-color: #EE4D2D; 
        color: white;
        font-weight: bold;
        border-radius: 8px;
        transition: all 0.3s ease;
    }
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 8px rgba(0,0,0,0.15);
    }
    .ai-box {
        background-color: #f0f8ff;
        padding: 20px;
        border-radius: 10px;
        border-left: 5px solid #0088cc;
    }
</style>
""", unsafe_allow_html=True)

st.title("🛍️ Shopee Affiliate: AI Video & Script Generator")
st.markdown("Aplikasi pintar untuk afiliator: Buat naskah *voice over* otomatis dari foto (dan screenshot spesifikasi) dengan AI, lalu jadikan video katalog elegan berbingkai polaroid.")

# --- FUNGSI FFmpeg (TIDAK DIUBAH SAMA SEKALI) ---
def get_audio_duration(audio_path):
    try:
        cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', audio_path]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return float(result.stdout.strip())
    except Exception as e:
        st.error(f"Gagal membaca durasi audio. Error: {e}")
        return 0.0

def generate_framed_video(daftar_gambar, audio_path, nama_output):
    jumlah_gambar = len(daftar_gambar)
    audio_duration = get_audio_duration(audio_path)
    if audio_duration == 0: return False

    durasi_transisi = 1.0 
    total_waktu_transisi = (jumlah_gambar - 1) * durasi_transisi
    durasi_per_gambar = (audio_duration + total_waktu_transisi) / jumlah_gambar
    
    input_padding = 3.0 
    frames_per_gambar = int(durasi_per_gambar * 30)

    TRANSITIONS = ['fade', 'dissolve', 'slideup', 'slidedown', 'wiperight', 'wipeleft', 'circleopen', 'radial']

    cmd = ['ffmpeg', '-y']
    for gambar in daftar_gambar:
        cmd.extend(['-loop', '1', '-t', str(durasi_per_gambar + input_padding), '-i', gambar])
            
    cmd.extend(['-i', audio_path])

    filter_complex = ""
    for i in range(jumlah_gambar):
        filter_complex += f"[{i}:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=150:150[bg{i}]; "
        filter_complex += f"[{i}:v]scale=850:1800:force_original_aspect_ratio=decrease[fg_raw{i}]; "
        filter_complex += f"[fg_raw{i}]pad=iw+80:ih+80:40:40:white[framed_fg{i}]; "
        filter_complex += f"[bg{i}][framed_fg{i}]overlay=(main_w-overlay_w)/2:(main_h-overlay_h)/2[comp{i}]; "
        filter_complex += f"[comp{i}]zoompan=z='min(zoom+0.0002,1.06)':d={frames_per_gambar+90}:s=1080x1920:fps=30[scene{i}]; "

    if jumlah_gambar == 1:
        filter_complex += "[scene0]copy[outv]"
    else:
        node_sebelumnya = "[scene0]"
        waktu_offset = durasi_per_gambar - durasi_transisi 
        for i in range(1, jumlah_gambar):
            node_sekarang = f"[scene{i}]"
            node_output = f"[fade{i}]" if i < jumlah_gambar - 1 else "[outv]"
            transisi_terpilih = random.choice(TRANSITIONS)
            filter_complex += f"{node_sebelumnya}{node_sekarang}xfade=transition={transisi_terpilih}:duration={durasi_transisi}:offset={waktu_offset}{node_output}; "
            node_sebelumnya = node_output
            waktu_offset += (durasi_per_gambar - durasi_transisi) 
            
    filter_complex = filter_complex.strip("; ")
    audio_index = len(daftar_gambar)
    cmd.extend(['-filter_complex', filter_complex, '-map', '[outv]', '-map', f'{audio_index}:a'])
    cmd.extend(['-c:v', 'libx264', '-preset', 'fast', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k', '-r', '30', '-shortest', nama_output])
    
    try:
        subprocess.run(cmd, check=True, stderr=subprocess.PIPE) 
        return True
    except subprocess.CalledProcessError as e:
        error_message = e.stderr.decode('utf-8') if e.stderr else str(e)
        st.error(f"Terjadi kesalahan FFmpeg:\n{error_message}")
        return False

# ================= UI STREAMLIT =================

col_kiri, col_kanan = st.columns([1, 1], gap="large")

with col_kiri:
    st.header("📸 1. Input Material Video")
    uploaded_images = st.file_uploader(
        "Upload Foto Produk (Minimal 2 untuk video)", 
        type=['png', 'jpg', 'jpeg'], 
        accept_multiple_files=True,
        key=f"img_uploader_{st.session_state.reset_counter}"
    )
    
    st.markdown("---")
    st.header("🎵 3. Upload Voice/Musik")
    st.info("Setelah men-generate script di samping dan mengubahnya jadi suara, upload file audionya ke sini.")
    uploaded_audio = st.file_uploader(
        "Upload Audio (MP3/WAV)", 
        type=['mp3', 'wav', 'm4a', 'aac'],
        key=f"aud_uploader_{st.session_state.reset_counter}"
    )

with col_kanan:
    st.header("🤖 2. AI Copywriter & SEO")
    st.markdown('<div class="ai-box">', unsafe_allow_html=True)
    
    try:
        gemini_key = st.secrets["GEMINI_API_KEY"]
        st.success("✅ API Key Sistem berhasil dimuat secara aman.")
    except Exception:
        gemini_key = ""
        st.error("⚠️ API Key tidak ditemukan di Streamlit Secrets. Aplikasi tidak bisa men-generate script.")

    # FITUR BARU: Uploader Screenshot (Maks 2)
    st.markdown("**Bahan Bacaan AI (Opsional):**")
    uploaded_captures = st.file_uploader(
        "📄 Upload Screenshot Spesifikasi/Teks (Maks 2):", 
        type=['png', 'jpg', 'jpeg'], 
        accept_multiple_files=True,
        key=f"cap_uploader_{st.session_state.reset_counter}",
        help="AI akan membaca teks di dalam gambar ini (nama bahan, harga, fitur) jadi Anda tidak perlu mengetik manual."
    )
    
    keterangan_produk = st.text_area(
        "📝 Keterangan Ketik Manual (Opsional):", 
        placeholder="Atau ketik info tambahan di sini jika tidak ada screenshot...",
        height=80,
        key=f"ket_{st.session_state.reset_counter}"
    )
    
    if st.button("✨ Generate Script & SEO Shopee", use_container_width=True):
        if not gemini_key:
            st.warning("⚠️ API Key belum disetting di Streamlit Cloud.")
        elif not uploaded_images:
            st.warning("⚠️ Mohon upload foto produk di Langkah 1 agar AI bisa melihat produknya.")
        else:
            with st.spinner("AI sedang membaca gambar, meracik Judul SEO, Naskah, dan Hashtag..."):
                try:
                    genai.configure(api_key=gemini_key)
                    model = genai.GenerativeModel('gemini-2.0-flash')
                    
                    # Siapkan list konten untuk dikirim ke AI
                    ai_payload = []
                    
                    # Prompt Instruksi
                    prompt_text = f"""
                    Kamu adalah pakar SEO Shopee Video dan Copywriter Affiliate handal.
                    Tugasmu membuat Judul, Naskah Voice Over, dan Hashtag.
                    
                    Bahan referensi:
                    1. Gambar pertama yang dilampirkan adalah wujud produknya.
                    2. Jika ada gambar kedua atau ketiga, itu adalah screenshot spesifikasi produk. BACA SEMUA TEKS di dalamnya secara teliti sebagai fitur/keunggulan produk.
                    3. Catatan manual dari user: "{keterangan_produk}" (jika kosong, abaikan).
                    
                    Aturan Naskah:
                    - Judul: Singkat, sangat SEO friendly, clickbait.
                    - Naskah VO: Bahasa gaul, persuasif, durasi baca 15-20 detik. Ada Hook, sebut fitur unggulan (dari screenshot/catatan), dan akhiri dengan Call to Action "klik keranjang kuning".
                    - Hashtag: 5 hashtag paling relevan.
                    
                    PENTING: Jawab persis dengan format ini:
                    JUDUL:
                    [Isi Judul]
                    ---
                    NASKAH:
                    [Isi Naskah]
                    ---
                    HASHTAG:
                    [Isi Hashtag]
                    """
                    ai_payload.append(prompt_text)
                    
                    # Masukkan Foto Produk (Ambil 1 saja sebagai rupa visual)
                    img_to_analyze = Image.open(uploaded_images[0])
                    ai_payload.append(img_to_analyze)
                    
                    # Masukkan Gambar Screenshot (Maksimal 2 untuk hemat token)
                    if uploaded_captures:
                        for cap_file in uploaded_captures[:2]:
                            cap_img = Image.open(cap_file)
                            ai_payload.append(cap_img)
                    
                    # Generate Respon
                    response = model.generate_content(ai_payload)
                    hasil = response.text
                    
                    judul_ai, naskah_ai, hashtag_ai = "", hasil, ""
                    if "---" in hasil:
                        parts = hasil.split("---")
                        if len(parts) >= 3:
                            judul_ai = parts[0].replace("JUDUL:", "").strip()
                            naskah_ai = parts[1].replace("NASKAH:", "").strip()
                            hashtag_ai = parts[2].replace("HASHTAG:", "").strip()
                    
                    st.session_state.judul_ai = judul_ai
                    st.session_state.naskah_ai = naskah_ai
                    st.session_state.hashtag_ai = hashtag_ai
                    st.session_state.ai_generated = True
                    
                    st.success("✅ SEO, Script, & Hashtag berhasil diracik!")
                    
                except Exception as e:
                    st.error(f"Gagal menghubungi Gemini AI. Error: {e}")
    
    if st.session_state.ai_generated:
        if st.session_state.judul_ai:
            st.write("📌 **Judul Video (SEO Friendly):**")
            st.code(st.session_state.judul_ai, language="text")
            
        st.write("📝 **Naskah Voice Over:**")
        st.code(st.session_state.naskah_ai, language="text")
        
        if st.session_state.hashtag_ai:
            st.write("🏷️ **5 Hashtag Shopee Video:**")
            st.code(st.session_state.hashtag_ai, language="text")
            
    st.markdown('</div>', unsafe_allow_html=True)

# --- TOMBOL RENDER FINAL ---
st.markdown("---")
if uploaded_images and uploaded_audio:
    st.success("✅ Foto dan Audio siap dirakit menjadi video!")
    
    _, col_btn, _ = st.columns([1, 2, 1])
    with col_btn:
         if st.button("🚀 RENDER VIDEO ELEGAN SEKARANG 🚀", use_container_width=True):
            with st.spinner('Sedang merender bingkai dan animasi... (Tunggu hingga selesai)'):
                with tempfile.TemporaryDirectory() as temp_dir:
                    image_paths = []
                    for i, img_file in enumerate(uploaded_images):
                        ext = os.path.splitext(img_file.name)[1]
                        temp_path = os.path.join(temp_dir, f"img_{i}{ext}")
                        
                        img_file.seek(0) 
                        with open(temp_path, "wb") as f:
                            f.write(img_file.getbuffer())
                        image_paths.append(temp_path)
                    
                    aud_ext = os.path.splitext(uploaded_audio.name)[1]
                    audio_path = os.path.join(temp_dir, f"audio_source{aud_ext}")
                    with open(audio_path, "wb") as f:
                        f.write(uploaded_audio.getbuffer())
                        
                    output_path = os.path.join(temp_dir, "video_affiliate_elegan.mp4")
                    
                    sukses = generate_framed_video(image_paths, audio_path, output_path)
                    
                    if sukses:
                        st.balloons()
                        st.success("🎉 Video Katalog Elegan Selesai!")
                        with open(output_path, 'rb') as video_file:
                            video_bytes = video_file.read()
                            st.video(video_bytes, format="video/mp4")
                            st.download_button("⬇️ Download Video (Siap Upload)", data=video_bytes, file_name="affiliate_promo.mp4", mime="video/mp4", use_container_width=True)

# --- TOMBOL RESET / HAPUS DATA ---
st.markdown("---")
st.markdown("<br>", unsafe_allow_html=True)
_, col_reset, _ = st.columns([1, 2, 1])

with col_reset:
    st.markdown("""
        <style>
        div[data-testid="stButton"] button[kind="secondary"] {
            background-color: #4f4f4f;
            color: white;
            border: none;
        }
        div[data-testid="stButton"] button[kind="secondary"]:hover {
            background-color: #cc0000;
        }
        </style>
    """, unsafe_allow_html=True)
    
    if st.button("🗑️ HAPUS DATA & BUAT PRODUK BARU", type="secondary", use_container_width=True):
        st.session_state.reset_counter += 1
        st.session_state.ai_generated = False
        st.session_state.judul_ai = ""
        st.session_state.naskah_ai = ""
        st.session_state.hashtag_ai = ""
        st.rerun()
