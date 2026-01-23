import requests
import os
import time
import argparse
import sys
from tqdm import tqdm
from urllib.parse import urlparse

# Configuration
API_URL = "https://api.gofile.io"
WEBSITE_TOKEN = "4fd6sg89d7s6"

def get_guest_token(session):
    """Obtains a guest token from Gofile API."""
    try:
        response = session.post(f"{API_URL}/accounts")
        response.raise_for_status()
        data = response.json()
        if data["status"] == "ok":
            token = data["data"]["token"]
            # Set the cookie for future requests
            session.cookies.set("accountToken", token, domain=".gofile.io")
            return token
    except Exception as e:
        print(f"Error getting guest token: {e}")
    return None

def get_direct_link(session, code, token):
    """Retrieves the direct download link for a given Gofile code."""
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Website-Token": WEBSITE_TOKEN,
        "Referer": "https://gofile.io/",
        "Origin": "https://gofile.io"
    }
    try:
        response = session.get(f"{API_URL}/contents/{code}?wt={WEBSITE_TOKEN}", headers=headers)
        response.raise_for_status()
        data = response.json()
        
        if data["status"] == "ok":
            children = data["data"]["children"]
            # We assume the main file we want is one of the children. 
            # If there are multiple, this simple logic grabs the first one with a link.
            for child_id, child_data in children.items():
                if "link" in child_data:
                    return child_data["link"], child_data["name"]
    except Exception as e:
        print(f"Error getting link for code '{code}': {e}")
    return None, None

def download_file(session, url, output_path, token):
    """Downloads the file with a progress bar."""
    if os.path.exists(output_path):
        print(f"File '{output_path}' already exists. Skipping.")
        return

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://gofile.io/",
        "Cookie": f"accountToken={token}"
    }

    try:
        with session.get(url, stream=True, headers=headers) as r:
            r.raise_for_status()
            total_size = int(r.headers.get('content-length', 0))
            
            with open(output_path, 'wb') as f, tqdm(
                desc=os.path.basename(output_path),
                total=total_size,
                unit='iB',
                unit_scale=True,
                unit_divisor=1024,
            ) as bar:
                for chunk in r.iter_content(chunk_size=8192):
                    size = f.write(chunk)
                    bar.update(size)
    except Exception as e:
        print(f"Error downloading '{output_path}': {e}")
        # Remove partial file if download failed
        if os.path.exists(output_path):
            os.remove(output_path)

def process_url(session, url, output_dir, token):
    """Processes a single Gofile URL."""
    # Extract code from URL (e.g., https://gofile.io/d/CODE)
    parsed = urlparse(url)
    path_parts = parsed.path.split('/')
    code = path_parts[-1] if path_parts[-1] else path_parts[-2]
    
    if not code:
        print(f"Could not parse code from URL: {url}")
        return

    print(f"Processing code: {code}...")
    link, name = get_direct_link(session, code, token)
    
    if link and name:
        output_path = os.path.join(output_dir, name)
        print(f"Found file: {name}")
        download_file(session, link, output_path, token)
    else:
        print(f"Failed to find download link for {url}")

def main():
    parser = argparse.ArgumentParser(description="Bulk downloader for gofile.io links.")
    parser.add_argument("input_file", help="Path to text file containing gofile.io URLs (one per line)")
    parser.add_argument("--output-dir", "-o", default=".", help="Directory to save downloaded files")
    parser.add_argument("--delay", "-d", type=int, default=2, help="Delay in seconds between downloads to be polite")
    
    args = parser.parse_args()

    if not os.path.exists(args.input_file):
        print(f"Error: Input file '{args.input_file}' not found.")
        sys.exit(1)

    if not os.path.exists(args.output_dir):
        os.makedirs(args.output_dir)

    # Initialize session
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    })

    # Get Guest Token
    print("Authenticating as guest...")
    token = get_guest_token(session)
    if not token:
        print("Failed to obtain guest token. Exiting.")
        sys.exit(1)
    print("Authentication successful.")

    # Read URLs
    with open(args.input_file, 'r') as f:
        urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    print(f"Found {len(urls)} URLs to process.")

    for i, url in enumerate(urls):
        process_url(session, url, args.output_dir, token)
        if i < len(urls) - 1:
            time.sleep(args.delay)

    print("All tasks completed.")

if __name__ == "__main__":
    main()
