import streamlit as st
import pandas as pd
import dns.resolver
from concurrent.futures import ThreadPoolExecutor, as_completed
import io
import zipfile
import re

st.set_page_config(page_title="Email Provider Sorter", layout="centered")

st.title("📦 Clean Email Provider Sorter")
st.write("Isolate providers into clean files containing **Names, Emails, and Roles** down to a compressed ZIP package.")

def extract_domain(email):
    if pd.isna(email) or not isinstance(email, str):
        return None
    email = email.strip()
    return email.split('@')[-1].lower() if '@' in email else email.lower()

def identify_email_host(domain):
    if not domain: 
        return "Invalid_or_Dead_Domains"
    try:
        answers = dns.resolver.resolve(domain, 'MX')
        for rdata in answers:
            host = str(rdata.exchange).lower()
            if "outlook" in host or "protection.outlook" in host: 
                return "Microsoft_365"
            elif "google" in host or "aspmx" in host: 
                return "Google_Workspace"
            elif "mimecast" in host: 
                return "Mimecast_Gateway"
            elif "proofpoint" in host or "pphosted" in host: 
                return "Proofpoint_Gateway"
            elif "comcast" in host or "businessclass" in host: 
                return "Comcast_Business"
        return "Private_or_Custom_Hosts"
    except:
        return "Invalid_or_Dead_Domains"

# --- CHOOSE INPUT METHOD CHANNELS ---
input_method = st.radio("Select Sorter Input Method Option:", ["📤 Upload CSV Spreadsheet File", "📋 Copy-Paste Raw Text Wall"], horizontal=True)

df_to_process = pd.DataFrame()
email_field_name = ""
name_field_name = ""
role_field_name = ""

# CHANNEL A: OLD SPREADSHEET CHANNELS
if input_method == "📤 Upload CSV Spreadsheet File":
    uploaded_file = st.file_uploader("Upload your leads CSV file", type=["csv"])
    if uploaded_file is not None:
        raw_uploaded_df = pd.read_csv(uploaded_file)
        columns_list = list(raw_uploaded_df.columns)
        
        st.write("### 🔍 Select Your Spreadsheet Columns")
        col_drop_1, col_drop_2, col_drop_3 = st.columns(3)
        with col_drop_1:
            email_field_name = st.selectbox("Which column contains EMAILS?", options=columns_list, key="csv_em_col")
        with col_drop_2:
            name_field_name = st.selectbox("Which column contains NAMES?", options=columns_list, key="csv_nm_col")
        with col_drop_3:
            role_field_name = st.selectbox("Which column contains ROLES?", options=["None"] + columns_list, key="csv_rl_col")
            
        if st.button("🚀 Run Sorter and Generate Zip Package", type="primary", use_container_width=True):
            df_to_process = pd.DataFrame()
            df_to_process['Name'] = raw_uploaded_df[name_field_name].astype(str).str.strip().str.title()
            df_to_process['Email'] = raw_uploaded_df[email_field_name].astype(str).str.strip().str.lower()
            
            # Pull role string mapping if defined, else fallback to standard label
            if role_field_name != "None":
                df_to_process['Role'] = raw_uploaded_df[role_field_name].astype(str).str.strip().str.title()
            else:
                df_to_process['Role'] = "Procurement Professional"

# CHANNEL B: NEW COPY-PASTE PROCESSING MODULES
else:
    st.caption("Paste entries (one per line). Format: Name - Email - Role (separated with dashes or commas)")
    pasted_text_wall = st.text_area(
        "Paste Text Data Block here:",
        value="John Doe - john.doe@mccormick.com - Sales Assistant\nJane Smith, jane@yahoo.com, Buyer\nHeather Chen - heather@bge.com",
        height=200
    )
    fallback_role_val = st.text_input("Default Role placeholder if line entry is missing a role value:", value="Procurement Representative")
    
    if st.button("🚀 Process Pasted Data and Generate Zip Package", type="primary", use_container_width=True):
        parsed_paste_records = []
        text_lines = pasted_text_wall.split("\n")
        
        for line in text_lines:
            if not line.strip():
                continue
            split_parts = re.split(r'[-–,|:]', line)
            
            if len(split_parts) >= 2:
                nm_clean = split_parts[0].strip().title()
                em_clean = split_parts[1].strip().lower()
                rl_clean = split_parts[2].strip().title() if len(split_parts) >= 3 and split_parts[2].strip() else fallback_role_val.strip().title()
                
                if "@" in em_clean:
                    parsed_paste_records.append({
                        "Name": nm_clean,
                        "Email": em_clean,
                        "Role": rl_clean
                    })
                    
        if parsed_paste_records:
            df_to_process = pd.DataFrame(parsed_paste_records)
        else:
            st.error("No valid lines containing email handles could be isolated. Check separators.")
# ==========================================
# THREADED BACKEND RESOLVER & PROCESSING LOOP
# ==========================================
if not df_to_process.empty:
    df_to_process['Extracted_Domain'] = df_to_process['Email'].apply(extract_domain)
    unique_domains = df_to_process['Extracted_Domain'].dropna().unique()
    
    progress_bar = st.progress(0)
    st.write(f"Analyzing network hosting structures for {len(unique_domains)} domains...")
    
    domain_category_map = {}
    # Run parallel multi-threading resolver using your workers pool logic
    with ThreadPoolExecutor(max_workers=20) as executor:
        future_to_domain = {executor.submit(identify_email_host, dom): dom for dom in unique_domains}
        for i, future in enumerate(as_completed(future_to_domain)):
            dom = future_to_domain[future]
            domain_category_map[dom] = future.result()
            progress_bar.progress((i + 1) / len(unique_domains))
            
    df_to_process['Email_Ecosystem'] = df_to_process['Extracted_Domain'].map(lambda d: domain_category_map.get(d, "Invalid_or_Dead_Domains"))
    
    # INITIALIZE IN-MEMORY ZIP PACKAGE BUFFER
    zip_buffer = io.BytesIO()
    buckets = [
        "Microsoft_365", "Google_Workspace", "Mimecast_Gateway", 
        "Proofpoint_Gateway", "Comcast_Business", "Private_or_Custom_Hosts", 
        "Invalid_or_Dead_Domains"
    ]
    
    files_created = 0
    
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
        for bucket_name in buckets:
            bucket_df = df_to_process[df_to_process['Email_Ecosystem'] == bucket_name].copy()
            
            # CRITICAL FIX: Ensure the output table preserves all three columns inside the file package
            if not bucket_df.empty:
                bucket_df = bucket_df[['Name', 'Email', 'Role']].drop_duplicates(subset=['Email'])
                csv_text = bucket_df.to_csv(index=False, encoding='utf-8')
                zip_file.writestr(f"{bucket_name}_leads.csv", csv_text)
                files_created += 1
                
    zip_buffer.seek(0)
    
    if files_created > 0:
        st.success(f"Sorting finished! Generated {files_created} segmented CSV spreadsheets containing Name, Email, and Role metrics.")
        
        st.download_button(
            label="📥 Download Sorted ZIP Package",
            data=zip_buffer,
            file_name="sorted_leads_package.zip",
            mime="application/zip",
            use_container_width=True
        )
    else:
        st.error("No entries matched the file parsing requirements.")
