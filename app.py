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
st.set_page_config(page_title="Audyt PVaaS B2B", layout="wide")
st.title("⚡ Profesjonalny Audyt PV as a Service: Profil Klienta i Symulacja Długoterminowa")
st.markdown("Model: **Czysty OPEX (0 PLN na start)** | Realne dane strefowe | Waloryzacja Mocowa 10%")

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

st.sidebar.header("📈 3. Czas i Waloryzacja (Inflacja)")
okres_umowy = st.sidebar.selectbox("Okres symulacji (lata)", [10, 15, 20], index=1)
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

# PRECYZYJNE ROZBICIE STREF B22 / B23 (Godzina po godzinie)
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
    # Mnożymy przypisane godziny przez konkretne stawki OSD dla tej strefy
    dys = sum(df[df['Tmp_Strefa'] == s][col].sum() * (osd_data[osd_choice][taryfa_choice][s] + WSPOLNE_NETTO) for s in osd_data[osd_choice][taryfa_choice])
    return en, dys

e_p_y1, d_p_y1 = calc_strefowe('Pobór')         # Koszt przed PV (baza strefowa)
e_n_y1, d_n_y1 = calc_strefowe('Nowy_Pobór')    # Koszt po PV (baza strefowa)

# Dokładne oszczędności z 1 roku (Energia i Dystrybucja osobno)
oszczednosc_energia_y1 = e_p_y1 - e_n_y1
oszczednosc_dystrybucja_y1 = d_p_y1 - d_n_y1
zyski_sieciowe_energia_dyst_y1 = oszczednosc_energia_y1 + oszczednosc_dystrybucja_y1

# Opłata Mocowa 2026
df['Is_Szczyt_Mocowy'] = (df['Godzina'] >= 7) & (df['Godzina'] < 22) & df['Roboczy']
def get_moc_daily(sub_df, col):
    if not sub_df['Roboczy'].any(): return pd.Series({'Koszt': 0.0, 'Mnożnik': 0.17, 'L': 0.0})
    e_sz, e_d = sub_df[sub_df['Is_Szczyt_Mocowy']][col].sum(), sub_df[col].sum()
    if e_d < 0.1: return pd.Series({'Koszt': 0.0, 'Mnożnik': 0.17, 'L': 0.0})
    l_f = (e_sz / e_d) - 0.625
    mn = 0.17 if l_f <= 0.05 else (0.50 if l_f <= 0.10 else (0.83 if l_f <= 0.15 else
