import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# --- KONFIGURACJA STRONY ---
st.set_page_config(page_title="Kalkulator PV as a Service", layout="wide")
st.title("☀️ Kalkulator Opłacalności: PV as a Service (Długoterminowy)")
st.markdown("Model biznesowy: **Czysty OPEX (0 PLN na start)** | Stała opłata abonamentowa z waloryzacją | Uwzględnia degradację PV")

# --- PANEL BOCZNY: PARAMETRY WEJŚCIOWE ---
st.sidebar.header("⚙️ Parametry Instalacji")
moc_pv = st.sidebar.number_input("Wielkość instalacji PV (kWp)", value=500.0, step=10.0)
uzysk = st.sidebar.number_input("Roczny uzysk (kWh z 1 kWp)", value=1000.0, step=10.0)
autokonsumpcja = st.sidebar.slider("Poziom autokonsumpcji (%)", min_value=10, max_value=100, value=80, step=5)
degradacja_pv = st.sidebar.number_input("Roczna degradacja paneli PV (%)", value=0.5, step=0.1) / 100

st.sidebar.header("💶 Parametry Finansowe (PVaaS)")
cena_pvaas_eur = st.sidebar.number_input("Cena usługi PVaaS (EUR/MWh)", value=65.0, step=1.0)
kurs_eur = st.sidebar.number_input("Kurs EUR/PLN", value=4.30, step=0.01)

st.sidebar.header("⚡ Ceny Energii z Sieci")
cena_pradu = st.sidebar.number_input("Obecna cena energii czynnej (PLN/MWh netto)", value=500.0, step=10.0)
cena_dystrybucji = st.sidebar.number_input("Obecna cena dystrybucji (PLN/MWh netto)", value=250.0, step=10.0)

st.sidebar.header("📈 Czas i Waloryzacja (Inflacja)")
okres_umowy = st.sidebar.selectbox("Okres symulacji (lata)", [10, 15, 20], index=1)
wzrost_cen_pradu = st.sidebar.number_input("Roczny wzrost cen prądu (%)", value=3.0, step=0.5) / 100
wzrost_cen_dyst = st.sidebar.number_input("Roczny wzrost cen dystrybucji (%)", value=3.0, step=0.5) / 100
wzrost_abonamentu = st.sidebar.number_input("Roczna waloryzacja abonamentu PVaaS (%)", value=2.0, step=0.5) / 100

# --- OBLICZENIA BAZOWE (ROK 1) ---
produkcja_roczna_mwh = (moc_pv * uzysk) / 1000

# Opłata za PVaaS w pierwszym roku (Abonament roczny wyliczony z EUR/MWh)
abonament_roczny_pln = produkcja_roczna_mwh * cena_pvaas_eur * kurs_eur

# --- SYMULACJA W CZASIE ---
dane_lata = []
skumulowane_oszczednosci = 0.0

aktualna_cena_pradu = cena_pradu
aktualna_cena_dyst = cena_dystrybucji
aktualny_abonament = abonament_roczny_pln
aktualna_produkcja_mwh = produkcja_roczna_mwh  # Startujemy od produkcji w roku 1

for rok in range(1, okres_umowy + 1):
    # Wyliczamy ile z wyprodukowanej w TYM ROKU energii idzie na autokonsumpcję
    energia_autokonsumpcja_mwh = aktualna_produkcja_mwh * (autokonsumpcja / 100)
    
    # Oszczędności brutto (ile klient nie zapłaci do zakładu energetycznego dzięki PV)
    oszczednosc_na_pradzie = energia_autokonsumpcja_mwh * aktualna_cena_pradu
    oszczednosc_na_dystrybucji = energia_autokonsumpcja_mwh * aktualna_cena_dyst
    calkowita_oszczednosc_siec = oszczednosc_na_pradzie + oszczednosc_na_dystrybucji
    
    # Zysk netto klienta (Oszczędności z sieci MINUS koszt abonamentu PVaaS)
    zysk_netto_rok = calkowita_oszczednosc_siec - aktualny_abonament
    skumulowane_oszczednosci += zysk_netto_rok
    
    # Zapisanie danych do tabeli (dodaliśmy kolumnę z produkcją)
    dane_lata.append({
        "Rok": rok,
        "Produkcja PV (MWh)": aktualna_produkcja_mwh,
        "Cena Prądu (PLN/MWh)": aktualna_cena_pradu,
        "Cena Dyst. (PLN/MWh)": aktualna_cena_dyst,
        "Oszczędność Sieciowa (PLN)": calkowita_oszczednosc_siec,
        "Koszt PVaaS (PLN)": aktualny_abonament,
        "Zysk Klienta w danym roku (PLN)": zysk_netto_rok,
        "Skumulowany Zysk (PLN)": skumulowane_oszczednosci
    })
    
    # Zmiany na kolejny rok (waloryzacja finansowa + fizyczna degradacja paneli)
    aktualna_cena_pradu *= (1 + wzrost_cen_pradu)
    aktualna_cena_dyst *= (1 + wzrost_cen_dyst)
    aktualny_abonament *= (1 + wzrost_abonamentu)
    aktualna_produkcja_mwh *= (1 - degradacja_pv)

# Tworzenie tabeli (DataFrame)
df_symulacja = pd.DataFrame(dane_lata)

# --- WYŚWIETLANIE WYNIKÓW ---
st.markdown("---")
st.subheader("💡 Podsumowanie Instalacji (Rok 1)")
col1, col2, col3, col4 = st.columns(4)
col1.metric("Produkcja z PV (Rok 1)", f"{produkcja_roczna_mwh:,.0f} MWh")
col2.metric("Energia zjedzona (Rok 1)", f"{produkcja_roczna_mwh * (autokonsumpcja / 100):,.0f} MWh")
col3.metric("Roczny abonament PVaaS", f"{abonament_roczny_pln:,.2f} PLN")
col4.metric(f"Skumulowany Zysk (po {okres_umowy} latach)", f"{skumulowane_oszczednosci:,.2f} PLN", "Na czysto")

# --- WYKRESY ---
st.markdown("---")
st.subheader(f"📊 Przepływy pieniężne przez {okres_umowy} lat")

fig = go.Figure()

# Słupek Oszczędności (na zielono)
fig.add_trace(go.Bar(
    x=df_symulacja["Rok"], 
    y=df_symulacja["Oszczędność Sieciowa (PLN)"], 
    name="Oszczędność na prądzie z sieci (Zysk)", 
    marker_color='#2ECC71'
))

# Słupek Kosztu PVaaS (na czerwono)
fig.add_trace(go.Bar(
    x=df_symulacja["Rok"], 
    y=df_symulacja["Koszt PVaaS (PLN)"], 
    name="Abonament PVaaS (Koszt)", 
    marker_color='#E74C3C'
))

# Linia zysku skumulowanego (na niebiesko)
fig.add_trace(go.Scatter(
    x=df_symulacja["Rok"], 
    y=df_symulacja["Skumulowany Zysk (PLN)"], 
    name="Skumulowany Zysk Klienta", 
    mode='lines+markers',
    line=dict(color='#3498DB', width=3),
    yaxis="y2"
))

# Konfiguracja osi i wyglądu
fig.update_layout(
    barmode='group',
    title="Zestawienie kosztów PVaaS vs Oszczędności z sieci",
    xaxis=dict(title="Rok", tickmode='linear'),
    yaxis=dict(title="Kwota (PLN)"),
    yaxis2=dict(title="Skumulowany Zysk (PLN)", overlaying='y', side='right'),
    legend=dict(x=0.01, y=0.99),
    template="plotly_white",
    hovermode="x unified"
)

st.plotly_chart(fig, use_container_width=True)

# --- TABELA DANYCH ---
st.markdown("---")
st.subheader("📋 Szczegółowa tabela symulacji")
# Formatowanie tabeli do ładnego widoku
df_wyswietlanie = df_symulacja.copy()
for col in df_wyswietlanie.columns:
    if col == "Produkcja PV (MWh)":
        df_wyswietlanie[col] = df_wyswietlanie[col].apply(lambda x: f"{x:,.2f}".replace(",", " "))
    elif col != "Rok":
        df_wyswietlanie[col] = df_wyswietlanie[col].apply(lambda x: f"{x:,.2f} PLN".replace(",", " "))

st.dataframe(df_wyswietlanie.set_index("Rok"), use_container_width=True)

st.markdown("---")
st.info("""
**Komentarz analityczny:**
Wykres pokazuje wyraźnie istotę waloryzacji. Mimo że panele naturalnie degradują (produkują co roku nieco mniej energii), ceny prądu z sieci rosną zazwyczaj szybciej. W efekcie każdego roku "nożyce" korzyści finansowych się rozszerzają, co przekłada się na potężny zysk skumulowany w długim terminie.
""")
