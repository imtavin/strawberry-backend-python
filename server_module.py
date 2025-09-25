import socket
import struct
import time
import errno
import threading
import queue
from typing import Optional

LOG_THROTTLE_SEC = 1.0  # evita spam de logs repetidos em loops apertados
_HEADER = struct.Struct("!I")  # 4 bytes big-endian p/ tamanho de JPEG


# ======================
#  A) Servidor TCP p/ COMANDOS (mantém reconexão, não-bloqueante)
# ======================
class TCPServerHandler:
    def __init__(self, config):
        self.config = config["server"]
        self.enabled = self.config.get("enabled", True)

        self.server = None
        self.conn = None
        self.addr = None
        self._last_log = {}  # controle de throttling de logs

        if not self.enabled:
            self._log("info", "Servidor desabilitado via config.")
            return

        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind((self.config["host"], self.config["port"]))
        self.server.listen(1)
        self._log("info", f"Servidor TCP aguardando conexão em {self.config['host']}:{self.config['port']}...")

        # Aceita o primeiro cliente (bloqueante apenas aqui)
        self.conn, self.addr = self.server.accept()
        self._log("info", f"✅ Cliente conectado: {self.addr}")
        self.conn.setblocking(False)

    def _log(self, level, msg, key=None):
        now = time.time()
        if key:
            last = self._last_log.get(key, 0)
            if now - last < LOG_THROTTLE_SEC:
                return
            self._last_log[key] = now
        prefix = {"info": "ℹ️", "warn": "⚠️", "error": "❌", "debug": "🐞"}.get(level, "•")
        print(f"{prefix} {msg}")

    def poll_accept(self):
        if not self.enabled or not self.server or self.conn is not None:
            return False
        self.server.setblocking(False)
        try:
            conn, addr = self.server.accept()
            self.conn, self.addr = conn, addr
            self.conn.setblocking(False)
            self._log("info", f"✅ Cliente reconectado: {self.addr}")
            return True
        except (BlockingIOError, InterruptedError):
            return False
        except OSError as e:
            self._log("warn", f"Falha ao aceitar conexão: {e}", key="accept_oserr")
            return False

    def receive_command(self):
        if not self.enabled or not self.conn:
            return None
        try:
            data = self.conn.recv(1024)
            if not data:
                self._log("warn", "Cliente fechou a conexão (EOF) em receive_command().")
                self.close_conn_only()
                return None
            cmd = data.decode(errors="ignore").strip()
            if cmd:
                self._log("info", f"Comando recebido: {cmd}", key="cmd_rx")
            return cmd or None
        except (BlockingIOError, InterruptedError):
            return None
        except ConnectionResetError as e:
            self._log("warn", f"Conexão resetada em receive_command(): {e}")
            self.close_conn_only()
            return None
        except OSError as e:
            self._log("warn", f"OSError em receive_command(): {e}", key="recv_oserr")
            self.close_conn_only()
            return None

    def close_conn_only(self):
        try:
            if self.conn:
                try:
                    self.conn.shutdown(socket.SHUT_RDWR)
                except Exception:
                    pass
                self.conn.close()
        finally:
            self.conn = None
            self.addr = None
            self._log("info", "Conexão com cliente foi encerrada.")

    def close(self):
        self.close_conn_only()
        try:
            if self.server:
                self.server.close()
        finally:
            self.server = None
            self._log("info", "Servidor encerrado.")


# ======================
#  B) Streamer UDP p/ FRAMES (fragmentado)
# ======================
class UDPStreamer:
    """
    Streamer UDP de frames para múltiplos clientes.
    Backend envia frames para frontends que escutam a porta UDP.
    """

    def __init__(self, config):
        udp_cfg = config.get("udp", {})
        self.max_packet = udp_cfg.get("max_packet_size", 4096)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.clients = set()
        self.running = True
        print(f"🖧 UDP streamer iniciado (envio de frames)")

    def add_client(self, addr):
        """Registra o cliente para receber frames."""
        if addr not in self.clients:
            self.clients.add(addr)
            print(f"✅ Cliente UDP adicionado: {addr}")
        else:
            print(f"ℹ️ Cliente já registrado: {addr}")

    def remove_client(self, addr):
        """Remove cliente da lista."""
        if addr in self.clients:
            self.clients.discard(addr)
            print(f"❌ Cliente UDP removido: {addr}")

    def send_frame(self, frame_bytes: bytes):
        if not self.clients:
            print("⚠️ Nenhum cliente UDP conectado. Frame descartado.")
            return
        if not frame_bytes:
            print("⚠️ Frame vazio. Nada para enviar.")
            return

        frame_id = int(time.time() * 1000) & 0xFFFFFFFF  # ID simples baseado no tempo
        total_packets = (len(frame_bytes) + self.max_packet - 1) // self.max_packet

        for client in list(self.clients):
            try:
                for i in range(total_packets):
                    chunk = frame_bytes[i*self.max_packet:(i+1)*self.max_packet]
                    header = struct.pack("!IHH", frame_id, total_packets, i)
                    self.sock.sendto(header + chunk, client)
            except Exception as e:
                print(f"⚠️ Falha ao enviar para {client}: {e}")
                self.remove_client(client)

    def stop(self):
        """Encerra o streamer e fecha o socket."""
        self.running = False
        try:
            self.sock.close()
        except Exception:
            pass
        print("🛑 UDP streamer encerrado.")


# ======================
#  C) Servidor TCP p/ FRAMES JPEG (1 cliente por vez, fila size=1)
# ======================
class FrameSender:
    def __init__(self, conn: socket.socket):
        self.conn = conn
        self.conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.queue: "queue.Queue[bytes]" = queue.Queue(maxsize=1)
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._run, daemon=True)
        self._t.start()

    def send(self, jpeg_bytes: bytes) -> None:
        try:
            if self.queue.full():
                try:
                    self.queue.get_nowait()
                except queue.Empty:
                    pass
            self.queue.put_nowait(jpeg_bytes)
        except Exception:
            pass

    def close(self):
        self._stop.set()
        try:
            self.conn.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        try:
            self.conn.close()
        except Exception:
            pass

    def _run(self):
        try:
            while not self._stop.is_set():
                try:
                    frame = self.queue.get(timeout=0.5)
                except queue.Empty:
                    continue
                header = _HEADER.pack(len(frame))
                self.conn.sendall(header)
                self.conn.sendall(frame)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            self.close()


class CameraServer:
    """
    Aceita exatamente 1 cliente por vez. O backend chama .broadcast(jpeg_bytes).
    Config em config["frame_tcp"] -> {"enabled": bool, "host": str, "port": int}
    """
    def __init__(self, host: str = "127.0.0.1", port: int = 5050, enabled: bool = False):
        self.host = host
        self.port = port
        self.enabled = enabled
        self._sock: Optional[socket.socket] = None
        self._accept_th: Optional[threading.Thread] = None
        self._sender: Optional[FrameSender] = None
        self._stop = threading.Event()

    def start(self):
        if not self.enabled:
            print("[CameraServer] desabilitado.")
            return
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((self.host, self.port))
        s.listen(1)
        self._sock = s
        self._accept_th = threading.Thread(target=self._accept_loop, daemon=True)
        self._accept_th.start()
        print(f"[CameraServer] ouvindo em {self.host}:{self.port}")

    def _accept_loop(self):
        while not self._stop.is_set():
            try:
                self._sock.settimeout(1.0)
                conn, addr = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            print(f"[CameraServer] cliente conectado: {addr}")
            if self._sender is not None:
                try:
                    self._sender.close()
                except Exception:
                    pass
            self._sender = FrameSender(conn)

    def broadcast(self, jpeg_bytes: bytes):
        if not self.enabled:
            return
        s = self._sender
        if s is not None:
            s.send(jpeg_bytes)

    def stop(self):
        self._stop.set()
        if self._sender is not None:
            self._sender.close()
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
        if self._accept_th and self._accept_th.is_alive():
            self._accept_th.join(timeout=1.0)
