import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from datetime import datetime, timedelta
from gspread.utils import rowcol_to_a1
import numpy as np

st.set_page_config(page_title="Shelf Life Update", layout="wide")

# =========================
# AUTHENTICATION
# =========================
scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

credentials = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=scope
)

gc = gspread.authorize(credentials)
drive_service = build("drive", "v3", credentials=credentials)

# =========================
# CONSTANT
# =========================
LINK_Avail = "https://docs.google.com/spreadsheets/d/1VUtfWoE4RNOxs-1ehrv5Th3uwOs7lgZMUlcxIYLHf6M"
LINK_TFRIRVSD = "https://docs.google.com/spreadsheets/d/1SwG5lmr2sHDmPmsMOHNDRyt8JjT8D25-hSdIf08uQXI"
LINK_US = "https://docs.google.com/spreadsheets/d/1NJYxD3_txFaBMEsOzHwdXGDEOdSp4Zg1NakiRb2GE78"
LINK_B = "https://docs.google.com/spreadsheets/d/1ttznlAdgr4ilGIixeufgeqqJloLsEofVMR3lZrfK4kQ"
LINK_C = "https://docs.google.com/spreadsheets/d/1TJb60cY5Z0qeHJ4ZMKtWTMENS6lxCCmFOD0Rj2jQiXM"

today = datetime.today().date()

# =========================
# FUNCTIONS (kode kamu, mostly sama)
# =========================
def filter_avail_data(df):
    return df[
        (df["SUB CAT"].isin(["EXP", "KIT", "POL", "SEREXP"])) &
        (df["Expired"].notna()) &
        (df["Expired"] != "")
    ].reset_index(drop=True)

def shelf_life_status(days):
    if pd.isna(days):
        return "TIDAK ADA DATA SHELF LIFE"
    if days < 0:
        return "SUDAH EXPIRED"

    bins = [0,1,31,61,91,121,151,181,211,241,271,301,331,361]
    labels = [
        "0 AKAN EXPIRED",
        "01 BULAN KEDEPAN",
        "02 BULAN KEDEPAN",
        "03 BULAN KEDEPAN",
        "04 BULAN KEDEPAN",
        "05 BULAN KEDEPAN",
        "06 BULAN KEDEPAN",
        "07 BULAN KEDEPAN",
        "08 BULAN KEDEPAN",
        "09 BULAN KEDEPAN",
        "10 BULAN KEDEPAN",
        "11 BULAN KEDEPAN",
        "12 BULAN KEDEPAN",
        "LEBIH DR SETAHUN KEDEPAN"
    ]

    for i in range(len(bins)-1):
        if bins[i] <= days < bins[i+1]:
            return labels[i]
    return labels[-1]

def determine_allocation_status(df_linkA, df_linkC):
    df_linkA["Expired"] = pd.to_numeric(df_linkA["Expired"], errors="coerce")

    linkC_map = (
        df_linkC
        .dropna(subset=["Main PN"])
        .set_index("Main PN")["CEK"]
        .astype(str)
        .to_dict()
    )

    def check_status(row):
        if pd.notna(row["Expired"]) and row["Expired"] < 0:
            return "EXPIRED"
        return linkC_map.get(str(row["MAIN PN"]), "N/A")

    return df_linkA.apply(check_status, axis=1)

def process_data(df_link, QTY, df_linkC):
    df_filtered = filter_avail_data(df_link)
    df_filtered["Expired"] = pd.to_numeric(df_filtered["Expired"], errors="coerce")
    df_filtered["TGL EXP"] = df_filtered["Expired"].apply(
        lambda x: (today + timedelta(days=int(x))) if pd.notna(x) else ""
    )

    df_filtered["STATUS SHELF LIFE"] = df_filtered["Expired"].apply(shelf_life_status)
    df_filtered["STATUS ALLOCATION"] = determine_allocation_status(df_filtered, df_linkC)

    return pd.DataFrame({
        "MAIN PN": df_filtered["MAIN PN"],
        "REMARK STATION": df_filtered["REMARK STORE"],
        "SCRAP/BER/RAI": df_filtered["SCRAP/BER/RAI"],
        "GRB": df_filtered["GOODS_RCVD_BATCH"],
        "EXPIRED": df_filtered["Expired"],
        "TGL EXP": df_filtered["TGL EXP"].astype(str),
        "QTY": df_filtered[QTY],
        "SUB": df_filtered["SUB CAT"],
        "STATUS SHELF LIFE": df_filtered["STATUS SHELF LIFE"],
        "STATUS ALLOCATION": df_filtered["STATUS ALLOCATION"],
    })

# =========================
# UI
# =========================
st.title("📦 Shelf Life Auto Update")

if st.button("🚀 RUN UPDATE"):
    with st.spinner("Processing data..."):

        sheet_avail = gc.open_by_url(LINK_Avail).worksheet("AVAIL")
        sheet_inTF = gc.open_by_url(LINK_TFRIRVSD).worksheet("IN TF")
        sheet_pendingRI = gc.open_by_url(LINK_TFRIRVSD).worksheet("PENDING RI")
        sheet_RSVD = gc.open_by_url(LINK_TFRIRVSD).worksheet("RSVD")
        sheet_US = gc.open_by_url(LINK_US).worksheet("US")
        sheet_c = gc.open_by_url(LINK_C).worksheet("ALLOCATION")

        df_linkC = pd.DataFrame(sheet_c.get_all_records())

        def load_df(sheet, cols):
            values = sheet.get(cols)
            return pd.DataFrame(values[2:], columns=values[1])

        output_map = {
            "AVAIL": process_data(load_df(sheet_avail,"A1:P"), "QTY_AVAILABLE", df_linkC),
            "IN TF": process_data(load_df(sheet_inTF,"A1:P"), "QTY_IN_TRANSFER", df_linkC),
            "PENDING RI": process_data(load_df(sheet_pendingRI,"A1:P"), "QTY_PENDING_RI", df_linkC),
            "RSVD": process_data(load_df(sheet_RSVD,"A1:P"), "QTY_RESERVED", df_linkC),
            "US": process_data(load_df(sheet_US,"A1:O"), "QTY_US", df_linkC),
        }

        for sheet_name, df in output_map.items():
            sheet = gc.open_by_url(LINK_B).worksheet(sheet_name)
            sheet.clear()
            sheet.update("A1", [[f"LAST UPDATE: {today}"]])
            sheet.update("A2", [df.columns.tolist()])
            sheet.update("A3", df.values.tolist())

    st.success("✅ Update selesai!")
