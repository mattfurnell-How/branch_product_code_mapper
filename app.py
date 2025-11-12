import streamlit as st 
import pandas as pd
import requests

# ----------------------------------
# CONFIGURATION
# ----------------------------------
USE_LOCAL_DATA = False  # Always False since you're using live APIs

PRODUCT_API_URL = "https://api.aplan.co.uk/api/producttypecodeitems"
BRANCH_API_URL = "https://api.aplan.co.uk/api/branches?includeNonLocalBranches=true&includeNonTradingBranches=true"

st.set_page_config(page_title="Branch & Product Code Mapper", layout="wide")

# ----------------------------------
# SIMPLE INLINE STYLING
# ----------------------------------
st.markdown("""
    <style>
        body {
            color: #244c5a;
            background-color: #cefdc9;
        }
        .stApp {
            background-color: #cefdc9;
        }
        section[data-testid="stSidebar"] {
            background-color: #244c5a;
        }
        section[data-testid="stSidebar"] * {
            color: #cefdc9 !important;
        }
        h1, h2, h3, h4, h5, h6, p, div, label, span {
            color: #244c5a;
        }
        /* Style Streamlit dataframes */
        .stDataFrame table {
            border: 1px solid #244c5a;
            border-radius: 8px;
        }
        .stDataFrame thead tr th {
            background-color: #244c5a !important;
            color: #cefdc9 !important;
            font-weight: bold;
        }
        .stDataFrame tbody tr td {
            color: #244c5a !important;
            background-color: #ffffff !important;
        }
        .stDataFrame tbody tr:nth-child(even) td {
            background-color: #f4fff3 !important;
        }
    </style>
""", unsafe_allow_html=True)

st.title("🏢 Branch & ProductCode Mapper")

# ----------------------------------
# FETCH DATA
# ----------------------------------
@st.cache_data(ttl=3600)
def fetch_data():
    try:
        products = requests.get(PRODUCT_API_URL).json()
        branches = requests.get(BRANCH_API_URL).json()

        df_products = pd.DataFrame(products)
        df_branches = pd.DataFrame(branches)

        # Rename columns to consistent format
        df_products.rename(columns={
            "code": "product_code",
            "detail": "product_name"
        }, inplace=True)

        df_branches.rename(columns={
            "name": "branch_name",
            "manager": "branch_manager",
            "postalAddress": "address",
            "openingTimes": "opening_hours",
            "productCodes": "product_codes"
        }, inplace=True)

        # Normalize product_codes to a list
        def normalize_codes(x):
            if isinstance(x, list):
                return x
            if isinstance(x, str):
                # comma separated string -> list
                return [c.strip() for c in x.split(",") if c.strip()]
            if pd.isna(x):
                return []
            # fallback: try to coerce to list
            try:
                return list(x)
            except Exception:
                return []

        if "product_codes" in df_branches.columns:
            df_branches["product_codes"] = df_branches["product_codes"].apply(normalize_codes)
        else:
            df_branches["product_codes"] = [[] for _ in range(len(df_branches))]

        return df_products, df_branches

    except Exception as e:
        st.error(f"Error fetching data: {e}")
        return pd.DataFrame(), pd.DataFrame()


df_products, df_branches = fetch_data()

if df_products.empty or df_branches.empty:
    st.error("Could not load data from one or both APIs.")
    st.stop()

# ----------------------------------
# Helper: format opening hours
# ----------------------------------
def format_opening_hours(opening_hours_raw):
    if not opening_hours_raw:
        return "N/A"
    if isinstance(opening_hours_raw, str):
        # in case API returns a string, just return it
        return opening_hours_raw
    if isinstance(opening_hours_raw, list):
        hours_list = []
        for entry in opening_hours_raw:
            if not isinstance(entry, dict):
                continue
            day = entry.get("day", "")
            open_h = entry.get("openingHour")
            open_m = entry.get("openingMinute", 0)
            close_h = entry.get("closingHour")
            close_m = entry.get("closingMinute", 0)
            if open_h is None or close_h is None:
                # if structure different, skip or show raw entry
                continue
            try:
                open_time = f"{int(open_h):02d}:{int(open_m or 0):02d}"
                close_time = f"{int(close_h):02d}:{int(close_m or 0):02d}"
                if day:
                    hours_list.append(f"{day}: {open_time}–{close_time}")
                else:
                    hours_list.append(f"{open_time}–{close_time}")
            except Exception:
                continue
        if hours_list:
            return ", ".join(hours_list)
        else:
            return "N/A"
    # default fallback
    return str(opening_hours_raw)

# ----------------------------------
# SEARCH MODE
# ----------------------------------
st.sidebar.header("Search Options")
search_mode = st.sidebar.radio(
    "Search by:",
    ["Product → Branches", "Branch → Products"]
)

search_input = st.sidebar.text_input("Enter search term:")

# ----------------------------------
# PRODUCT → BRANCH SEARCH
# ----------------------------------
if search_mode == "Product → Branches":
    st.subheader("🔍 Search by Product")

    if search_input:
        matched_products = df_products[
            df_products["product_name"].astype(str).str.contains(search_input, case=False, na=False)
            | df_products["product_code"].astype(str).str.contains(search_input, case=False, na=False)
        ]

        if not matched_products.empty:
            for _, product_row in matched_products.iterrows():
                product_code = product_row["product_code"]
                product_name = product_row["product_name"]

                st.markdown(f"### {product_name} (`{product_code}`)")

                # Find branches that include this product code
                def branch_has_code(codes):
                    try:
                        return product_code in codes
                    except Exception:
                        return False

                matched_branches = df_branches[df_branches["product_codes"].apply(branch_has_code)]

                if not matched_branches.empty:
                    st.write(f"**Allocated Branches:** {len(matched_branches)} found.")
                    # Add a nicely formatted opening hours column for display
                    display_branches = matched_branches.copy()
                    display_branches["opening_hours_display"] = display_branches["opening_hours"].apply(format_opening_hours)
                    st.dataframe(
                        display_branches[["branch_name", "branch_manager", "address", "opening_hours_display"]].rename(columns={"opening_hours_display": "opening_hours"}).reset_index(drop=True)
                    )
                else:
                    st.warning("No branches found for this product.")
        else:
            st.warning("No products found matching your search.")
    else:
        st.info("Enter a product name or code above to search.")

# ----------------------------------
# BRANCH → PRODUCT SEARCH
# ----------------------------------
elif search_mode == "Branch → Products":
    st.subheader("🏢 Search by Branch")

    if search_input:
        matched_branches = df_branches[
            df_branches["branch_name"].astype(str).str.contains(search_input, case=False, na=False)
        ]

        if not matched_branches.empty:
            for _, branch_row in matched_branches.iterrows():
                branch_name = branch_row["branch_name"]
                st.markdown(f"### {branch_name}")
                st.write(f"**Manager:** {branch_row.get('branch_manager', 'N/A')}")
                st.write(f"**Address:** {branch_row.get('address', 'N/A')}")
                st.write(f"**Opening Hours:** {format_opening_hours(branch_row.get('opening_hours'))}")

                branch_products = branch_row.get("product_codes") or []
                matched_products = df_products[df_products["product_code"].isin(branch_products)]

                if not matched_products.empty:
                    st.write(f"**Products allocated to this branch:** {len(matched_products)}")
                    st.dataframe(
                        matched_products[["product_code", "product_name"]].reset_index(drop=True)
                    )
                else:
                    st.warning("No products found for this branch.")
        else:
            st.warning("No branches found matching your search.")
    else:
        st.info("Enter a branch name above to search.")
