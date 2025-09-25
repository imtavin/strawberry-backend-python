# backend/main.py
import json
import time
import threading
import os
import platform
import numpy as np
import cv2

from server_module import TCPServerHandler, UDPStreamer, CameraServer

def _load_tflite_interpreter(model_path: str):
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Modelo TFLite não encontrado: {model_path}")
    try:
        from tflite_runtime.interpreter import Interpreter
    except ImportError:
        from tensorflow.lite import Interpreter  # fallback se tflite_runtime não estiver instalado
    interpreter = Interpreter(model_path=model_path)
    interpreter.allocate_tensors()
    return interpreter

def _softmax(x: np.ndarray) -> np.ndarray:
    x = x.astype(np.float32)
    x = x - np.max(x)
    e = np.exp(x)
    s = e / np.sum(e)
    return s

def _preprocess_for_tflite(img_bgr: np.ndarray, input_details, norm: str = "uint8"):
    """
    Converte BGR->RGB, redimensiona para (H,W) do modelo e ajusta dtype.
    norm: "uint8" (sem normalização) ou "float32_0_1"
    """
    h, w, c = input_details[0]['shape'][1], input_details[0]['shape'][2], input_details[0]['shape'][3]
    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    resized = cv2.resize(rgb, (w, h), interpolation=cv2.INTER_LINEAR)

    if input_details[0]['dtype'] == np.uint8 and norm == "uint8":
        tensor = resized.astype(np.uint8)
    else:
        tensor = resized.astype(np.float32) / 255.0

    # adiciona batch
    tensor = np.expand_dims(tensor, axis=0)
    return tensor

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

    ml_cfg = CONFIG.get("ml", {})
    tflite_path = ml_cfg.get("model_path", "MorganaAI.tflite")
    labels = ml_cfg.get("labels", [])
    input_norm = ml_cfg.get("input_norm", "auto")  # "auto" | "uint8" | "float32_0_1"

    interpreter = None
    input_details = output_details = None
    try:
        interpreter = _load_tflite_interpreter(tflite_path)
        input_details = interpreter.get_input_details()
        output_details = interpreter.get_output_details()
        print(f"🧠 Modelo TFLite carregado: {tflite_path}")
        print(f"   Input: shape={input_details[0]['shape']}, dtype={input_details[0]['dtype']}")
        print(f"   Output: shape={output_details[0]['shape']}, dtype={output_details[0]['dtype']}")
    except Exception as e:
        print(f"⚠️ Falha ao carregar modelo TFLite: {e}. CAPTURE enviará apenas a foto salva.")

    # 3) Thread para capturar e enviar frames (vídeo)
    def stream_loop():
        target_fps = float(CONFIG["camera"].get("target_fps", 15))
        delay = 1.0 / max(1.0, target_fps)
        while True:
            try:
                _, frame_bytes = camera.capture_frame()
                if frame_bytes:
                    jpeg_server.broadcast(frame_bytes)      # TCP-JPEG (se habilitado)
                    if udp_streamer is not None:            # UDP (se habilitado)
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
                        print("ℹ️ Comando REGISTER_UDP recebido, mas o transporte UDP está desativado.")

                elif cmd in ("FOTO", "CAPTURE"):
                    # Salvar foto com o last_frame atual
                    camera.save_photo(os.getcwd())

                    # ============ NOVO: rodar inferência se modelo estiver carregado ============
                    if interpreter is not None and hasattr(camera, "last_frame") and camera.last_frame is not None:
                        try:
                            # Escolhe normalização
                            if input_norm == "auto":
                                norm_mode = "uint8" if input_details[0]['dtype'] == np.uint8 else "float32_0_1"
                            else:
                                norm_mode = input_norm

                            inp = _preprocess_for_tflite(camera.last_frame, input_details, norm=norm_mode)
                            interpreter.set_tensor(input_details[0]['index'], inp)
                            interpreter.invoke()
                            out = interpreter.get_tensor(output_details[0]['index'])  # assume [1, N] ou [N]
                            out = np.squeeze(out)

                            # Se saída não parece probabilidade, aplica softmax (comum em logits)
                            if np.max(out) > 1.0 or np.min(out) < 0.0:
                                probs = _softmax(out)
                            else:
                                probs = out.astype(np.float32)
                                s = np.sum(probs)
                                if s > 0:
                                    probs = probs / s

                            cls_idx = int(np.argmax(probs))
                            conf = float(probs[cls_idx])

                            if labels and 0 <= cls_idx < len(labels):
                                label = labels[cls_idx]
                            else:
                                label = f"class_{cls_idx}"

                            result = {"label": label, "confidence": round(conf * 100.0, 2)}
                            # Envia JSON para o frontend (ele já aceita JSON ou "LABEL:CONF")
                            tcp_server.send_text(json.dumps(result))

                        except Exception as e:
                            print(f"⚠️ Erro ao inferir TFLite: {e}")
                            tcp_server.send_text(json.dumps({"label": "erro_inferencia", "confidence": 0.0}))
                    else:
                        # Sem modelo carregado: ainda assim sinaliza captura
                        tcp_server.send_text(json.dumps({"label": "capturado", "confidence": 0.0}))

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
