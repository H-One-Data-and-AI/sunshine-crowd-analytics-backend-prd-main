import os
import base64
from dotenv import load_dotenv
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from Crypto.Util.Padding import pad

# --- Your existing setup code ---
load_dotenv()
base64_key = os.getenv("SECRET_KEY")
key = base64.b64decode(base64_key)

# --- Your existing encrypt_data function ---
def encrypt_data(plain_text: str) -> dict:
    iv = get_random_bytes(16)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    encrypted_bytes = cipher.encrypt(pad(plain_text.encode('utf-8'), AES.block_size))
    return {
        "data": base64.b64encode(encrypted_bytes).decode('utf-8'),
        "iv": base64.b64encode(iv).decode('utf-8')
    }

# --- CORRECTED STREAMING FUNCTION ---
def encrypt_stream_generator(data_generator):
    """
    Encrypts a data stream using AES-CTR and yields raw bytes.
    1. Yields the b64-encoded nonce + a newline.
    2. Yields the RAW encrypted binary data for the rest of the stream.
    This is the most efficient and correct way to stream encrypted data.
    """
    nonce = get_random_bytes(8)
    cipher = AES.new(key, AES.MODE_CTR, nonce=nonce)

    # 1. Yield the nonce, Base64 encoded for easy parsing, followed by a newline separator.
    yield base64.b64encode(nonce) + b'\n'

    # 2. Encrypt and yield each chunk as RAW BYTES.
    #    NO per-chunk Base64 encoding. NO extra newlines.
    for chunk in data_generator:
        encrypted_chunk = cipher.encrypt(chunk.encode('utf-8'))
        yield encrypted_chunk # <--- THIS IS THE ONLY CHANGE NEEDED