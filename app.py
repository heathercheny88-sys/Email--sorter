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
    
    # 1. DYNAMICALLY LOCATE CRITICAL COLUMNS
    email_col = None
    name_col = None
    
    for col in df.columns:
        col_clean = col.lower().strip()
        if col_clean in ['email', 'emails', 'email address', 'mail', 'contact']:
            email_col = col
        elif col_clean in ['name', 'full name', 'lead name', 'contact name', 'first name']:
            name_col = col

    # Fallbacks if columns aren't named explicitly
    if email_col is None:
        email_col = df.columns[0]
    if name_col is None:
        # If no explicit name column exists, look for any text column that isn't the email
        non_email_cols = [c for c in df.columns if c != email_col]
        name_col = non_email_cols[0] if non_email_cols else None

    st.info(f"Targeting Columns ➔ Name: **'{name_col}'** | Email: **'{email_col}'**")

    if st.button("🚀 Run Sorter"):
        # Make a secure working copy with only our target columns
        keep_cols = [name_col, email_col] if name_col else [email_col]
        working_df = df[keep_cols].copy()
        
        # Standardize our column names for the output files
        if name_col:
            working_df = working_df.rename(columns={name_col: 'Name', email_col: 'Email'})
        else:
            working_df = working_df.rename(columns={email_col: 'Email'})
            working_df['Name'] = "Unknown"  # Fallback if file has no names
            
        # Reorder columns to guarantee Name is first, Email is second
        working_df = working_df[['Name', 'Email']]

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
        
        st.success("Sorting finished! Download your targeted files below:")
        st.write("---")

        # 2. SEPARATE FILE SEGMENTATION & CLEAN DOWNLOAD LINKS
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
                    label=f"📥 Download {bucket_name} ({len(bucket_df)} leads)",
                    data=csv_buffer,
                    file_name=filename,
                    mime="text/csv",
                    key=filename
                )
