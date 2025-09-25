# backend/main.py
import json
import time
import threading
import os
import platform

from server_module import TCPServerHandler, UDPStreamer, CameraServer

# Escolha automática da câmera: Pi → picamera, senão OpenCV
def _load_camera_handler(CONFIG):
    cam_type = CONFIG.get("camera", {}).get("type")  # "picamera" | "opencv" | None
    if cam_type is None:
        cam_type = "picamera" if "raspberrypi" in platform.platform().lower() else "opencv"
    if cam_type.lower() == "picamera":
        from camera_module import CameraHandler
    else:
        from camera_webcam import CameraHandler
    return CameraHandler

def main():
    # 1) Carrega config
    with open("config.json", "r", encoding="utf-8") as f:
        CONFIG = json.load(f)

    # Detecta transporte desejado para o VÍDEO do frontend
    video_cfg = CONFIG.get("video", {})
    transport = (video_cfg.get("transport") or "udp").lower()
    use_udp = (transport == "udp")

    # 2) Inicializa câmera e servidores
    CameraHandler = _load_camera_handler(CONFIG)
    camera = CameraHandler(CONFIG)

    tcp_server = TCPServerHandler(CONFIG)

    # Só ligue o streamer UDP se o transporte for UDP
    udp_streamer = UDPStreamer(CONFIG) if use_udp else None

    frame_tcp_cfg = CONFIG.get("frame_tcp", {"enabled": False, "host": "127.0.0.1", "port": 5050})
    jpeg_server = CameraServer(
        host=frame_tcp_cfg.get("host", "127.0.0.1"),
        port=int(frame_tcp_cfg.get("port", 5050)),
        enabled=bool(frame_tcp_cfg.get("enabled", False)),
    )
    jpeg_server.start()

    # 3) Thread para capturar e enviar frames
    def stream_loop():
        target_fps = float(CONFIG["camera"].get("target_fps", 15))
        delay = 1.0 / max(1.0, target_fps)
        while True:
            try:
                _, frame_bytes = camera.capture_frame()
                if frame_bytes:
                    # Envia para TCP-JPEG (sempre que habilitado)
                    jpeg_server.broadcast(frame_bytes)
                    # Envia para UDP somente se ativo
                    if udp_streamer is not None:
                        udp_streamer.send_frame(frame_bytes)
                time.sleep(delay)
            except Exception as e:
                print(f"⚠️ Erro no envio de frame: {e}")
                time.sleep(0.05)

    threading.Thread(target=stream_loop, daemon=True).start()
    print(f"📷 Backend iniciado | TCP=Comandos | "
          f"{'UDP=Stream | ' if use_udp else ''}"
          f"TCP-JPEG={'Ativo' if frame_tcp_cfg.get('enabled', False) else 'Desligado'}")

    try:
        while True:
            # Aceita reconexões TCP
            tcp_server.poll_accept()

            # Lê comandos do frontend/cliente
            cmd = tcp_server.receive_command()
            if cmd is not None:
                if cmd.startswith("REGISTER_UDP:"):
                    if udp_streamer is not None:
                        try:
                            udp_port = int(cmd.split(":")[1])
                            client_ip = tcp_server.addr[0]
                            udp_streamer.add_client((client_ip, udp_port))
                        except Exception as e:
                            print(f"⚠️ Falha ao registrar cliente UDP: {e}")
                    else:
                        # Ignora com aviso discreto quando UDP está desativado
                        print("ℹ️ Comando REGISTER_UDP recebido, mas o transporte UDP está desativado.")
                elif cmd in ("FOTO", "CAPTURE"):
                    camera.save_photo(os.getcwd())
                else:
                    print(f"ℹ️ Comando TCP recebido: {cmd}")

            time.sleep(0.001)

    except KeyboardInterrupt:
        print("🛑 Encerrando backend...")
    finally:
        try:
            camera.release()
        except Exception:
            pass
        try:
            tcp_server.close()
        except Exception:
            pass
        try:
            if udp_streamer is not None:
                udp_streamer.stop()
        except Exception:
            pass
        try:
            jpeg_server.stop()
        except Exception:
            pass

if __name__ == "__main__":
    main()
