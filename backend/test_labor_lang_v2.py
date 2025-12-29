import requests

def login():
    try:
        r = requests.post("http://localhost:8000/api/v1/auth/login", data={"username": "user@checkmate.ai", "password": "demo1234"})
        if r.status_code != 200:
             print(f"Login failed: {r.status_code} {r.text}")
             return None
        return r.json()['access_token']
    except Exception as e:
        print(f"Login connection failed: {e}")
        return None

try:
    token = login()
    if token:
        headers = {"Authorization": f"Bearer {token}"}
        url = "http://localhost:8000/api/v1/analyze/labor"
        files = {
            'contract_file': ('test_labor_lang.pdf', b'fake pdf content', 'application/pdf')
        }
        data = {
            'target_language': 'vi'
        }
        
        print(f"Sending request to {url} with target_language=vi")
        r = requests.post(url, files=files, data=data, headers=headers)
        print(f"Status: {r.status_code}")
        # print(f"Response: {r.text}") 
        
        if r.status_code == 200:
            res = r.json()
            if res.get('data'):
                lang = res['data']['summary']['language']
                print(f"Result Language: {lang}")
            else:
                print("No data returned.")
        else:
            print(r.text)

except Exception as e:
    print(e)
