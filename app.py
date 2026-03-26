import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import io

# PRÓBA IMPORTU BIBLIOTEK (BEZPIECZNIKI Z PIERWOTNEGO KODU)
try:
    import holidays
    pl_holidays = holidays.Poland()
    HAS_HOLIDAYS = True
except ImportError:
    HAS_HOLIDAYS = False

# --- KONFIGURACJA STRONY ---
st.set_page_config(page_title="Audyt PVaaS B2B", layout="wide")
st.title("⚡ Profesjonalny Audyt PV as a Service: Profil Klienta i Symulacja Długoterminowa")
st.markdown("Model: **Czysty OPEX (0 PLN na start)** | Realne dane profilu | Waloryzacja i Degradacja")

# --- ZAŁOŻENIA STAŁE (Z PIERWOTNEGO KODU) ---
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

st.sidebar.header("📈 3. Czas i Waloryzacja (Inflacja)")
okres_umowy = st.sidebar.selectbox("Okres symulacji (lata)", [10, 15, 20], index=1)
wzrost_cen_pradu = st.sidebar.number_input("Roczny wzrost cen prądu i dyst. (%)", value=3.0, step=0.5) / 100
wzrost_abonamentu = st.sidebar.number_input("Roczna waloryzacja abonamentu PVaaS (%)", value=2.0, step=0.5) / 100

# ==============================================================================
# LOKALNY SILNIK OBLICZENIOWY: ROK 1 (PRECYZYJNA ANALIZA PROFILU)
# ==============================================================================

# --- WCZYTYWANIE DANYCH ---
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

# Tworzenie profilu syntetycznego, jeśli brak pliku
if df is None:
    dates = pd.date_range("2024-07-01", periods=8760, freq="h")
    # Generowanie bazy (konsumpcja tła)
    pobor_baza = np.random.uniform(500, 1500, 8760)
    # Dodanie szczytów roboczych (8-17)
    df = pd.DataFrame({"Timestamp": dates, "Pobór": pobor_baza})
    df['Godzina'] = df['Timestamp'].dt.hour
    df['Roboczy'] = df['Timestamp'].dt.weekday < 5
    df.loc[(df['Roboczy']) & (df['Godzina'] >= 8) & (df['Godzina'] < 17), 'Pobór'] += np.random.uniform(1000, 2000)

# --- LOGIKA DAT I OBLICZENIA PROFILI ---
def check_holiday(dt):
    if HAS_HOLIDAYS: return dt in pl_holidays
    return (dt.month, dt.day) in [(1,1),(1,6),(5,1),(5,3),(8,15),(11,1),(11,11),(12,25),(12,26)]

df['Data_Klucz'] = df['Timestamp'].dt.date
df['Roboczy'] = (df['Timestamp'].dt.weekday < 5) & (~df['Timestamp'].apply(check_holiday))
df['Godzina'] = df['Timestamp'].dt.hour
df['Rok_Miesiac'] = df['Timestamp'].dt.to_period('M')
df['Etykieta_Miesiac'] = df['Timestamp'].dt.strftime('%Y-%m')

# Generowanie profilu PV
weights = {1:0.3, 2:0.5, 3:0.9, 4:1.2, 5:1.5, 6:1.6, 7:1.6, 8:1.4, 9:1.0, 10:0.6, 11:0.3, 12:0.2}
sin_p = np.maximum(0, np.sin((df['Godzina'] - 6) * np.pi / 12))
df['Gen_Raw'] = sin_p * df['Timestamp'].dt.month.map(weights)
# Skalowanie generacji do założonego uzysku
real_y1_produkcja_mwh = (moc_pv * uzysk) / 1000
df['Generacja_PV'] = (df['Gen_Raw'] / df['Gen_Raw'].sum()) * (moc_pv * uzysk * (len(df)/8760)) if df['Gen_Raw'].sum() > 0 else 0

# Autokonsumpcja
df['Autokonsumpcja'] = np.minimum(df['Pobór'], df['Generacja_PV'])
df['Nowy_Pobór'] = np.maximum(0, df['Pobór'] - df['Autokonsumpcja'])

real_y1_autokonsumpcja_mwh = df['Autokonsumpcja'].sum() / 1000

# --- PRECYZYJNE WYLICZENIE FINANSÓW: STREFY I OPŁATA MOCOWA ---

# Opłata Mocowa 2026 (Logika dzienna)
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

# Dystrybucja strefowa i energia czynna (Logika roczna)
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
    # Dystrybucja strefowa + WSPOLNE_NETTO (jako jedna suma sieciowa zmienna)
    dys = sum(df[df['Tmp_Strefa'] == s][col].sum() * (osd_data[osd_choice][taryfa_choice][s] + WSPOLNE_NETTO) for s in osd_data[osd_choice][taryfa_choice])
    return en, dys

e_p_y1, d_p_y1 = calc_strefowe('Pobór')
e_n_y1, d_n_y1 = calc_strefowe('Nowy_Pobór')

# SUMARYCZNY ZYSK Z SIECI (BRUTTO) W ROKU 1
# Czyli ile PLN klient *nie zapłaci* do OSD i Sprzedawcy dzięki instalacji PV.
zyski_sieciowe_brutto_y1 = (e_p_y1 + d_p_y1 + total_m_pre_y1) - (e_n_y1 + d_n_y1 + total_m_po_y1)

# ==============================================================================
# JĄDRO OBLICZENIOWE PVaaS: SYMULACJA DŁUGOTERMINOWA (PĘTLA CZASU)
# ==============================================================================

# Opłata za PVaaS w pierwszym roku (Stały Abonament roczny wyliczony z EUR/MWh * Produkcja)
abonament_roczny_pln_y1 = real_y1_produkcja_mwh * cena_pvaas_eur * kurs_eur

dane_symulacji = []
skumulowany_zysk = 0.0

# Parametry startowe dla pętli
aktualna_roczna_produkcja_mwh = real_y1_produkcja_mwh
# Oszczędność brutto w MWh (realna autokonsumpcja z profilu)
aktualna_roczna_autokonsumpcja_mwh = real_y1_autokonsumpcja_mwh 

# Uśredniona cena prądu i dystrybucji z faktur w roku 1 (do waloryzacji)
# Robimy to, żeby móc stosować płaską inflację % w pętli.
energia_total_pobor_mwh = df['Pobór'].sum() / 1000
usredniona_cena_pradu_y1 = e_p_y1 / energia_total_pobor_mwh
# Łączymy tu dystrybucję strefową + opłatę jako uśrednioną stawkę sieciową
usredniona_cena_dyst_total_y1 = (d_p_y1 + total_m_pre_y1) / energia_total_pobor_mwh

aktualna_cena_pradu = usredniona_cena_pradu_y1
aktualna_cena_dyst = usredniona_cena_dyst_total_y1
aktualny_abonament = abonament_roczny_pln_y1

# --- START PĘTLI SYMULACJI (LATA 1 do okres_umowy) ---
for rok in range(1, okres_umowy + 1):
    # Fizyczna Degradacja (Produkcja i Autokonsumpcja spadają)
    f_prod_rok = aktualna_roczna_produkcja_mwh
    f_auto_rok = aktualna_roczna_autokonsumpcja_mwh
    
    # Oszczędność z sieci BRUTTO (Degradacja wolumenu MWh x Waloryzacja ceny PLN/MWh)
    zysk_brutto_prad = f_auto_rok * aktualna_cena_pradu
    zysk_brutto_dyst = f_auto_rok * aktualna_cena_dyst
    total_zysk_siec_rok = zysk_brutto_prad + zysk_brutto_dyst
    
    # KOSZT USŁUGI PVaaS (Abonament zaindeksowany inflacją)
    koszt_pvaas_rok = aktualny_abonament
    
    # ZYSK NETTO KLIENTA W DANYM ROKU
    zysk_netto_rok = total_zysk_siec_rok - koszt_pvaas_rok
    skumulowany_zysk += zysk_netto_rok
    
    # Zapisanie danych
    dane_symulacji.append({
        "Rok": rok,
        "Produkcja PV (MWh)": f_prod_rok,
        "Cena Prądu (PLN/MWh)": aktualna_cena_pradu,
        "Oszczędność Sieciowa (PLN)": total_zysk_siec_rok,
        "Koszt PVaaS (PLN)": koszt_pvaas_rok,
        "Zysk Klienta (PLN)": zysk_netto_rok,
        "Skumulowany Zysk (PLN)": skumulowany_zysk
    })
    
    # Waloryzacja i Degradacja NA KOLEJNY rok
    aktualna_cena_pradu *= (1 + wzrost_cen_pradu)
    aktualna_cena_dyst *= (1 + wzrost_cen_pradu)
    aktualny_abonament *= (1 + wzrost_abonamentu)
    aktualna_roczna_produkcja_mwh *= (1 - degradacja_pv)
    aktualna_roczna_autokonsumpcja_mwh *= (1 - degradacja_pv)

df_sym_final = pd.DataFrame(dane_symulacji)

# ==============================================================================
# SEKCJA WYŚWIETLANIA WYNIKÓW (GUI)
# ==============================================================================

# --- PANEL METRYK ROK 1 ---
st.subheader("💡 Szczegółowy Bilans Profilu (Rok 1)")
c1, c2, c3 = st.columns(3)
c1.metric("Produkcja z PV", f"{real_y1_produkcja_mwh:,.0f} MWh/rok")
real_auto_perc = (real_y1_autokonsumpcja_mwh / real_y1_produkcja_mwh) * 100
c2.metric("Realna Autokonsumpcja", f"{real_y1_autokonsumpcja_mwh:,.0f} MWh/rok", f"{real_auto_perc:.1f}%")
c3.metric("Oszczędność Sieci Brutto", f"{zyski_sieciowe_brutto_y1:,.2f} PLN")

st.info(f"Oszczędność brutto w roku 1 obliczono co do złotówki na podstawie profilu godzinowego (DSO: {osd_choice}, Taryfa: {taryfa_choice}, Energia: {cena_mwh} PLN/MWh).")

# --- WYKRESY I SYMULACJA DŁUGOTERMINOWA ---
st.markdown("---")
st.subheader(f"📈 Symulacja Finansowa PVaaS na okres {okres_umowy} lat")
c_m1, c_m2, c_m3 = st.columns(3)
with c_m1: st.metric("Roczny abonament PVaaS (Rok 1)", f"{abonament_roczny_pln_y1:,.2f} PLN", "Stały / Indeksowany")
with c_m2: st.metric("Łączna Oszczędność z Sieci", f"{df_sym_final['Oszczędność Sieciowa (PLN)'].sum():,.2f} PLN", "Brutto")
with c_m3: st.metric("SKUMULOWANY ZYSK KLIENTA NETTO", f"{skumulowany_zysk:,.2f} PLN", "Zysk czysty")

# Wykres przepływów
fig = go.Figure()
fig.add_trace(go.Bar(x=df_sym_final["Rok"], y=df_sym_final["Oszczędność Sieciowa (PLN)"], name="Oszczędność Sieciowa (Zysk Brutto)", marker_color='#2ECC71'))
fig.add_trace(go.Bar(x=df_sym_final["Rok"], y=df_sym_final["Koszt PVaaS (PLN)"], name="Opłata PVaaS (Koszt)", marker_color='#E74C3C'))
fig.add_trace(go.Scatter(x=df_sym_final["Rok"], y=df_sym_final["Skumulowany Zysk (PLN)"], name="Skumulowany Zysk Netto", mode='lines+markers', line=dict(color='#3498DB', width=3), yaxis="y2"))
fig.update_layout(barmode='group', title="Zestawienie Zysków Brutto vs Opłata PVaaS", xaxis=dict(title="Rok", tickmode='linear'), yaxis=dict(title="Kwota roczna (PLN)"), yaxis2=dict(title="Zysk skumulowany (PLN)", overlaying='y', side='right'), legend=dict(x=0.01, y=0.99), template="plotly_white", hovermode="x unified")
st.plotly_chart(fig, use_container_width=True)

# --- TABELA DANYCH I POBIERANIE ---
st.markdown("---")
st.subheader("📋 Szczegółowa tabela symulacji PVaaS")

df_formatted = df_sym_final.copy()
for col in df_formatted.columns:
    if col == "Produkcja PV (MWh)": df_formatted[col] = df_formatted[col].apply(lambda x: f"{x:,.1f}".replace(",", " "))
    elif col != "Rok": df_formatted[col] = df_formatted[col].apply(lambda x: f"{x:,.2f} PLN".replace(",", " "))
st.dataframe(df_formatted.set_index("Rok"), use_container_width=True)

# EKSPORT DO EXCELA (Narzędzie sprzedażowe)
def create_excel_pvaas(df_sym, moc, prod_y1, auto_y1, sub_y1):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_sym.to_excel(writer, sheet_name='Symulacja_PVaaS', index=False)
        workbook = writer.book
        worksheet = writer.sheets['Symulacja_PVaaS']
        
        # Formaty
        header_fmt = workbook.add_format({'bold': True, 'bg_color': '#D7E4BC', 'border': 1})
        num_fmt = workbook.add_format({'num_format': '#,##0.00 "PLN"', 'border': 1})
        prod_fmt = workbook.add_format({'num_format': '#,##0.0 "MWh"', 'border': 1})
        
        # Formatowanie nagłówków
        for col_num, value in enumerate(df_sym.columns.values):
            worksheet.write(0, col_num, value, header_fmt)
        
        # Formatowanie danych
        for row in range(1, len(df_sym) + 1):
            worksheet.write(row, 0, df_sym.iloc[row-1, 0]) # Rok
            worksheet.write(row, 1, df_sym.iloc[row-1, 1], prod_fmt) # Produkcja
            worksheet.write(row, 2, df_sym.iloc[row-1, 2], num_fmt) # Cena
            worksheet.write(row, 3, df_sym.iloc[row-1, 3], num_fmt) # Oszczednosc
            worksheet.write(row, 4, df_sym.iloc[row-1, 4], num_fmt) # Koszt
            worksheet.write(row, 5, df_sym.iloc[row-1, 5], num_fmt) # Zysk
            worksheet.write(row, 6, df_sym.iloc[row-1, 6], num_fmt) # Skumulowany
        
        worksheet.set_column('A:A', 5)
        worksheet.set_column('B:G', 20)
        
        # Dodatkowy arkusz z parametrami (Z POPRAWIONĄ FUNKCJĄ)
        worksheet_p = workbook.add_worksheet('Założenia')
        par_data = [['Wielkość Instalacji', moc, 'kWp'],['Produkcja (Rok 1)', prod_y1, 'MWh'],['Autokonsumpcja (Rok 1)', auto_y1, 'MWh'],['Abonament roczny (Rok 1)', sub_y1, 'PLN']]
        for row, data in enumerate(par_data): worksheet_p.write(row, 0, data[0]); worksheet_p.write(row, 1, data[1]); worksheet_p.write(row, 2, data[2])
        
    return output.getvalue()

st.download_button(label="📥 Pobierz raport Excel (Pelna Symulacja)", data=create_excel_pvaas(df_sym_final, moc_pv, real_y1_produkcja_mwh, real_y1_autokonsumpcja_mwh, abonament_roczny_pln_y1), file_name=f"Raport_PVaaS_{moc_pv}kWp_{okres_umowy}lat.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
