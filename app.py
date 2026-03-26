import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import io

# PRÓBA IMPORTU BIBLIOTEK
try:
    import holidays
    pl_holidays = holidays.Poland()
    HAS_HOLIDAYS = True
except ImportError:
    HAS_HOLIDAYS = False

# --- KONFIGURACJA STRONY ---
st.set_page_config(page_title="Audyt PVaaS", layout="wide")

try:
    st.image("logo.png", width=250)
except Exception:
    pass

st.title("⚡ Audyt PV as a Service: Profil Klienta i Symulacja Długoterminowa")
st.markdown("Model: **Czysty OPEX (0 PLN na start)** | Przejście instalacji na własność | Realne dane i waloryzacja")

# --- ZAŁOŻENIA STAŁE (CENNIKI OSD) ---
STAWKA_MOCOWA_BAZOWA = 0.2194 
WSPOLNE_NETTO = 0.04346 
osd_data = {
    "PGE": {"B21": {"całodobowa": 0.06446}, "B22": {"szczyt": 0.08512, "pozaszczyt": 0.04467}, "B23": {"przedpołudnie": 0.06611, "popołudnie": 0.12438, "pozostałe": 0.02298}},
    "Tauron": {"B21": {"całodobowa": 0.07114}, "B22": {"szczyt": 0.07243, "pozaszczyt": 0.05042}, "B23": {"przedpołudnie": 0.04964, "popołudnie": 0.05610, "pozostałe": 0.03748}},
    "Enea": {"B21": {"całodobowa": 0.06820}, "B22": {"szczyt": 0.08940, "pozaszczyt": 0.04210}, "B23": {"przedpołudnie": 0.07120, "popołudnie": 1.12850, "pozostałe": 0.02050}},
    "Stoen": {"B21": {"całodobowa": 0.06150}, "B22": {"szczyt": 0.08230, "pozaszczyt": 0.03840}, "B23": {"przedpołudnie": 0.06420, "popołudnie": 1.11980, "pozostałe": 0.01820}}
}

# --- PANEL BOCZNY: ŁĄCZONA KONFIGURACJA ---
st.sidebar.header("⚙️ 1. Profil Klienta i Instalacja")
uploaded_file = st.sidebar.file_uploader("Wgraj CSV klienta (dane godzinowe)", type=['csv'])
if not uploaded_file:
    st.sidebar.warning("⚠️ Wgraj plik CSV, aby uzyskać realne dane. Obecne wyliczenia oparto na profilu syntetycznym.")
data_type = st.sidebar.radio("Typ danych w pliku:", ["15-minutowe", "Godzinowe"], index=1)
osd_choice = st.sidebar.selectbox("Operator OSD", list(osd_data.keys()))
taryfa_choice = st.sidebar.selectbox("Taryfa", ["B21", "B22", "B23"])
cena_mwh = st.sidebar.number_input("Obecna cena energii czynnej (PLN/MWh netto)", value=485.0)

moc_pv = st.sidebar.number_input("Moc PV (kWp)", value=500.0) 
uzysk = st.sidebar.number_input("Uzysk roczny (kWh/kWp)", value=1000.0)
degradacja_pv = st.sidebar.number_input("Roczna degradacja paneli PV (%)", value=0.5, step=0.1) / 100

st.sidebar.header("💶 2. Parametry Finansowe PVaaS")
cena_pvaas_eur = st.sidebar.number_input("Cena usługi PVaaS (EUR/MWh)", value=65.0, step=1.0)
kurs_eur = st.sidebar.number_input("Kurs EUR/PLN", value=4.30, step=0.01)

st.sidebar.header("📈 3. Czas i Waloryzacja")
okres_umowy = st.sidebar.selectbox("Okres umowy PVaaS (lata)", [10, 15, 20], index=1)
cykl_zycia = st.sidebar.slider("Całkowita żywotność instalacji (lata)", min_value=15, max_value=35, value=25, step=1)
wzrost_cen_pradu = st.sidebar.number_input("Roczny wzrost cen prądu i dyst. (%)", value=3.0, step=0.5) / 100
wzrost_oplaty_mocowej = st.sidebar.number_input("Roczny wzrost opłaty mocowej (%)", value=10.0, step=1.0) / 100
wzrost_abonamentu = st.sidebar.number_input("Roczna waloryzacja abonamentu PVaaS (%)", value=2.0, step=0.5) / 100

# ==============================================================================
# LOKALNY SILNIK OBLICZENIOWY: ROK 1 (PRECYZYJNA ANALIZA PROFILU)
# ==============================================================================

df = None
if uploaded_file:
    try:
        raw = uploaded_file.read()
        try: decoded = raw.decode('cp1250')
        except: decoded = raw.decode('utf-8', errors='ignore')
        df_raw = pd.read_csv(io.StringIO(decoded), sep=';', decimal=',', engine='python', header=None, skiprows=1).dropna(how='all')
        if df_raw.shape[1] >= 3:
            t = pd.to_datetime(df_raw.iloc[:, 0].astype(str) + ' ' + df_raw.iloc[:, 1].astype(str), dayfirst=True, errors='coerce')
            v = pd.to_numeric(df_raw.iloc[:, 2], errors='coerce').fillna(0)
            temp = pd.DataFrame({'T': t, 'V': v}).dropna(subset=['T'])
            if data_type == "15-minutowe":
                df = temp.set_index('T')['V'].resample('1H').sum().to_frame(name='Pobór').reset_index().rename(columns={'T': 'Timestamp'})
            else:
                df = temp.rename(columns={'T': 'Timestamp', 'V': 'Pobór'}).reset_index(drop=True)
    except Exception as e: st.error(f"Błąd pliku: {e}")

if df is None:
    dates = pd.date_range("2024-07-01", periods=8760, freq="h")
    pobor_baza = np.random.uniform(500, 1500, 8760)
    df = pd.DataFrame({"Timestamp": dates, "Pobór": pobor_baza})
    df['Godzina'] = df['Timestamp'].dt.hour
    df['Roboczy'] = df['Timestamp'].dt.weekday < 5
    df.loc[(df['Roboczy']) & (df['Godzina'] >= 8) & (df['Godzina'] < 17), 'Pobór'] += np.random.uniform(1000, 2000)

def check_holiday(dt):
    if HAS_HOLIDAYS: return dt in pl_holidays
    return (dt.month, dt.day) in [(1,1),(1,6),(5,1),(5,3),(8,15),(11,1),(11,11),(12,25),(12,26)]

df['Data_Klucz'] = df['Timestamp'].dt.date
df['Roboczy'] = (df['Timestamp'].dt.weekday < 5) & (~df['Timestamp'].apply(check_holiday))
df['Godzina'] = df['Timestamp'].dt.hour
df['Rok_Miesiac'] = df['Timestamp'].dt.to_period('M')

weights = {1:0.3, 2:0.5, 3:0.9, 4:1.2, 5:1.5, 6:1.6, 7:1.6, 8:1.4, 9:1.0, 10:0.6, 11:0.3, 12:0.2}
sin_p = np.maximum(0, np.sin((df['Godzina'] - 6) * np.pi / 12))
df['Gen_Raw'] = sin_p * df['Timestamp'].dt.month.map(weights)
real_y1_produkcja_mwh = (moc_pv * uzysk) / 1000
df['Generacja_PV'] = (df['Gen_Raw'] / df['Gen_Raw'].sum()) * (moc_pv * uzysk * (len(df)/8760)) if df['Gen_Raw'].sum() > 0 else 0

df['Autokonsumpcja'] = np.minimum(df['Pobór'], df['Generacja_PV'])
df['Nowy_Pobór'] = np.maximum(0, df['Pobór'] - df['Autokonsumpcja'])
real_y1_autokonsumpcja_mwh = df['Autokonsumpcja'].sum() / 1000

def calc_strefowe(col):
    en = df[col].sum() * (cena_mwh / 1000)
    def get_strefa(row):
        h, rob = row['Godzina'], row['Roboczy']
        if taryfa_choice == "B21": return "całodobowa"
        if taryfa_choice == "B22": return "szczyt" if (6 <= h < 21) and rob else "pozaszczyt"
        if taryfa_choice == "B23":
            if not rob: return "pozostałe"
            return "przedpołudnie" if 7 <= h < 13 else ("popołudnie" if 16 <= h < 21 else "pozostałe")
        return "całodobowa"
    df['Tmp_Strefa'] = df.apply(get_strefa, axis=1)
    dys = sum(df[df['Tmp_Strefa'] == s][col].sum() * (osd_data[osd_choice][taryfa_choice][s] + WSPOLNE_NETTO) for s in osd_data[osd_choice][taryfa_choice])
    return en, dys

e_p_y1, d_p_y1 = calc_strefowe('Pobór')         
e_n_y1, d_n_y1 = calc_strefowe('Nowy_Pobór')    

oszczednosc_energia_y1 = e_p_y1 - e_n_y1
oszczednosc_dystrybucja_y1 = d_p_y1 - d_n_y1
zyski_sieciowe_energia_dyst_y1 = oszczednosc_energia_y1 + oszczednosc_dystrybucja_y1

# Opłata Mocowa
df['Is_Szczyt_Mocowy'] = (df['Godzina'] >= 7) & (df['Godzina'] < 22) & df['Roboczy']
def get_moc_daily(sub_df, col):
    if not sub_df['Roboczy'].any(): return pd.Series({'Koszt': 0.0, 'Mnożnik': 0.17, 'L': 0.0})
    e_sz, e_d = sub_df[sub_df['Is_Szczyt_Mocowy']][col].sum(), sub_df[col].sum()
    if e_d < 0.1: return pd.Series({'Koszt': 0.0, 'Mnożnik': 0.17, 'L': 0.0})
    l_f = (e_sz / e_d) - 0.625
    mn = 0.17 if l_f <= 0.05 else (0.50 if l_f <= 0.10 else (0.83 if l_f <= 0.15 else 1.00))
    return pd.Series({'Koszt': e_sz * STAWKA_MOCOWA_BAZOWA * mn, 'Mnożnik': mn, 'L': l_f})

moc_po = df.groupby('Data_Klucz').apply(lambda x: get_moc_daily(x, 'Nowy_Pobór'))
moc_pre = df.groupby('Data_Klucz').apply(lambda x: get_moc_daily(x, 'Pobór'))

total_m_pre_y1, total_m_po_y1 = moc_pre['Koszt'].sum(), moc_po['Koszt'].sum()
zysk_mocowy_y1 = total_m_pre_y1 - total_m_po_y1 

zyski_sieciowe_brutto_total_y1 = zyski_sieciowe_energia_dyst_y1 + zysk_mocowy_y1

# ==============================================================================
# JĄDRO OBLICZENIOWE PVaaS: SYMULACJA Z PRZEJŚCIEM NA WŁASNOŚĆ
# ==============================================================================

abonament_roczny_pln_y1 = real_y1_produkcja_mwh * cena_pvaas_eur * kurs_eur

dane_symulacji = []
skumulowany_zysk = 0.0

aktualna_roczna_produkcja_mwh = real_y1_produkcja_mwh
aktualna_roczna_autokonsumpcja_mwh = real_y1_autokonsumpcja_mwh 

wartosc_uniknietej_mwh_pradu = oszczednosc_energia_y1 / real_y1_autokonsumpcja_mwh if real_y1_autokonsumpcja_mwh > 0 else 0
wartosc_uniknietej_mwh_dyst = oszczednosc_dystrybucja_y1 / real_y1_autokonsumpcja_mwh if real_y1_autokonsumpcja_mwh > 0 else 0

aktualna_wartosc_pradu = wartosc_uniknietej_mwh_pradu
aktualna_wartosc_dyst = wartosc_uniknietej_mwh_dyst
aktualny_indeks_mocowy = 1.0  
aktualny_abonament = abonament_roczny_pln_y1

# Pętla liczy aż do końca całkowitej żywotności instalacji (np. 25 lat)
for rok in range(1, cykl_zycia + 1):
    f_prod_rok = aktualna_roczna_produkcja_mwh
    f_auto_rok = aktualna_roczna_autokonsumpcja_mwh
    
    # Oszczędność na Energii i Dystrybucji
    zysk_brutto_prad = f_auto_rok * aktualna_wartosc_pradu
    zysk_brutto_dyst = f_auto_rok * aktualna_wartosc_dyst
    zysk_energia_dyst = zysk_brutto_prad + zysk_brutto_dyst
    
    # Oszczędność Mocowa
    wspolczynnik_degradacji_szczytow = aktualna_roczna_produkcja_mwh / real_y1_produkcja_mwh
    zysk_mocowy_rok = zysk_mocowy_y1 * wspolczynnik_degradacji_szczytow * aktualny_indeks_mocowy
    total_zysk_siec_rok = zysk_energia_dyst + zysk_mocowy_rok
    
    # LOGIKA WŁASNOŚCI: Abonament płacimy tylko w trakcie trwania umowy!
    if rok <= okres_umowy:
        koszt_pvaas_rok = aktualny_abonament
        # Waloryzacja abonamentu tylko w trakcie trwania umowy
        aktualny_abonament *= (1 + wzrost_abonamentu)
    else:
        koszt_pvaas_rok = 0.0 # Instalacja jest własnością klienta!
    
    zysk_netto_rok = total_zysk_siec_rok - koszt_pvaas_rok
    skumulowany_zysk += zysk_netto_rok
    
    status_umowy = "W trakcie umowy" if rok <= okres_umowy else "Instalacja na własność"
    
    dane_symulacji.append({
        "Rok": rok,
        "Status": status_umowy,
        "Produkcja PV (MWh)": f_prod_rok,
        "Oszcz. Energia i Dystryb. (PLN)": zysk_energia_dyst,
        "Oszcz. Mocowa (PLN)": zysk_mocowy_rok,
        "Suma Oszczędności Brutto (PLN)": total_zysk_siec_rok,
        "Koszt PVaaS (PLN)": koszt_pvaas_rok,
        "Zysk Klienta Netto (PLN)": zysk_netto_rok,
        "Skumulowany Zysk (PLN)": skumulowany_zysk
    })
    
    # Waloryzacja sieciowa na kolejny rok
    aktualna_wartosc_pradu *= (1 + wzrost_cen_pradu)
    aktualna_wartosc_dyst *= (1 + wzrost_cen_pradu)
    aktualny_indeks_mocowy *= (1 + wzrost_oplaty_mocowej) 
    aktualna_roczna_produkcja_mwh *= (1 - degradacja_pv)
    aktualna_roczna_autokonsumpcja_mwh *= (1 - degradacja_pv)

df_sym_final = pd.DataFrame(dane_symulacji)

# Obliczanie ROI (Czas zwrotu z inwestycji)
rok_zwrotu = 0
for index, row in df_sym_final.iterrows():
    if row['Skumulowany Zysk (PLN)'] > 0:
        rok_zwrotu = row['Rok']
        break

if rok_zwrotu == 1:
    tekst_zwrotu = "Natychmiast (Zysk już od 1. roku, brak wkładu początkowego!)"
elif rok_zwrotu > 1:
    tekst_zwrotu = f"W {rok_zwrotu}. roku trwania umowy"
else:
    tekst_zwrotu = "Brak pełnego zwrotu w analizowanym okresie"

# ==============================================================================
# SEKCJA WYŚWIETLANIA WYNIKÓW (GUI)
# ==============================================================================

st.subheader("💡 Szczegółowy Bilans Profilu (Rok 1)")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Produkcja z PV", f"{real_y1_produkcja_mwh:,.0f} MWh/rok")
c2.metric("Oszcz. Energia i Dyst.", f"{zyski_sieciowe_energia_dyst_y1:,.2f} PLN")
c3.metric("Oszcz. z Opłaty Mocowej", f"{zysk_mocowy_y1:,.2f} PLN")
c4.metric("Suma Oszczędności Brutto", f"{zyski_sieciowe_brutto_total_y1:,.2f} PLN")

st.markdown("---")
st.subheader(f"📈 Symulacja Finansowa: Cykl {cykl_zycia} lat (Umowa PVaaS: {okres_umowy} lat)")

# Wyróżnione boxy informacyjne
st.success(f"**Czas zwrotu z inwestycji:** {tekst_zwrotu}")
st.info(f"**Co po umowie?** Po upływie {okres_umowy} lat, instalacja przechodzi na własność klienta za **0 PLN**. Abonament znika, a klient czerpie 100% zysków z oszczędności przez kolejne dekady.")

c_m1, c_m2, c_m3 = st.columns(3)
with c_m1: st.metric("Roczny abonament (Rok 1)", f"{abonament_roczny_pln_y1:,.2f} PLN", "Spada do 0 po umowie")
zysk_tylko_w_umowie = df_sym_final[df_sym_final['Rok'] <= okres_umowy]['Zysk Klienta Netto (PLN)'].sum()
with c_m2: st.metric(f"Zysk Skumulowany (w trakcie umowy)", f"{zysk_tylko_w_umowie:,.2f} PLN", "Na czysto")
with c_m3: st.metric(f"ZYSK SKUMULOWANY ({cykl_zycia} LAT)", f"{skumulowany_zysk:,.2f} PLN", "Łączny zysk klienta")

# Wykres przepływów (Zjawiskowy po zakończeniu umowy)
fig = go.Figure()
fig.add_trace(go.Bar(x=df_sym_final["Rok"], y=df_sym_final["Oszcz. Energia i Dystryb. (PLN)"], name="Oszcz. Energia + Dystrybucja", marker_color='#27AE60'))
fig.add_trace(go.Bar(x=df_sym_final["Rok"], y=df_sym_final["Oszcz. Mocowa (PLN)"], name="Oszczędność Mocowa", marker_color='#F1C40F'))
fig.add_trace(go.Bar(x=df_sym_final["Rok"], y=-df_sym_final["Koszt PVaaS (PLN)"], name="Opłata PVaaS (Koszt)", marker_color='#E74C3C'))
fig.add_trace(go.Scatter(x=df_sym_final["Rok"], y=df_sym_final["Skumulowany Zysk (PLN)"], name="Skumulowany Zysk Netto", mode='lines+markers', line=dict(color='#2980B9', width=3), yaxis="y2"))

# Pionowa linia symbolizująca przejście na własność
fig.add_vline(x=okres_umowy + 0.5, line_width=2, line_dash="dash", line_color="black")
fig.add_annotation(x=okres_umowy + 0.5, y=max(df_sym_final["Skumulowany Zysk (PLN)"])/2, text="Przejście na własność (Koniec Abonamentu)", showarrow=False, textangle=-90, yshift=10)

fig.update_layout(barmode='relative', title="Struktura Zysków Brutto vs Opłata PVaaS (z przejściem na własność)", xaxis=dict(title="Rok", tickmode='linear'), yaxis=dict(title="Kwota roczna (PLN)"), yaxis2=dict(title="Zysk skumulowany (PLN)", overlaying='y', side='right'), legend=dict(x=0.01, y=0.99), template="plotly_white", hovermode="x unified")
st.plotly_chart(fig, use_container_width=True)

# --- TABELA DANYCH I POBIERANIE ---
st.markdown("---")
st.subheader("📋 Szczegółowa tabela symulacji")

df_formatted = df_sym_final.copy()
for col in df_formatted.columns:
    if col == "Produkcja PV (MWh)": df_formatted[col] = df_formatted[col].apply(lambda x: f"{x:,.1f}".replace(",", " "))
    elif col not in ["Rok", "Status"]: df_formatted[col] = df_formatted[col].apply(lambda x: f"{x:,.2f} PLN".replace(",", " "))
st.dataframe(df_formatted.set_index("Rok"), use_container_width=True)

# EKSPORT DO EXCELA 
def create_excel_pvaas(df_sym, moc, prod_y1, auto_y1, sub_y1):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_sym.to_excel(writer, sheet_name='Symulacja_PVaaS', index=False)
        workbook = writer.book
        worksheet = writer.sheets['Symulacja_PVaaS']
        
        header_fmt = workbook.add_format({'bold': True, 'bg_color': '#D7E4BC', 'border': 1})
        num_fmt = workbook.add_format({'num_format': '#,##0.00 "PLN"', 'border': 1})
        prod_fmt = workbook.add_format({'num_format': '#,##0.0 "MWh"', 'border': 1})
        
        for col_num, value in enumerate(df_sym.columns.values):
            worksheet.write(0, col_num, value, header_fmt)
        
        for row in range(1, len(df_sym) + 1):
            worksheet.write(row, 0, df_sym.iloc[row-1, 0]) 
            worksheet.write(row, 1, df_sym.iloc[row-1, 1]) # Status
            worksheet.write(row, 2, df_sym.iloc[row-1, 2], prod_fmt) 
            worksheet.write(row, 3, df_sym.iloc[row-1, 3], num_fmt) 
            worksheet.write(row, 4, df_sym.iloc[row-1, 4], num_fmt) 
            worksheet.write(row, 5, df_sym.iloc[row-1, 5], num_fmt) 
            worksheet.write(row, 6, df_sym.iloc[row-1, 6], num_fmt) 
            worksheet.write(row, 7, df_sym.iloc[row-1, 7], num_fmt) 
            worksheet.write(row, 8, df_sym.iloc[row
