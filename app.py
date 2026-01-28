import streamlit as st
import cv2
import numpy as np
from fpdf import FPDF
import os
from datetime import datetime
import requests
import re

# --- CONFIGURATION ---
st.set_page_config(page_title="Poké-Station V16", page_icon="⚡", layout="wide")

# 🔒 CONFIGURATION MOT DE PASSE DE SECOURS
MOT_DE_PASSE_SECOURS = "admin"

# --- DICTIONNAIRE DE TRADUCTION (FR -> EN) ---
# Ajout de "Embrochet" pour l'exemple
POKEMON_NAMES = {
    "tortank": "Blastoise", "dracaufeu": "Charizard", "florizarre": "Venusaur",
    "reptincel": "Charmeleon", "salameche": "Charmander", "carapuce": "Squirtle",
    "carabaffe": "Wartortle", "bulbizarre": "Bulbasaur", "herbizarre": "Ivysaur",
    "evoli": "Eevee", "noctali": "Umbreon", "mentali": "Espeon",
    "aquali": "Vaporeon", "voltali": "Jolteon", "pyroli": "Flareon",
    "mewtwo": "Mewtwo", "mew": "Mew", "pikachu": "Pikachu",
    "rayquaza": "Rayquaza", "lugia": "Lugia", "dracolosse": "Dragonite",
    "leviator": "Gyarados", "ectoplasma": "Gengar", "embrochet": "Remoraid",
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
            secret_code = st.secrets["access_code"]
            if password_input == secret_code:
                st.session_state['password_correct'] = True
                st.rerun()
            else:
                st.error("❌ Code incorrect")
        except (FileNotFoundError, KeyError):
            if password_input == MOT_DE_PASSE_SECOURS: 
                st.session_state['password_correct'] = True
                st.rerun()
            else:
                st.error("❌ Code incorrect")
            
    return False

if not check_password():
    st.stop()

# --- FONCTIONS API & UTILITAIRES ---

def clean_number(num_str):
    """Nettoie un numéro de carte pour comparaison (ex: '082' -> '82')"""
    if not num_str: return ""
    # Garde seulement les chiffres
    nums = re.findall(r'\d+', str(num_str))
    if nums:
        return str(int(nums[0])) # Enlève les zéros non significatifs
    return ""

def search_tcgdex_fallback(query_name, target_number=None):
    """API de secours : TCGDex (Français) avec filtrage par numéro"""
    try:
        url = f"https://api.tcgdex.net/v2/fr/cards?name={query_name}"
        response = requests.get(url, timeout=15)
        data = response.json()
        
        results = []
        if data:
            count = 0
            for card in data:
                if count >= 60: break 
                
                # Extraction du numéro (souvent à la fin de l'ID local ex: sv3pt5-184)
                raw_number = card['id'].split('-')[-1] if '-' in card['id'] else ""
                
                # FILTRAGE PAR NUMERO SI DEMANDÉ
                if target_number:
                    # On compare les numéros nettoyés (82 == 082)
                    if clean_number(raw_number) != clean_number(target_number):
                        continue # On passe si ça ne correspond pas

                img_url = f"{card['image']}/high.png" if 'image' in card else None
                if not img_url: continue

                # Extraction infos supplémentaires (TCGDex donne moins d'infos directes dans la liste)
                # On fait avec ce qu'on a
                set_name = card.get('set', {}).get('name', 'Série Inconnue')
                
                results.append({
                    'id': card['id'],
                    'name': card['name'],
                    'number': raw_number, 
                    'set': {'name': set_name, 'releaseDate': 'Inconnue'}, # Date souvent absente en liste simple
                    'artist': card.get('illustrator', 'Inconnu'),
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
    """Recherche multi-sources avec gestion intelligente du numéro."""
    clean_query = user_query.lower().strip()
    
    # 1. Extraction Nom / Numéro
    # Regex pour trouver un numéro à la fin (ex: "82" ou "082" ou "82/165")
    match = re.search(r'(\d+)(?:/\d+)?$', clean_query)
    number_query = ""
    target_number = None # Pour le filtrage manuel fallback
    name_part = clean_query
    
    if match:
        number_val = match.group(1) 
        target_number = number_val
        number_query = f" number:{number_val}"
        name_part = clean_query[:match.start()].strip() # Enlève le numéro du nom

    # 2. Traduction
    name_words = name_part.split()
    translated_words = [POKEMON_NAMES.get(word, word) for word in name_words]
    translated_name = " ".join(translated_words)
    
    # 3. Requête Officielle
    final_query = f"name:\"{translated_name}*\"{number_query}"
    
    try:
        url = f"https://api.pokemontcg.io/v2/cards?q={final_query}&pageSize=100"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        
        response = requests.get(url, headers=headers, timeout=20)
        data = response.json()

        if 'data' in data and data['data']:
            return data['data'], "official"
        
        # Si échec officiel, on tente le fallback TCGDex avec le nom FR original
        raise Exception("Rien sur API Officielle")

    except Exception:
        # On passe le numéro cible au fallback pour filtrer
        fallback_results = search_tcgdex_fallback(name_part, target_number)
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
    # Lignes un peu plus épaisses pour le mobile
    THICKNESS = 3 
    
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
        artist = api_card_data.get('artist', 'Inconnu')
        info_txt = clean_text(f"Serie: {set_name} | Art: {artist} | Rarete: {rarity}")
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
st.title("⚡ Poké-Station V16")

if 'selected_api_card' not in st.session_state:
    st.session_state['selected_api_card'] = None
if 'api_source' not in st.session_state:
    st.session_state['api_source'] = None
if 'manual_mode' not in st.session_state:
    st.session_state['manual_mode'] = False
if 'search_expanded' not in st.session_state:
    st.session_state['search_expanded'] = True

# --- 1. RECHERCHE ---
with st.expander("🔎 1. Recherche & Prix", expanded=st.session_state['search_expanded']):
    col_search, col_btn = st.columns([3, 1])
    with col_search:
        # Placeholder mis à jour pour inciter à mettre le numéro
        search_query = st.text_input("Nom + Numéro (ex: Embrochet 82)", placeholder="ex: Embrochet 82")
    with col_btn:
        st.write("") 
        st.write("") 
        if st.button("Go"):
            st.session_state['manual_mode'] = False
            st.session_state['selected_api_card'] = None 
            st.session_state['search_expanded'] = True
            with st.spinner("Recherche précise..."):
                results, source = get_card_price(search_query)
                if results:
                    st.session_state['api_results'] = results
                    st.session_state['api_source'] = source
                else:
                    st.warning("Aucune carte trouvée. Vérifiez l'orthographe ou le numéro.")
                    
    if not st.session_state.get('api_results') and not st.session_state['selected_api_card']:
        if st.button("📝 Créer manuellement"):
            st.session_state['manual_mode'] = True
            st.session_state['api_results'] = []
            st.session_state['selected_api_card'] = None
            st.rerun()

# --- AFFICHAGE ---

if st.session_state['selected_api_card']:
    st.markdown("---")
    card = st.session_state['selected_api_card']
    
    st.success(f"✅ Carte active : **{card['name']}**")
    
    col_sel_img, col_sel_info = st.columns([1, 2])
    
    with col_sel_img:
        if card.get('images') and card['images'].get('small'):
            st.image(card['images']['small'], width=300)
        else:
            st.info("Pas d'image (Mode Manuel)")

    with col_sel_info:
        st.subheader(f"{card['name']}")
        
        # --- BLOC DÉTAILS AMÉLIORÉ ---
        set_name = card.get('set', {}).get('name', 'Inconnu')
        artist = card.get('artist', 'Inconnu')
        release = card.get('set', {}).get('releaseDate', 'Inconnue')
        rarity = card.get('rarity', 'Inconnue')
        
        st.markdown(f"**Série :** {set_name}")
        st.markdown(f"**Illustrateur :** {artist}")
        st.markdown(f"**Sortie :** {release}")
        st.markdown(f"**Rareté :** {rarity}")
        
        if card.get('cardmarket') and 'prices' in card['cardmarket']:
            st.metric("Prix Cardmarket", f"{card['cardmarket']['prices']['averageSellPrice']} €")
        
        if st.button("↩️ Nouvelle recherche"):
            st.session_state['selected_api_card'] = None
            st.session_state['search_expanded'] = True
            st.rerun()

elif 'api_results' in st.session_state and st.session_state['api_results'] and not st.session_state['manual_mode']:
    st.markdown("---")
    res_count = len(st.session_state['api_results'])
    if st.session_state['api_source'] == "fallback":
        st.info(f"ℹ️ Mode Secours (TCGDex) : {res_count} résultat(s).")
    else:
        st.info(f"✅ {res_count} résultat(s) trouvé(s).")
        
    cols = st.columns(3)
    for i, card in enumerate(st.session_state['api_results']):
        col_idx = i % 3
        with cols[col_idx]:
            img_url = card['images']['small']
            st.image(img_url, use_container_width=True)
            st.caption(f"**{card['name']}** #{card.get('number', '?')}")
            st.caption(f"_{card['set']['name']}_")

            price_disp = "Prix N/A"
            if card.get('cardmarket') and 'prices' in card['cardmarket']:
                price_val = card['cardmarket']['prices']['averageSellPrice']
                price_disp = f"{price_val} €"
            
            if st.button(f"Choisir ({price_disp})", key=f"sel_{card['id']}"):
                st.session_state['selected_api_card'] = card
                st.session_state['search_expanded'] = False
                st.rerun()
            
            # Lien eBay
            card_num = str(card.get('number', ''))
            if not card_num and '-' in str(card['id']):
                    card_num = str(card['id']).split('-')[-1]
            ebay_query = f"{card['name']} {card_num}".strip()
            ebay_url = f"https://www.ebay.fr/sch/i.html?_nkw={ebay_query}&LH_Sold=1&LH_Complete=1"
            st.markdown(f"[Voir ventes eBay]({ebay_url})")
            st.write("---")

if st.session_state['manual_mode']:
    st.markdown("---")
    st.info("✍️ Mode Manuel")
    with st.container():
        col_m1, col_m2 = st.columns(2)
        with col_m1:
            man_name = st.text_input("Nom", value="Ma Carte")
            man_artist = st.text_input("Illustrateur", value="")
        with col_m2:
            man_set = st.text_input("Série", value="")
            man_rarity = st.text_input("Rareté", value="")
        
        if st.button("Valider"):
            manual_card = {
                'name': man_name,
                'set': {'name': man_set, 'releaseDate': '?'},
                'artist': man_artist,
                'rarity': man_rarity,
                'cardmarket': None,
                'images': {'small': None} 
            }
            st.session_state['selected_api_card'] = manual_card
            st.session_state['search_expanded'] = False
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
if st.session_state['selected_api_card']:
    with st.expander("🧮 2. Prix Manuel (Si nécessaire)", expanded=(final_price_str.startswith("Saisir"))):
        man_price = st.number_input("Prix estimé (€)", 0.0)
        if man_price > 0:
            final_price_str = f"{man_price} € (Manuel)"

# --- 3. PHOTO ---
if st.session_state['selected_api_card']:
    st.markdown("### 📸 3. Gradation (Centrage)")
    
    # GUIDE PHOTO
    st.info("💡 **Guide Photo** : Cadrez la carte bien au centre et bien à plat. Pour la mise au point (netteté), touchez l'écran de votre téléphone avant de prendre la photo.")

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
        st.caption("Ajustez les lignes avec les curseurs ci-dessous.")
        
        h_c, w_c = cropped.shape[:2]
        
        sc1, sc2 = st.columns(2)
        with sc1:
            st.markdown("**Horizontal**")
            lo = st.slider("Bord Gauche", 0, w_c, int(w_c*0.05), key="lo")
            li = st.slider("Image Gauche", 0, w_c, int(w_c*0.10), key="li")
            ri = st.slider("Image Droite", 0, w_c, int(w_c*0.90), key="ri")
            ro = st.slider("Bord Droit", 0, w_c, int(w_c*0.95), key="ro")
        with sc2:
            st.markdown("**Vertical**")
            to = st.slider("Bord Haut", 0, h_c, int(h_c*0.05), key="to")
            ti = st.slider("Image Haut", 0, h_c, int(h_c*0.10), key="ti")
            bi = st.slider("Image Bas", 0, h_c, int(h_c*0.90), key="bi")
            bo = st.slider("Bord Bas", 0, h_c, int(h_c*0.95), key="bo")
            
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
