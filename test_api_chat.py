import requests
import json
import time
import sys

# Force UTF-8 for stdout just in case
sys.stdout.reconfigure(encoding='utf-8')

def test_rag_chat_endpoint():
    print("Testing Benny API /rag/chat endpoint...")
    
    url = "http://localhost:8005/api/rag/chat"
    
    payload = {
        "query": "Hello, simply reply with the word 'Working'.",
        "workspace": "default",
        "provider": "fastflowlm",
        "top_k": 1
    }
    
    print(f"Target: {url}")
    
    try:
        start_time = time.time()
        response = requests.post(
            url, 
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=60
        )
        duration = time.time() - start_time
        
        print(f"\nStatus Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("SUCCESS")
            # print(f"Full Response: {json.dumps(data, indent=2)}")
            
            if 'debug_response' in data:
                 print(f"Debug Response: {json.dumps(data['debug_response'], indent=2)}")

            if 'answer' in data:
                print(f"\nAnswer: {data['answer']}")
            else:
                print("Warning: 'answer' field missing in response")
                
        else:
            print(f"FAILED with status {response.status_code}")
            try:
                error_data = response.json()
                print(f"Error Details: {json.dumps(error_data, indent=2)}")
            except:
                print(f"Response Text: {response.text}")
                
    except requests.exceptions.ConnectionError:
        print("CONNECTION ERROR: Could not connect to localhost:8005.")
    except Exception as e:
        print(f"ERROR: {str(e)}")

if __name__ == "__main__":
    test_rag_chat_endpoint()
