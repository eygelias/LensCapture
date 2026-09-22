import requests
import base64

def upload_image(image_path: str) -> str:
    """
    Uploads an image to Imgur anonymously and returns the URL.
    Raises an exception on failure.
    """
    headers = {
        "Authorization": "Client-ID 546c25a59c58ad7"
    }
    
    with open(image_path, "rb") as file:
        image_data = file.read()
        
    payload = {
        "image": base64.b64encode(image_data).decode('utf-8')
    }
    
    response = requests.post("https://api.imgur.com/3/image", headers=headers, data=payload)
    
    if response.status_code == 200:
        data = response.json()
        return data["data"]["link"]
    else:
        raise Exception(f"Failed to upload to Imgur: {response.text}")
