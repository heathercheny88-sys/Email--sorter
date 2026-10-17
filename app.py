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

# CHANNEL A: DIRECT FIXED INTERFACE FILE LOAD
if input_method == "📤 Upload CSV Spreadsheet File":
    uploaded_file = st.file_uploader("Upload your leads CSV file", type=["csv"])
    if uploaded_file is not None:
        raw_uploaded_df = pd.read_csv(uploaded_file)
        
        # Display the data preview to the user
        st.write("### 📊 Uploaded Spreadsheet Preview")
        st.dataframe(raw_uploaded_df.head(10), use_container_width=True)
        
        if st.button("🚀 Run Sorter and Generate Zip Package", type="primary", use_container_width=True):
            if len(raw_uploaded_df.columns) >= 3:
                df_to_process = pd.DataFrame()
                # FIXED MAPPING: Strict extraction by position coordinates (Col 0 = Name, Col 1 = Email, Col 2 = Role)
                df_to_process['Name'] = raw_uploaded_df.iloc[:, 0].astype(str).str.strip().str.title()
                df_to_process['Email'] = raw_uploaded_df.iloc[:, 1].astype(str).str.strip().str.lower()
                df_to_process['Role'] = raw_uploaded_df.iloc[:, 2].astype(str).str.strip().str.title()
            else:
                st.error("❌ The uploaded CSV file must contain at least 3 columns in this exact sequence order: [Name, Email, Role]")

# CHANNEL B: TEXT PROCESSING ENTRIES
else:
    st.caption("Paste entries (one per line). Sequential Order: Name - Email - Role (separated with dashes or commas)")
    pasted_text_wall = st.text_area(
        "Paste Text Data Block here:",
        value="John Doe - john.doe@mccormick.com - Sales Assistant\nJane Smith, jane@yahoo.com, Buyer\nHeather Chen - heather@bge.com - Procurement Officer",
        height=200
    )
    
    if st.button("🚀 Process Pasted Data and Generate Zip Package", type="primary", use_container_width=True):
        parsed_paste_records = []
        text_lines = pasted_text_wall.split("\n")
        
        for line in text_lines:
            if not line.strip():
                continue
            split_parts = re.split(r'[-–,|:]', line)
            
            if len(split_parts) >= 3:
                nm_clean = split_parts[0].strip().title()
                em_clean = split_parts[1].strip().lower()
                rl_clean = split_parts[2].strip().title()
                
                if "@" in em_clean:
                    parsed_paste_records.append({
                        "Name": nm_clean,
                        "Email": em_clean,
                        "Role": rl_clean
                    })
            elif len(split_parts) == 2:
                nm_clean = split_parts[0].strip().title()
                em_clean = split_parts[1].strip().lower()
                if "@" in em_clean:
                    parsed_paste_records.append({
                        "Name": nm_clean,
                        "Email": em_clean,
                        "Role": "Procurement Professional"
                    })
                    
        if parsed_paste_records:
            df_to_process = pd.DataFrame(parsed_paste_records)
        else:
            st.error("❌ Could not parse line layouts. Ensure they fit the Name - Email - Role structure sequence.")
# ==========================================
# THREADED RESOLVER & STRUCTURAL OUTPUT PROCESSING CORE
# ==========================================
if not df_to_process.empty:
    df_to_process['Extracted_Domain'] = df_to_process['Email'].apply(extract_domain)
    unique_domains = df_to_process['Extracted_Domain'].dropna().unique()
    
    progress_bar = st.progress(0)
    st.write(f"Analyzing network hosting structures for {len(unique_domains)} domains...")
    
    domain_category_map = {}
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
            
            if not bucket_df.empty:
                # STRICT SEQUENCE: Locks columns structurally into exactly Name, Email, and Role 
                bucket_df = bucket_df[['Name', 'Email', 'Role']].drop_duplicates(subset=['Email'])
                csv_text = bucket_df.to_csv(index=False, encoding='utf-8')
                zip_file.writestr(f"{bucket_name}_leads.csv", csv_text)
                files_created += 1
                
    zip_buffer.seek(0)
    
    if files_created > 0:
        st.success(f"Sorting finished! Generated {files_created} separate CSV spreadsheets containing Name, Email, and Role columns.")
        
        st.download_button(
            label="📥 Download Sorted ZIP Package",
            data=zip_buffer,
            file_name="sorted_leads_package.zip",
            mime="application/zip",
            use_container_width=True
        )
    else:
        st.error("No entries matched the file parsing requirements.")
