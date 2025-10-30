# backend/health_check.py
import socket
import time
import sys

def check_backend_ready(host='127.0.0.1', port=5000, timeout=30):
    """Verifica se o backend está pronto para aceitar conexões"""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(2)
                result = sock.connect_ex((host, port))
                if result == 0:
                    print("Backend está pronto")
                    return True
        except Exception:
            pass
        print("Aguardando backend...")
        time.sleep(2)
    print("Timeout aguardando backend")
    return False

if __name__ == "__main__":
    success = check_backend_ready()
    sys.exit(0 if success else 1)