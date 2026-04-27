import hmac
import hashlib
import os
import sys
from pathlib import Path

def main():
    if "MODEL_HMAC_KEY" not in os.environ:
        print("ERROR: MODEL_HMAC_KEY environment variable not set")
        sys.exit(1)
    
    if len(sys.argv) < 2:
        print("Usage: python ml/sign_model.py <model_path>")
        sys.exit(1)
        
    key = os.environ["MODEL_HMAC_KEY"].encode()
    p = Path(sys.argv[1])
    if not p.exists():
        print(f"ERROR: file not found: {p}")
        sys.exit(1)
        
    sig = hmac.new(key, p.read_bytes(), hashlib.sha256).hexdigest()
    sig_path = p.with_suffix(p.suffix + ".sig")
    sig_path.write_text(sig, encoding="utf-8")
    print(f"Signed: {p}")
    print(f"Signature saved to: {sig_path}")

if __name__ == "__main__":
    main()
