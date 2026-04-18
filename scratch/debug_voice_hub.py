
import requests
import io

API_URL = "http://localhost:8005/api/audio/talk"
HEADERS = {"X-Benny-API-Key": "benny-mesh-2026-auth"}

# Create a tiny dummy wav file
def create_dummy_wav():
    return b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x44\xac\x00\x00\x01\x00\x08\x00data\x00\x00\x00\x00"

def test_talk():
    files = {
        'file': ('test.wav', create_dummy_wav(), 'audio/wav')
    }
    data = {
        'notebook_id': 'default',
        'workspace': 'default'
    }
    
    try:
        print(f"Sending request to {API_URL}...")
        resp = requests.post(API_URL, headers=HEADERS, files=files, data=data)
        print(f"Status Code: {resp.status_code}")
        print(f"Response: {resp.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_talk()
