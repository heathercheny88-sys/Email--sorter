import streamlit as st
import pandas as pd
import dns.resolver
from concurrent.futures import ThreadPoolExecutor, as_completed
import io
import zipfile

st.set_page_config(page_title="Email Provider Sorter", layout="centered")

st.title("📦 Clean Email Provider Sorter")
st.write("Upload your spreadsheet to isolate providers into clean lists containing **only Names and Emails** downloaded in a clean package.")

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

# File Uploader
uploaded_file = st.file_uploader("Upload your leads CSV file", type=["csv"])

if uploaded_file is not None:
    df = pd.read_csv(uploaded_file)
    columns_list = list(df.columns)
    
    st.write("### 🔍 Select Your Spreadsheet Columns")
    email_col = st.selectbox("Which column contains the EMAIL ADDRESSES?", options=columns_list)
    name_col = st.selectbox("Which column contains the NAMES?", options=columns_list)

    if st.button("🚀 Run Sorter and Generate Zip Package"):
        # Build clean dataframe structure
        working_df = pd.DataFrame()
        working_df['Name'] = df[name_col].astype(str)
        working_df['Email'] = df[email_col].astype(str)
            
        working_df['Extracted_Domain'] = working_df['Email'].apply(extract_domain)
        unique_domains = working_df['Extracted_Domain'].dropna().unique()
        
        progress_bar = st.progress(0)
        st.write(f"Analyzing network hosting structures for {len(unique_domains)} domains...")
        
        domain_category_map = {}
        with ThreadPoolExecutor(max_workers=20) as executor:
            future_to_domain = {executor.submit(identify_email_host, dom): dom for dom in unique_domains}
            for i, future in enumerate(as_completed(future_to_domain)):
                dom = future_to_domain[future]
                domain_category_map[dom] = future.result()
                progress_bar.progress((i + 1) / len(unique_domains))
                
        working_df['Email_Ecosystem'] = working_df['Extracted_Domain'].map(lambda d: domain_category_map.get(d, "Invalid_or_Dead_Domains"))
        
        # 1. INITIALIZE IN-MEMORY ZIP BUFFER
        zip_buffer = io.BytesIO()
        
        # Categories we want to build
        buckets = [
            "Microsoft_365", "Google_Workspace", "Mimecast_Gateway", 
            "Proofpoint_Gateway", "Comcast_Business", "Private_or_Custom_Hosts", 
            "Invalid_or_Dead_Domains"
        ]
        
        files_created = 0
        
        # Open zip framework
        with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
            for bucket_name in buckets:
                # Filter down row data
                bucket_df = working_df[working_df['Email_Ecosystem'] == bucket_name].copy()
                # Isolate target constraints strictly to Name and Email
                bucket_df = bucket_df[['Name', 'Email']]
                
                # If rows match this provider, write it into the zip file
                if not bucket_df.empty:
                    csv_text = bucket_df.to_csv(index=False, encoding='utf-8')
                    zip_file.writestr(f"{bucket_name}_leads.csv", csv_text)
                    files_created += 1
        
        zip_buffer.seek(0)
        
        if files_created > 0:
            st.success(f"Sorting finished! Generated {files_created} separate CSV spreadsheets.")
            
            # 2. SINGLE STABLE DOWNLOAD PRIMITIVE
            st.download_button(
                label="📥 Download Sorted ZIP Package",
                data=zip_buffer,
                file_name="sorted_leads_package.zip",
                mime="application/zip"
            )
        else:
            st.error("No valid entries processed.")
