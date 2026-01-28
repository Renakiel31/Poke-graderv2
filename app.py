import streamlit as st
import cv2
import numpy as np
from fpdf import FPDF
import os
from datetime import datetime
import requests
import re

# --- CONFIGURATION ---
st.set_page_config(page_title="Poké-Station V15", page_icon="⚡", layout="wide")

# 🔒 CONFIGURATION MOT DE PASSE DE SECOURS
# Modifiez "admin" ci-dessous par le mot de passe que vous souhaitez
MOT_DE_PASSE_SECOURS = "admin"

# --- DICTIONNAIRE DE TRADUCTION (FR -> EN) ---
POKEMON_NAMES = {
    "tortank": "Blastoise", "dracaufeu": "Charizard", "florizarre": "Venusaur",
    "reptincel": "Charmeleon", "salameche": "Charmander", "carapuce": "Squirtle",
    "carabaffe": "Wartortle", "bulbizarre": "Bulbasaur", "herbizarre": "Ivysaur",
    "evoli": "Eevee", "noctali": "Umbreon", "mentali": "Espeon",
    "aquali": "Vaporeon", "voltali": "Jolteon", "pyroli": "Flareon",
    "mewtwo": "Mewtwo", "mew": "Mew", "pikachu": "Pikachu",
    "rayquaza": "Rayquaza", "lugia": "Lugia", "dracolosse": "Dragonite",
    "leviator": "Gyarados", "ectoplasma": "Gengar",
    "radieux": "Radiant", "brillant": "Shining", "lumineux": "Light", "obscur": "Dark",
    "star": "Star", "vmax": "VMAX", "vstar": "VSTAR", "ex": "ex"
}

def check_password():
    """Gère l'accès par mot de passe."""
    if st.session_state.get('password_correct', False):
        return True

    st.markdown("### 🔒 Accès Restreint")
    password_input = st.text_input("Entrez le code d'accès", type="password")

    if password_input:
        try:
            # Priorité au fichier secrets.toml s'il existe
            secret_code = st.secrets["access_code"]
            if password_input == secret_code:
                st.session_state['password_correct'] = True
                st.rerun()
            else:
                st.error("❌ Code incorrect")
        except (FileNotFoundError, KeyError):
            # Sinon utilisation du mot de passe de secours défini en haut du fichier
            if password_input == MOT_DE_PASSE_SECOURS: 
                st.session_state['password_correct'] = True
                st.rerun()
            else:
                st.error("❌ Code incorrect") # Message générique pour sécurité
            
    return False

if not check_password():
    st.stop()

# --- FONCTIONS API & UTILITAIRES ---

def search_tcgdex_fallback(query):
    """API de secours : TCGDex"""
    try:
        url = f"https://api.tcgdex.net/v2/fr/cards?name={query}"
        response = requests.get(url, timeout=15)
        data = response.json()
        
        results = []
        if data:
            count = 0
            for card in data:
                if count >= 60: break 
                
                img_url = f"{card['image']}/high.png" if 'image' in card else None
                if not img_url: continue

                card_number = card['id'].split('-')[-1] if '-' in card['id'] else ""
                set_name = card.get('set', {}).get('name', 'Série Inconnue')

                results.append({
                    'id': card['id'],
                    'name': card['name'],
                    'number': card_number, 
                    'set': {'name': set_name},
                    'rarity': card.get('rarity', 'Standard'),
                    'images': {'small': img_url, 'large': img_url},
                    'cardmarket': None 
                })
                count += 1
        return results
    except Exception as e:
        print(f"Erreur TCGDex: {e}")
        return None

def get_card_price(user_query):
    """Cherche la carte sur l'API officielle puis fallback."""
    clean_query = user_query.lower().strip()
    
    match = re.search(r'(\d+)(?:/\d+)?$', clean_query)
    number_query = ""
    name_part = clean_query
    
    if match:
        number_val = match.group(1) 
        number_query = f" number:{number_val}"
        name_part = clean_query[:match.start()].strip()

    name_words = name_part.split()
    translated_words = [POKEMON_NAMES.get(word, word) for word in name_words]
    translated_name = " ".join(translated_words)
    
    final_query = f"name:\"{translated_name}*\"{number_query}"
    
    try:
        url = f"https://api.pokemontcg.io/v2/cards?q={final_query}&pageSize=100"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0'}
        
        response = requests.get(url, headers=headers, timeout=30) 
        try:
            data = response.json()
        except ValueError:
            raise Exception("Réponse API invalide")

        if 'data' in data and data['data']:
            return data['data'], "official"
        
        if number_query:
            url_broad = f"https://api.pokemontcg.io/v2/cards?q=name:\"{translated_name}*\"&pageSize=100"
            response_broad = requests.get(url_broad, headers=headers, timeout=30)
            data_broad = response_broad.json()
            if 'data' in data_broad and data_broad['data']:
                return data_broad['data'], "official"

        raise Exception("Aucun résultat Officiel")

    except Exception:
        fallback_results = search_tcgdex_fallback(name_part)
        if fallback_results:
            return fallback_results, "fallback"
        return None, None

def process_image(image_file):
    image_file.seek(0)
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

def clean_text(text):
    text = str(text)
    text = text.replace("€", "EUR")
    return text.encode('latin-1', 'replace').decode('latin-1')

def create_pdf(image_array, card_name, g_px, d_px, h_px, b_px, rh, rv, final_price, api_card_data=None, extra_images=None):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    
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
    
    temp_card = "temp_card_main.jpg"
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

    if extra_images:
        pdf.add_page()
        pdf.set_font("Arial", 'B', 14)
        pdf.cell(0, 10, clean_text("Photos Supplementaires"), ln=1, align='C')
        y_pos = 30
        for i, img_file in enumerate(extra_images):
            if i > 0 and i % 2 == 0:
                pdf.add_page()
                y_pos = 30
            extra_img_array = process_image(img_file)
            temp_extra = f"temp_extra_{i}.jpg"
            cv2.imwrite(temp_extra, extra_img_array)
            pdf.image(temp_extra, x=15, y=y_pos, w=180)
            if os.path.exists(temp_extra): os.remove(temp_extra)
            y_pos += 130 

    return pdf.output(dest='S').encode('latin-1', 'replace')

# --- INTERFACE ---
st.title("⚡ Poké-Station V15")

if 'selected_api_card' not in st.session_state:
    st.session_state['selected_api_card'] = None
if 'api_source' not in st.session_state:
    st.session_state['api_source'] = None
if 'manual_mode' not in st.session_state:
    st.session_state['manual_mode'] = False
# Gestion de l'état du panneau de recherche
if 'search_expanded' not in st.session_state:
    st.session_state['search_expanded'] = True

# --- 1. RECHERCHE ---
# On utilise la variable d'état pour contrôler l'ouverture/fermeture
with st.expander("🔎 1. Recherche & Prix", expanded=st.session_state['search_expanded']):
    col_search, col_btn = st.columns([3, 1])
    with col_search:
        search_query = st.text_input("Nom du Pokémon (ex: Tortank 200)", placeholder="Nom + Numéro")
    with col_btn:
        st.write("") 
        st.write("") 
        if st.button("Go"):
            st.session_state['manual_mode'] = False
            st.session_state['selected_api_card'] = None 
            st.session_state['search_expanded'] = True # On garde ouvert pour les résultats
            with st.spinner("Recherche..."):
                results, source = get_card_price(search_query)
                if results:
                    st.session_state['api_results'] = results
                    st.session_state['api_source'] = source
                else:
                    st.warning("Aucune carte trouvée.")
                    
    # OPTION MANUELLE DE SECOURS (Dans le panneau)
    if not st.session_state.get('api_results') and not st.session_state['selected_api_card']:
        if st.button("📝 Créer la carte manuellement (si introuvable)"):
            st.session_state['manual_mode'] = True
            st.session_state['api_results'] = []
            st.session_state['selected_api_card'] = None
            st.rerun()

# --- AFFICHAGE (EN DEHORS DU PANNEAU) ---

# CAS 1 : CARTE SELECTIONNEE (VUE UNIQUE)
if st.session_state['selected_api_card']:
    st.markdown("---") # Séparateur visuel
    card = st.session_state['selected_api_card']
    
    # Message succès
    st.success(f"✅ Carte active : **{card['name']}**")
    
    col_sel_img, col_sel_info = st.columns([1, 2])
    
    with col_sel_img:
        if card.get('images') and card['images'].get('small'):
            st.image(card['images']['small'], width=250)
        else:
            st.info("Pas d'image (Mode Manuel)")

    with col_sel_info:
        st.subheader(f"{card['name']}")
        st.caption(f"Série : {card['set']['name']}")
        
        # Affichage du prix auto s'il existe
        if card.get('cardmarket') and 'prices' in card['cardmarket']:
            st.metric("Prix Cardmarket (Moyen)", f"{card['cardmarket']['prices']['averageSellPrice']} €")
        
        # Bouton pour changer
        if st.button("↩️ Changer de carte / Nouvelle recherche"):
            st.session_state['selected_api_card'] = None
            st.session_state['search_expanded'] = True # On rouvre la recherche
            st.rerun()

# CAS 2 : GRILLE DE RESULTATS (Si aucune carte sélectionnée)
elif 'api_results' in st.session_state and st.session_state['api_results'] and not st.session_state['manual_mode']:
    
    st.markdown("---")
    if st.session_state['api_source'] == "fallback":
        st.info("ℹ️ Mode Secours (TCGDex) : Images chargées sans les prix auto.")
    else:
        st.info(f"👇 **{len(st.session_state['api_results'])} résultats trouvés**. Cliquez sur 'Choisir' pour valider.")
        
    cols = st.columns(3)
    for i, card in enumerate(st.session_state['api_results']):
        col_idx = i % 3
        with cols[col_idx]:
            img_url = card['images']['small']
            st.image(img_url, use_container_width=True)
            st.caption(f"**{card['name']}**")
            st.caption(f"_{card['set']['name']}_")

            price_disp = "Prix N/A"
            if card.get('cardmarket') and 'prices' in card['cardmarket']:
                price_val = card['cardmarket']['prices']['averageSellPrice']
                price_disp = f"{price_val} €"
            
            # BOUTON SELECTION
            if st.button(f"Choisir ({price_disp})", key=f"sel_{card['id']}"):
                st.session_state['selected_api_card'] = card
                st.session_state['search_expanded'] = False # ON FERME LE PANNEAU DE RECHERCHE
                st.rerun()
            
            card_num = str(card.get('number', ''))
            if not card_num and '-' in str(card['id']):
                    card_num = str(card['id']).split('-')[-1]
            
            ebay_query = f"{card['name']} {card_num}".strip()
            ebay_url = f"https://www.ebay.fr/sch/i.html?_nkw={ebay_query}&LH_Sold=1&LH_Complete=1"
            st.markdown(f"🛒 [Voir ventes eBay]({ebay_url})")
            st.write("---")

# CAS 3 : MODE MANUEL
if st.session_state['manual_mode']:
    st.markdown("---")
    st.info("✍️ Mode Manuel activé : Entrez les détails de votre carte.")
    with st.container():
        col_m1, col_m2 = st.columns(2)
        with col_m1:
            man_name = st.text_input("Nom de la Carte", value="Ma Carte")
        with col_m2:
            man_set = st.text_input("Série / Extension", value="Inconnue")
        
        if st.button("Valider les informations manuelles"):
            manual_card = {
                'name': man_name,
                'set': {'name': man_set},
                'rarity': 'Manuelle',
                'cardmarket': None,
                'images': {'small': None} 
            }
            st.session_state['selected_api_card'] = manual_card
            st.session_state['search_expanded'] = False # On ferme la recherche
            st.rerun()

final_price_str = "Non défini"
selected_card_data = None

if st.session_state['selected_api_card']:
    selected_card_data = st.session_state['selected_api_card']
    if 'cardmarket' in selected_card_data and selected_card_data['cardmarket']:
        final_price_str = f"{selected_card_data['cardmarket']['prices']['averageSellPrice']} €"
    else:
        final_price_str = "Saisir manuellement ci-dessous"

# --- 2. MANUEL ---
# On affiche le prix manuel UNIQUEMENT si une carte est sélectionnée mais n'a pas de prix
if st.session_state['selected_api_card']:
    with st.expander("🧮 2. Prix Manuel (Obligatoire si Mode Secours/Manuel)", expanded=(final_price_str.startswith("Saisir"))):
        man_price = st.number_input("Prix estimé (€)", 0.0)
        if man_price > 0:
            final_price_str = f"{man_price} € (Manuel)"

# --- 3. PHOTO ---
# On n'affiche la gradation QUE si une carte est sélectionnée (pour éviter de grader "rien")
if st.session_state['selected_api_card']:
    st.markdown("### 📸 3. Gradation (Centrage)")

    tab_cam, tab_upload = st.tabs(["📸 Caméra Directe", "📂 Importer Fichier"])

    img_input = None
    with tab_cam:
        cam_pic = st.camera_input("Prendre une photo")
        if cam_pic: img_input = cam_pic
    with tab_upload:
        up_pic = st.file_uploader("Choisir une image", type=['jpg', 'png', 'jpeg'])
        if up_pic: img_input = up_pic

    uploaded_extras = []

    if img_input:
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
        
        # --- 4. PHOTOS SUPPLEMENTAIRES ---
        st.write("---")
        st.markdown("### 🖼️ 4. Photos Supplémentaires (Optionnel)")
        uploaded_extras = st.file_uploader("Ajouter dos / défauts", type=['jpg', 'png', 'jpeg'], accept_multiple_files=True)
        
        if uploaded_extras:
            cols_extra = st.columns(4)
            for i, extra in enumerate(uploaded_extras):
                with cols_extra[i % 4]:
                    st.image(extra, use_container_width=True)

        if th>0 and tv>0:
            rh, rv = (bl/th)*100, (bt/tv)*100
            
            st.write("---")
            st.markdown("### 📊 Résultats & PDF")
            k1, k2 = st.columns(2)
            k1.info(f"H: {rh:.1f}%")
            k2.info(f"V: {rv:.1f}%")
            
            card_label = selected_card_data['name'] if selected_card_data else "Carte"
            
            pdf_data = create_pdf(final, card_label, bl, br, bt, bb, rh, rv, final_price_str, selected_card_data, extra_images=uploaded_extras)
            st.download_button("📥 Télécharger Rapport PDF", pdf_data, f"Rapport_{card_label}.pdf", "application/pdf")
