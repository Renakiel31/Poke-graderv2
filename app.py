import streamlit as st
import cv2
import numpy as np
from fpdf import FPDF
import os
from datetime import datetime
import requests

# --- CONFIGURATION ---
st.set_page_config(page_title="Poké-Station V10", page_icon="⚡", layout="wide")

# --- DICTIONNAIRE DE TRADUCTION (FR -> EN) ---
POKEMON_NAMES = {
    "tortank": "Blastoise", "dracaufeu": "Charizard", "florizarre": "Venusaur",
    "reptincel": "Charmeleon", "salameche": "Charmander", "carapuce": "Squirtle",
    "carabaffe": "Wartortle", "bulbizarre": "Bulbasaur", "herbizarre": "Ivysaur",
    "evoli": "Eevee", "noctali": "Umbreon", "mentali": "Espeon",
    "aquali": "Vaporeon", "voltali": "Jolteon", "pyroli": "Flareon",
    "mewtwo": "Mewtwo", "mew": "Mew", "pikachu": "Pikachu",
    "rayquaza": "Rayquaza", "lugia": "Lugia", "dracolosse": "Dragonite",
    "leviator": "Gyarados", "ectoplasma": "Gengar"
}

def check_password():
    """Gère l'accès par mot de passe."""
    if st.session_state.get('password_correct', False):
        return True

    st.markdown("### 🔒 Accès Restreint")
    password_input = st.text_input("Entrez le code d'accès", type="password")

    if password_input:
        try:
            # Tente de récupérer le secret, sinon utilise le code de secours "1234"
            secret_code = st.secrets["access_code"]
            if password_input == secret_code:
                st.session_state['password_correct'] = True
                st.rerun()
            else:
                st.error("❌ Mauvais code")
        except (FileNotFoundError, KeyError):
            if password_input == "1234":
                st.session_state['password_correct'] = True
                st.rerun()
            else:
                st.error("❌ Mauvais code (Mode Secours : essayez 1234)")
            
    return False

if not check_password():
    st.stop()

# --- FONCTIONS API & UTILITAIRES ---

def get_card_price(card_name):
    """Cherche la carte sur l'API et renvoie les infos et le prix."""
    clean_name = card_name.lower().strip()
    search_term = POKEMON_NAMES.get(clean_name, card_name)
    
    try:
        url = f"https://api.pokemontcg.io/v2/cards?q=name:\"{search_term}*\"&pageSize=5"
        response = requests.get(url, timeout=8) 
        data = response.json()
        
        if 'data' in data and data['data']:
            return data['data']
        return None
    except Exception as e:
        st.error(f"Erreur connexion API: {e}")
        return None

def process_image(image_file):
    # Lit le fichier image (buffer) et le convertit pour OpenCV
    file_bytes = np.asarray(bytearray(image_file.read()), dtype=np.uint8)
    return cv2.imdecode(file_bytes, 1)

def draw_alignment_lines(img, l_out, l_in, r_in, r_out, t_out, t_in, b_in, b_out):
    img_lines = img.copy()
    h, w = img.shape[:2]
    YELLOW = (0, 255, 255)
    GREEN = (0, 255, 0)
    THICKNESS = 4 if w > 1000 else 2 
    
    cv2.line(img_lines, (l_out, 0), (l_out, h), YELLOW, THICKNESS)
    cv2.line(img_lines, (l_in, 0), (l_in, h), GREEN, THICKNESS)
    cv2.line(img_lines, (r_in, 0), (r_in, h), GREEN, THICKNESS)
    cv2.line(img_lines, (r_out, 0), (r_out, h), YELLOW, THICKNESS)
    cv2.line(img_lines, (0, t_out), (w, t_out), YELLOW, THICKNESS)
    cv2.line(img_lines, (0, t_in), (w, t_in), GREEN, THICKNESS)
    cv2.line(img_lines, (0, b_in), (w, b_in), GREEN, THICKNESS)
    cv2.line(img_lines, (0, b_out), (w, b_out), YELLOW, THICKNESS)
    return img_lines

# --- CORRECTIF ENCODAGE PDF ---
def clean_text(text):
    """Nettoie le texte pour éviter le crash UnicodeEncodeError du PDF"""
    # Force la conversion en string pour éviter les problèmes de type
    text = str(text)
    # Le symbole Euro fait planter FPDF standard -> on le remplace
    text = text.replace("€", "EUR")
    # On force l'encodage latin-1 en remplaçant les caractères inconnus par ?
    return text.encode('latin-1', 'replace').decode('latin-1')

def create_pdf(image_array, card_name, g_px, d_px, h_px, b_px, rh, rv, final_price, api_card_data=None):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    
    # On nettoie tous les textes affichés
    title = clean_text(f"Rapport : {card_name}")
    pdf.cell(0, 10, txt=title, ln=1, align='C')
    
    pdf.set_font("Arial", 'I', 10)
    if api_card_data:
        set_name = api_card_data.get('set', {}).get('name', 'Inconnu')
        rarity = api_card_data.get('rarity', 'Inconnue')
        
        info_txt = clean_text(f"Serie: {set_name} | Rarete: {rarity}")
        pdf.cell(0, 8, txt=info_txt, ln=1, align='C')
        
    price_txt = clean_text(f"Date: {datetime.now().strftime('%d/%m/%Y')} | Valeur: {final_price}")
    pdf.cell(0, 8, txt=price_txt, ln=1, align='C')
    
    temp_card = "temp_card_mobile.jpg"
    cv2.imwrite(temp_card, image_array)
    pdf.image(temp_card, x=60, y=45, w=90)
    
    pdf.set_y(170)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, clean_text("Details du Centrage"), ln=1)
    pdf.set_font("Arial", '', 11)
    
    grade_h = "GEM MINT (10)" if 45 <= rh <= 55 else "MINT (9)" if 40 <= rh <= 60 else "OC"
    grade_v = "GEM MINT (10)" if 45 <= rv <= 55 else "MINT (9)" if 40 <= rv <= 60 else "OC"
    
    line1 = clean_text(f"Horiz.: {g_px}/{d_px} ({rh:.1f}%) -> {grade_h}")
    line2 = clean_text(f"Vert.: {h_px}/{b_px} ({rv:.1f}%) -> {grade_v}")
    
    pdf.cell(95, 8, line1, border=1)
    pdf.cell(95, 8, line2, border=1, ln=1)
    
    if os.path.exists(temp_card): os.remove(temp_card)
    # AJOUT CRITIQUE : on utilise 'replace' ici aussi pour empêcher le crash final
    return pdf.output(dest='S').encode('latin-1', 'replace')

# --- INTERFACE ---
st.title("⚡ Poké-Station V10")

if 'selected_api_card' not in st.session_state:
    st.session_state['selected_api_card'] = None

# --- 1. RECHERCHE ---
with st.expander("🔎 1. Recherche & Prix", expanded=True):
    col_search, col_btn = st.columns([3, 1])
    with col_search:
        search_query = st.text_input("Nom du Pokémon", placeholder="Dracaufeu...")
    with col_btn:
        st.write("") 
        st.write("") 
        if st.button("Go"):
            results = get_card_price(search_query)
            if results:
                st.session_state['api_results'] = results
            else:
                st.warning("Rien trouvé. Essayez en anglais.")

    if 'api_results' in st.session_state and st.session_state['api_results']:
        st.write("### Résultats :")
        cols = st.columns(2)
        for i, card in enumerate(st.session_state['api_results'][:4]):
            col_idx = i % 2
            with cols[col_idx]:
                st.image(card['images']['small'], use_container_width=True)
                price = "N/A"
                if 'cardmarket' in card and 'prices' in card['cardmarket']:
                    price = f"{card['cardmarket']['prices']['averageSellPrice']} €"
                
                if st.button(f"Choisir ({price})", key=f"sel_{card['id']}"):
                    st.session_state['selected_api_card'] = card
                    st.success(f"OK: {card['name']}")

final_price_str = "Non défini"
selected_card_data = None

if st.session_state['selected_api_card']:
    selected_card_data = st.session_state['selected_api_card']
    if 'cardmarket' in selected_card_data:
        final_price_str = f"{selected_card_data['cardmarket']['prices']['averageSellPrice']} €"
    st.info(f"📍 Carte : **{selected_card_data['name']}** | Prix : **{final_price_str}**")

# --- 2. MANUEL ---
with st.expander("🧮 2. Prix Manuel", expanded=False):
    man_price = st.number_input("Prix (€)", 0.0)
    if man_price > 0:
        final_price_str = f"{man_price} € (Manuel)"

# --- 3. PHOTO (MODIFIÉ POUR CAMERA) ---
st.markdown("### 📸 3. Gradation")

# Onglets pour choisir entre Caméra et Importation
tab_cam, tab_upload = st.tabs(["📸 Caméra Directe", "📂 Importer Fichier"])

img_input = None

with tab_cam:
    # C'est ce composant qui active la caméra sur mobile
    cam_pic = st.camera_input("Prendre une photo")
    if cam_pic:
        img_input = cam_pic

with tab_upload:
    up_pic = st.file_uploader("Choisir une image", type=['jpg', 'png', 'jpeg'])
    if up_pic:
        img_input = up_pic

if img_input:
    # Traitement commun quelle que soit la source (Caméra ou Fichier)
    raw = process_image(img_input)
    h_o, w_o = raw.shape[:2]
    
    st.write("**A. Découpage (Crop)**")
    c_cut1, c_cut2 = st.columns(2)
    with c_cut1:
        ct = st.slider("Haut", 0, h_o, 0)
        cb = st.slider("Bas", 0, h_o, h_o)
    with c_cut2:
        cl = st.slider("Gauche", 0, w_o, 0)
        cr = st.slider("Droite", 0, w_o, w_o)
        
    if ct>=cb: cb=ct+10
    if cl>=cr: cr=cl+10
    cropped = raw[ct:cb, cl:cr]
    st.image(cv2.cvtColor(cropped, cv2.COLOR_BGR2RGB), use_container_width=True)
    
    st.write("---")
    st.write("**B. Centrage**")
    h_c, w_c = cropped.shape[:2]
    
    sc1, sc2 = st.columns(2)
    with sc1:
        st.caption("Horizontal")
        lo = st.slider("J-Gau", 0, w_c, int(w_c*0.02), key="lo")
        li = st.slider("V-Gau", 0, w_c, int(w_c*0.08), key="li")
        ri = st.slider("V-Dro", 0, w_c, int(w_c*0.92), key="ri")
        ro = st.slider("J-Dro", 0, w_c, int(w_c*0.98), key="ro")
    with sc2:
        st.caption("Vertical")
        to = st.slider("J-Haut", 0, h_c, int(h_c*0.02), key="to")
        ti = st.slider("V-Haut", 0, h_c, int(h_c*0.08), key="ti")
        bi = st.slider("V-Bas", 0, h_c, int(h_c*0.92), key="bi")
        bo = st.slider("J-Bas", 0, h_c, int(h_c*0.98), key="bo")
        
    final = draw_alignment_lines(cropped, lo, li, ri, ro, to, ti, bi, bo)
    st.image(cv2.cvtColor(final, cv2.COLOR_BGR2RGB), use_container_width=True)
    
    bl, br = abs(li-lo), abs(ro-ri)
    bt, bb = abs(ti-to), abs(bo-bi)
    th, tv = bl+br, bt+bb
    
    if th>0 and tv>0:
        rh, rv = (bl/th)*100, (bt/tv)*100
        
        k1, k2 = st.columns(2)
        k1.info(f"H: {rh:.1f}%")
        k2.info(f"V: {rv:.1f}%")
        
        card_label = selected_card_data['name'] if selected_card_data else "Carte"
        
        pdf_data = create_pdf(final, card_label, bl, br, bt, bb, rh, rv, final_price_str, selected_card_data)
        st.download_button("📥 PDF", pdf_data, f"Rapport.pdf", "application/pdf")

