import streamlit as st
import pandas as pd
import dns.resolver
from concurrent.futures import ThreadPoolExecutor, as_completed
import io

st.set_page_config(page_title="Email Provider Sorter", layout="centered")

st.title("📦 Clean Email Provider Sorter")
st.write("Upload your spreadsheet to isolate providers into clean lists containing **only Names and Emails**.")

def extract_domain(email):
    if pd.isna(email) or not isinstance(email, str):
        return None
    email = email.strip()
    return email.split('@')[-1].lower() if '@' in email else email.lower()

def identify_email_host(domain):
    if not domain: 
        return "Invalid / Dead Domain"
    try:
        answers = dns.resolver.resolve(domain, 'MX')
        for rdata in answers:
            host = str(rdata.exchange).lower()
            if "outlook" in host or "protection.outlook" in host: 
                return "Microsoft 365"
            elif "google" in host or "aspmx" in host: 
                return "Google Workspace"
            elif "mimecast" in host: 
                return "Mimecast Gateway"
            elif "proofpoint" in host or "pphosted" in host: 
                return "Proofpoint Gateway"
            elif "comcast" in host or "businessclass" in host: 
                return "Comcast Business"
        return "Private / Custom Host"
    except:
        return "Invalid / Dead Domain"

# File Uploader
uploaded_file = st.file_uploader("Upload your leads CSV file", type=["csv"])

if uploaded_file is not None:
    df = pd.read_csv(uploaded_file)
    columns_list = list(df.columns)
    
    st.write("### 🔍 Select Your Spreadsheet Columns")
    
    # Let the user explicitly choose the columns so there is no guessing
    email_col = st.selectbox("Which column contains the EMAIL ADDRESSES?", options=columns_list)
    name_col = st.selectbox("Which column contains the NAMES?", options=columns_list)

    if st.button("🚀 Run Sorter and Generate Files"):
        # Make a secure working copy with only our target columns
        working_df = pd.DataFrame()
        working_df['Name'] = df[name_col].astype(str)
        working_df['Email'] = df[email_col].astype(str)
            
        # Scan unique domains
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
                
        working_df['Email_Ecosystem'] = working_df['Extracted_Domain'].map(lambda d: domain_category_map.get(d, "Invalid / Dead Domain"))
        
        st.success("Sorting finished! Click the buttons below to download your clean files:")
        st.write("---")

        # SEPARATE FILE SEGMENTATION & CLEAN DOWNLOAD LINKS
        sorting_buckets = {
            "Microsoft 365": "microsoft_leads.csv",
            "Google Workspace": "google_leads.csv",
            "Mimecast Gateway": "mimecast_high_security_leads.csv",
            "Proofpoint Gateway": "proofpoint_high_security_leads.csv",
            "Comcast Business": "comcast_leads.csv",
            "Private / Custom Host": "private_hosted_leads.csv",
            "Invalid / Dead Domain": "invalid_or_dead_emails.csv"
        }

        for bucket_name, filename in sorting_buckets.items():
            # Filter rows for this specific bucket
            bucket_df = working_df[working_df['Email_Ecosystem'] == bucket_name].copy()
            
            # Keep ONLY the final Name and Email columns
            bucket_df = bucket_df[['Name', 'Email']]
            
            if not bucket_df.empty:
                # Convert dataframe to clean CSV bytes
                csv_buffer = io.BytesIO()
                bucket_df.to_csv(csv_buffer, index=False, encoding='utf-8')
                csv_buffer.seek(0)
                
                # Render separate download row
                st.download_button(
                    label=f"📥 Download Only {bucket_name} ({len(bucket_df)} leads)",
                    data=csv_buffer,
                    file_name=filename,
                    mime="text/csv",
                    key=filename
                )
