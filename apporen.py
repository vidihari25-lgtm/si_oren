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
st.markdown("Aplikasi pintar untuk afiliator: Buat naskah *voice over* otomatis dari foto/screenshot dengan AI, lalu jadikan video katalog elegan berbingkai polaroid.")

# --- FUNGSI FFmpeg (VAKSIN ANTI-SPASI SEJATI) ---
def get_audio_duration(temp_dir, audio_filename):
    try:
        # PERINTAH KUNCI: cwd=temp_dir (memaksa mesin mengeksekusi di dalam folder, menghindari spasi path Windows)
        cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', audio_filename]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True, cwd=temp_dir)
        return float(result.stdout.strip())
    except Exception as e:
        st.error(f"Gagal membaca durasi audio. Error: {e}")
        return 0.0

def generate_framed_video(temp_dir, media_filenames, audio_filename, output_filename):
    jumlah_media = len(media_filenames)
    audio_duration = get_audio_duration(temp_dir, audio_filename)
    
    if audio_duration == 0: 
        st.error("Gagal memproses audio. Proses render dibatalkan.")
        return False

    durasi_transisi = 1.0 
    total_waktu_transisi = (jumlah_media - 1) * durasi_transisi
    durasi_per_media = (audio_duration + total_waktu_transisi) / jumlah_media
    
    input_padding = 3.0 
    frames_per_media = int(durasi_per_media * 30)

    TRANSITIONS = ['fade', 'dissolve', 'slideup', 'slidedown', 'wiperight', 'wipeleft', 'circleopen', 'radial']

    cmd = ['ffmpeg', '-y']
    
    # Memasukkan input media (Hanya menggunakan nama file pendek, bukan full path)
    for media in media_filenames:
        ext = os.path.splitext(media)[1].lower()
        if ext in ['.mp4', '.mov', '.avi']:
            cmd.extend(['-stream_loop', '-1', '-t', str(durasi_per_media + input_padding), '-i', media])
        else:
            cmd.extend(['-loop', '1', '-t', str(durasi_per_media + input_padding), '-i', media])
            
    cmd.extend(['-i', audio_filename])

    filter_complex = ""
    for i in range(jumlah_media):
        ext = os.path.splitext(media_filenames[i])[1].lower()
        is_video = ext in ['.mp4', '.mov', '.avi']

        filter_complex += f"[{i}:v]split=2[in_bg{i}][in_fg{i}]; "
        filter_complex += f"[in_bg{i}]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,scale=270:480,boxblur=15:15,scale=1080:1920[bg{i}]; "
        filter_complex += f"[in_fg{i}]scale=850:1800:force_original_aspect_ratio=decrease[fg_raw{i}]; "
        filter_complex += f"[fg_raw{i}]pad=iw+80:ih+80:40:40:white[framed_fg{i}]; "
        filter_complex += f"[bg{i}][framed_fg{i}]overlay=(main_w-overlay_w)/2:(main_h-overlay_h)/2[comp{i}]; "
        
        if is_video:
            filter_complex += f"[comp{i}]fps=30,scale=1080:1920[scene{i}]; "
        else:
            filter_complex += f"[comp{i}]zoompan=z='min(zoom+0.0002,1.06)':d={frames_per_media+90}:s=1080x1920:fps=30[scene{i}]; "

    if jumlah_media == 1:
        filter_complex += "[scene0]copy[outv]"
    else:
        node_sebelumnya = "[scene0]"
        waktu_offset = durasi_per_media - durasi_transisi 
        for i in range(1, jumlah_media):
            node_sekarang = f"[scene{i}]"
            node_output = f"[fade{i}]" if i < jumlah_media - 1 else "[outv]"
            transisi_terpilih = random.choice(TRANSITIONS)
            filter_complex += f"{node_sebelumnya}{node_sekarang}xfade=transition={transisi_terpilih}:duration={durasi_transisi}:offset={waktu_offset}{node_output}; "
            node_sebelumnya = node_output
            waktu_offset += (durasi_per_media - durasi_transisi) 
            
    filter_complex = filter_complex.strip("; ")
    audio_index = len(media_filenames)
    cmd.extend(['-filter_complex', filter_complex, '-map', '[outv]', '-map', f'{audio_index}:a'])
    
    cmd.extend(['-c:v', 'libx264', '-preset', 'superfast', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k', '-r', '30', '-shortest', output_filename])
    
    try:
        # PERINTAH KUNCI: cwd=temp_dir. FFmpeg dieksekusi terkurung di dalam folder.
        subprocess.run(cmd, check=True, stderr=subprocess.PIPE, cwd=temp_dir) 
        return True
    except subprocess.CalledProcessError as e:
        error_message = e.stderr.decode('utf-8') if e.stderr else str(e)
        st.error(f"Terjadi kesalahan FFmpeg:\n{error_message}")
        return False

# ================= UI STREAMLIT =================

col_kiri, col_kanan = st.columns([1, 1], gap="large")

with col_kiri:
    st.header("📸 1. Input Material Video")
    uploaded_media = st.file_uploader(
        "Upload Foto / Video Produk (Minimal 2 file)", 
        type=['png', 'jpg', 'jpeg', 'mp4', 'mov', 'avi'], 
        accept_multiple_files=True,
        key=f"img_uploader_{st.session_state.reset_counter}"
    )
    
    st.markdown("---")
    st.header("🎵 3. Upload Voice/Musik")
    st.info("Setelah men-generate script di samping dan mengubahnya jadi suara, upload file audionya ke sini.")
    uploaded_audio = st.file_uploader(
        "Upload Audio (MP3/WAV)", 
        type=['mp3', 'wav', 'WAV', 'm4a', 'aac', 'ogg'],
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
        elif not uploaded_media and not uploaded_captures:
            st.warning("⚠️ Mohon upload setidaknya 1 foto produk atau screenshot spesifikasi agar AI ada bahan bacaan.")
        else:
            with st.spinner("AI sedang membaca gambar, meracik Judul SEO, Naskah, dan Hashtag..."):
                try:
                    genai.configure(api_key=gemini_key)
                    model = genai.GenerativeModel('gemini-2.0-flash')
                    
                    ai_payload = []
                    
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
                    
                    img_to_analyze = None
                    if uploaded_media:
                        for media_file in uploaded_media:
                            ext = os.path.splitext(media_file.name)[1].lower()
                            if ext in ['.png', '.jpg', '.jpeg']:
                                img_to_analyze = Image.open(media_file)
                                break 
                    
                    if img_to_analyze:
                        ai_payload.append(img_to_analyze)
                    
                    if uploaded_captures:
                        for cap_file in uploaded_captures[:2]:
                            cap_img = Image.open(cap_file)
                            ai_payload.append(cap_img)
                    
                    if len(ai_payload) > 1 or keterangan_produk.strip() != "":
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
                    else:
                        st.error("Silakan masukkan minimal 1 foto/screenshot atau ketik keterangan manual agar AI bisa bekerja.")
                        
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
if uploaded_media and uploaded_audio:
    st.success("✅ File lengkap! Siap dirakit menjadi video.")
    
    _, col_btn, _ = st.columns([1, 2, 1])
    with col_btn:
         if st.button("🚀 RENDER VIDEO ELEGAN SEKARANG 🚀", use_container_width=True):
            with st.spinner('Sedang merender bingkai dan animasi... (Tunggu hingga selesai)'):
                with tempfile.TemporaryDirectory() as temp_dir:
                    media_filenames = []
                    for i, media_file in enumerate(uploaded_media):
                        # Ekstrak nama asli, buang karakter aneh/spasi
                        ext = os.path.splitext(media_file.name)[1].lower()
                        safe_ext = "".join(c for c in ext if c.isalnum() or c == '.')
                        
                        media_filename = f"media_{i}{safe_ext}"
                        temp_path = os.path.join(temp_dir, media_filename)
                        
                        media_file.seek(0) 
                        with open(temp_path, "wb") as f:
                            f.write(media_file.getbuffer())
                        media_filenames.append(media_filename)
                    
                    aud_ext = os.path.splitext(uploaded_audio.name)[1].lower()
                    safe_aud_ext = "".join(c for c in aud_ext if c.isalnum() or c == '.')
                    if not safe_aud_ext:
                        safe_aud_ext = ".wav" 
                        
                    audio_filename = f"audio_source{safe_aud_ext}"
                    audio_path = os.path.join(temp_dir, audio_filename)
                    with open(audio_path, "wb") as f:
                        f.write(uploaded_audio.getbuffer())
                        
                    output_filename = "video_affiliate_elegan.mp4"
                    output_path = os.path.join(temp_dir, output_filename)
                    
                    sukses = generate_framed_video(temp_dir, media_filenames, audio_filename, output_filename)
                    
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
