import streamlit as st
import pandas as pd
import dns.resolver
from concurrent.futures import ThreadPoolExecutor, as_completed
import io

st.set_page_config(page_title="Email Provider Sorter", layout="centered")

st.title("📦 Clean Email Provider Sorter")
st.write("Upload your spreadsheet to isolate providers into clean lists containing **only Names and Emails**.")

# Initialize the website memory (Session State) so data doesn't erase on download clicks
if "sorted_data" not in st.session_state:
    st.session_state.sorted_data = None

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
    # Read the file once uploaded
    df = pd.read_csv(uploaded_file)
    columns_list = list(df.columns)
    
    st.write("### 🔍 Select Your Spreadsheet Columns")
    email_col = st.selectbox("Which column contains the EMAIL ADDRESSES?", options=columns_list)
    name_col = st.selectbox("Which column contains the NAMES?", options=columns_list)

    # When a new file is uploaded or columns change, clear the previous run from memory
    if st.button("🚀 Run Sorter and Generate Files"):
        st.session_state.sorted_data = None # Reset memory for new calculations
        
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
                
        working_df['Email_Ecosystem'] = working_df['Extracted_Domain'].map(lambda d: domain_category_map.get(d, "Invalid / Dead Domain"))
        
        # Keep ONLY Name and Email for output files
        working_df = working_df[['Name', 'Email', 'Email_Ecosystem']]
        
        # Store sorted results inside persistent app memory
        st.session_state.sorted_data = working_df
        st.success("Sorting finished! Download links compiled.")

    # 2. RUN RENDER BLOCK FROM PERSISTENT MEMORY
    if st.session_state.sorted_data is not None:
        st.write("---")
        st.write("### 📥 Download Clean Provider Files (Name & Email Only)")
        
        saved_df = st.session_state.sorted_data
        
        sorting_buckets = {
            "Microsoft 365": "microsoft_leads.csv",
            "Google Workspace": "google_leads.csv",
            "Mimecast Gateway": "mimecast_high_security_leads.csv",
            "Proofpoint Gateway": "proofpoint_high_security_leads.csv",
            "Comcast Business": "comcast_leads.csv",
            "Private / Custom Host": "private_hosted_leads.csv",
            "Invalid / Dead Domain": "invalid_or_dead_emails.csv"
        }

        # Loop through buckets and render persistent buttons
        for bucket_name, filename in sorting_buckets.items():
            bucket_df = saved_df[saved_df['Email_Ecosystem'] == bucket_name].copy()
            bucket_df = bucket_df[['Name', 'Email']]  # Strip everything except Name and Email
            
            if not bucket_df.empty:
                csv_buffer = io.BytesIO()
                bucket_df.to_csv(csv_buffer, index=False, encoding='utf-8')
                csv_buffer.seek(0)
                
                # These buttons will now remain visible on the screen during user interactions
                st.download_button(
                    label=f"📥 Download {bucket_name} List ({len(bucket_df)} leads)",
                    data=csv_buffer,
                    file_name=filename,
                    mime="text/csv",
                    key=f"btn_{filename}"
                )
