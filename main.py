import json
import time
import threading
import cv2
from camera_webcam import CameraHandler   # ou camera_module.CameraHandler para PiCamera
from server_module import TCPServerHandler, UDPStreamer

def main():
    # 1️⃣ Carrega config
    with open("config.json") as f:
        CONFIG = json.load(f)

    # 2️⃣ Inicializa câmera, TCP e UDP
    camera = CameraHandler(CONFIG)
    tcp_server = TCPServerHandler(CONFIG)
    udp_streamer = UDPStreamer(CONFIG)

    # Thread para capturar e enviar frames via UDP
    def udp_loop():
        while udp_streamer.running:
            try:
                _, frame_bytes = camera.capture_frame()
                udp_streamer.send_frame(frame_bytes)
                time.sleep(1 / CONFIG["camera"].get("target_fps", 15))
            except Exception as e:
                print(f"⚠️ Erro no envio UDP: {e}")

    threading.Thread(target=udp_loop, daemon=True).start()

    print("📷 Backend iniciado | TCP para comandos | UDP para stream")

    try:
        while True:
            # Aceita reconexões TCP
            tcp_server.poll_accept()

            # Lê comandos do frontend
            cmd = tcp_server.receive_command()
            
            if cmd is not None:
                if cmd.startswith("REGISTER_UDP:"):
                    try:
                        udp_port = int(cmd.split(":")[1])
                        client_ip = tcp_server.addr[0]
                        udp_streamer.add_client((client_ip, udp_port))
                        tcp_server._log("info", f"Cliente UDP registrado: {client_ip}:{udp_port}")
                    except Exception as e:
                        tcp_server._log("warn", f"Falha ao registrar cliente UDP: {e}")
                elif cmd in ("FOTO", "CAPTURE"):
                    camera.save_photo()
                else:
                    tcp_server._log("info", f"Comando TCP recebido: {cmd}")

            # Pequena pausa para reduzir CPU
            time.sleep(0.001)

    except KeyboardInterrupt:
        print("🛑 Encerrando backend...")

    finally:
        camera.release()
        tcp_server.close()
        udp_streamer.stop()

if __name__ == "__main__":
    main()