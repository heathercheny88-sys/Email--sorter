import streamlit as st
import pandas as pd
import dns.resolver
from concurrent.futures import ThreadPoolExecutor, as_completed
import io

st.set_page_config(page_title="Bulk Email Ecosystem Sorter", layout="centered")
st.title("📦 Bulk Email Ecosystem Sorter")
st.write("Upload a CSV file of emails to automatically sort them by their email hosting infrastructure.")

def extract_domain(email):
    if pd.isna(email) or not isinstance(email, str):
        return None
    email = email.strip()
    return email.split('@')[-1].lower() if '@' in email else email.lower()

def identify_email_host(domain):
    if not domain: return "Invalid / No Domain"
    try:
        answers = dns.resolver.resolve(domain, 'MX')
        for rdata in answers:
            host = str(rdata.exchange).lower()
            if "outlook" in host or "protection.outlook" in host: return "Microsoft 365"
            elif "google" in host or "aspmx" in host: return "Google Workspace"
            elif "mimecast" in host: return "Mimecast Secure Gateway"
            elif "proofpoint" in host or "pphosted" in host: return "Proofpoint Secure Gateway"
            elif "comcast" in host or "businessclass" in host: return "Comcast Business"
        return "Private Host / Custom Server"
    except:
        return "Invalid / Dead Domain"

uploaded_file = st.file_uploader("Choose your leads CSV file", type=["csv"])

if uploaded_file is not None:
    df = pd.read_csv(uploaded_file)
    
    # Try to find email column
    email_col = None
    for col in df.columns:
        if col.lower().strip() in ['email', 'emails', 'email address', 'mail', 'contact']:
            email_col = col
            break
    if email_col is None:
        email_col = df.columns[0]
        
    st.info(f"Using column '{email_col}' for email addresses.")
    
    if st.button("🚀 Start Sorting List"):
        df['Extracted_Domain'] = df[email_col].apply(extract_domain)
        unique_domains = df['Extracted_Domain'].dropna().unique()
        
        progress_bar = st.progress(0)
        st.write(f"Scanning {len(unique_domains)} unique domains...")
        
        domain_category_map = {}
        with ThreadPoolExecutor(max_workers=20) as executor:
            future_to_domain = {executor.submit(identify_email_host, dom): dom for dom in unique_domains}
            for i, future in enumerate(as_completed(future_to_domain)):
                dom = future_to_domain[future]
                domain_category_map[dom] = future.result()
                progress_bar.progress((i + 1) / len(unique_domains))
                
        df['Email_Ecosystem'] = df['Extracted_Domain'].map(lambda d: domain_category_map.get(d, "Invalid / No Domain"))
        df = df.drop(columns=['Extracted_Domain'])
        
        st.success("Sorting Complete!")
        
        # Display breakdown tally
        st.write("### 📊 Distribution Results")
        tally = df['Email_Ecosystem'].value_counts()
        st.dataframe(tally)
        
        # Create a single download file containing the new classification column
        towrite = io.BytesIO()
        df.to_csv(towrite, index=False, encoding='utf-8')
        towrite.seek(0)
        
        st.download_button(
            label="📥 Download Sorted Master CSV File",
            data=towrite,
            file_name="sorted_leads_report.csv",
            mime="text/csv"
        )
