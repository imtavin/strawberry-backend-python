import socket
import struct
import time
import errno
import threading
import queue
from typing import Optional
from utils.logger import server_logger, tcp_logger, udp_logger

# ======================
#  A) Servidor TCP p/ COMANDOS
# ======================
class TCPServerHandler:
    def __init__(self, config):
        self.config = config["server"]
        self.enabled = self.config.get("enabled", True)

        self.server = None
        self.conn = None
        self.addr = None
        self._last_log = {}

        if not self.enabled:
            tcp_logger.info("Servidor TCP desabilitado via configuração")
            return

        try:
            self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server.bind((self.config["host"], self.config["port"]))
            self.server.listen(1)
            
            tcp_logger.info(f"Servidor TCP aguardando conexão em {self.config['host']}:{self.config['port']}")

            # Aceita o primeiro cliente
            self.conn, self.addr = self.server.accept()
            tcp_logger.info(f"Cliente conectado: {self.addr[0]}:{self.addr[1]}")
            self.conn.setblocking(False)
            
        except Exception as e:
            tcp_logger.error(f"Erro ao inicializar servidor TCP: {e}")
            raise

    def _log_throttled(self, level, msg, key=None):
        """Log com throttling para evitar spam"""
        now = time.time()
        if key:
            last = self._last_log.get(key, 0)
            if now - last < 1.0:  # 1 segundo de throttling
                return
            self._last_log[key] = now
        
        if level == "info":
            tcp_logger.info(msg)
        elif level == "warn":
            tcp_logger.warning(msg)
        elif level == "error":
            tcp_logger.error(msg)
        elif level == "debug":
            tcp_logger.debug(msg)

    def poll_accept(self):
        if not self.enabled or not self.server or self.conn is not None:
            return False
            
        self.server.setblocking(False)
        try:
            conn, addr = self.server.accept()
            self.conn, self.addr = conn, addr
            self.conn.setblocking(False)
            tcp_logger.info(f"Cliente reconectado: {self.addr[0]}:{self.addr[1]}")
            return True
        except (BlockingIOError, InterruptedError):
            return False
        except OSError as e:
            self._log_throttled("warn", f"Falha ao aceitar conexão: {e}", key="accept_oserr")
            return False

    def receive_command(self):
        if not self.enabled or not self.conn:
            return None
            
        try:
            data = self.conn.recv(1024)
            if not data:
                tcp_logger.warning("Cliente fechou a conexão (EOF)")
                self.close_conn_only()
                return None
                
            cmd = data.decode(errors="ignore").strip()
            if cmd:
                self._log_throttled("info", f"Comando recebido: {cmd}", key="cmd_rx")
            return cmd or None
            
        except (BlockingIOError, InterruptedError):
            return None
        except ConnectionResetError as e:
            tcp_logger.warning(f"Conexão resetada pelo cliente: {e}")
            self.close_conn_only()
            return None
        except OSError as e:
            self._log_throttled("warn", f"Erro de socket: {e}", key="recv_oserr")
            self.close_conn_only()
            return None

    def close_conn_only(self):
        try:
            if self.conn:
                try:
                    self.conn.shutdown(socket.SHUT_RDWR)
                except Exception as e:
                    tcp_logger.debug(f"Erro no shutdown da conexão: {e}")
                self.conn.close()
        except Exception as e:
            tcp_logger.error(f"Erro ao fechar conexão: {e}")
        finally:
            tcp_logger.info("Conexão com cliente encerrada")
            self.conn = None
            self.addr = None

    def close(self):
        self.close_conn_only()
        try:
            if self.server:
                self.server.close()
                tcp_logger.info("Servidor TCP encerrado")
        except Exception as e:
            tcp_logger.error(f"Erro ao fechar servidor: {e}")
        finally:
            self.server = None
            
    def send_text(self, text: str):
        if not self.enabled or not self.conn:
            return False
            
        try:
            if not text.endswith("\n"):
                text = text + "\n"
            self.conn.sendall(text.encode("utf-8", errors="ignore"))
            tcp_logger.debug(f"Texto enviado para cliente: {text.strip()}")
            return True
        except Exception as e:
            tcp_logger.error(f"Falha ao enviar resposta: {e}")
            self.close_conn_only()
            return False


# ======================
#  B) Streamer UDP p/ FRAMES
# ======================
class UDPStreamer:
    def __init__(self, config):
        try:
            udp_cfg = config.get("udp", {})
            self.max_packet = udp_cfg.get("max_packet_size", 4096)
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.clients = set()
            self.running = True
            
            udp_logger.info(f"UDP Streamer inicializado | Max packet: {self.max_packet} bytes")
            
        except Exception as e:
            udp_logger.error(f"Erro ao inicializar UDP Streamer: {e}")
            raise

    def add_client(self, addr):
        if addr not in self.clients:
            self.clients.add(addr)
            udp_logger.info(f"Cliente UDP registrado: {addr[0]}:{addr[1]}")
        else:
            udp_logger.debug(f"Cliente UDP já registrado: {addr[0]}:{addr[1]}")

    def remove_client(self, addr):
        if addr in self.clients:
            self.clients.discard(addr)
            udp_logger.info(f"Cliente UDP removido: {addr[0]}:{addr[1]}")

    def send_frame(self, frame_bytes: bytes):
        if not self.clients:
            udp_logger.warning("Nenhum cliente UDP conectado. Frame descartado.")
            return
            
        if not frame_bytes:
            udp_logger.warning("Frame vazio. Nada para enviar.")
            return

        frame_id = int(time.time() * 1000) & 0xFFFFFFFF
        total_packets = (len(frame_bytes) + self.max_packet - 1) // self.max_packet
        
        udp_logger.debug(f"Enviando frame UDP: {len(frame_bytes)} bytes, {total_packets} pacotes")

        for client in list(self.clients):
            try:
                for i in range(total_packets):
                    chunk = frame_bytes[i*self.max_packet:(i+1)*self.max_packet]
                    header = struct.pack("!IHH", frame_id, total_packets, i)
                    self.sock.sendto(header + chunk, client)
            except Exception as e:
                udp_logger.error(f"Falha ao enviar para {client[0]}:{client[1]}: {e}")
                self.remove_client(client)

    def stop(self):
        self.running = False
        try:
            self.sock.close()
            udp_logger.info("UDP Streamer encerrado")
        except Exception as e:
            udp_logger.error(f"Erro ao fechar socket UDP: {e}")


# ======================
#  C) Servidor TCP p/ FRAMES JPEG
# ======================
class FrameSender:
    def __init__(self, conn: socket.socket, client_addr: tuple):
        self.conn = conn
        self.client_addr = client_addr
        self.conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.queue: "queue.Queue[bytes]" = queue.Queue(maxsize=1)
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._run, daemon=True, name=f"FrameSender-{client_addr}")
        self._t.start()
        
        server_logger.info(f"FrameSender iniciado para {client_addr[0]}:{client_addr[1]}")

    def send(self, jpeg_bytes: bytes) -> None:
        try:
            if self.queue.full():
                try:
                    self.queue.get_nowait()
                    server_logger.debug("Fila de frames cheia - descartando frame antigo")
                except queue.Empty:
                    pass
            self.queue.put_nowait(jpeg_bytes)
        except Exception as e:
            server_logger.debug(f"Erro ao enfileirar frame: {e}")

    def close(self):
        self._stop.set()
        try:
            self.conn.shutdown(socket.SHUT_RDWR)
        except Exception as e:
            server_logger.debug(f"Erro no shutdown do FrameSender: {e}")
        try:
            self.conn.close()
        except Exception as e:
            server_logger.debug(f"Erro ao fechar conexão FrameSender: {e}")
        
        server_logger.info(f"FrameSender encerrado para {self.client_addr[0]}:{self.client_addr[1]}")

    def _run(self):
        frames_sent = 0
        try:
            while not self._stop.is_set():
                try:
                    frame = self.queue.get(timeout=0.5)
                except queue.Empty:
                    continue
                    
                try:
                    header = struct.pack("!I", len(frame))
                    self.conn.sendall(header)
                    self.conn.sendall(frame)
                    frames_sent += 1
                    
                    if frames_sent % 100 == 0:
                        server_logger.debug(f"Frames enviados para {self.client_addr[0]}:{self.client_addr[1]}: {frames_sent}")
                        
                except (BrokenPipeError, ConnectionResetError, OSError) as e:
                    server_logger.warning(f"Erro ao enviar frame: {e}")
                    break
                    
        except Exception as e:
            server_logger.error(f"Erro no FrameSender: {e}")
        finally:
            server_logger.info(f"FrameSender finalizado - total de frames: {frames_sent}")
            self.close()


class CameraServer:
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
            server_logger.info("CameraServer desabilitado via configuração")
            return
            
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((self.host, self.port))
            s.listen(1)
            self._sock = s
            self._accept_th = threading.Thread(target=self._accept_loop, daemon=True, name="CameraServer-Accept")
            self._accept_th.start()
            
            server_logger.info(f"CameraServer ouvindo em {self.host}:{self.port}")
            
        except Exception as e:
            server_logger.error(f"Erro ao iniciar CameraServer: {e}")
            raise

    def _accept_loop(self):
        server_logger.info("Loop de aceitação do CameraServer iniciado")
        
        while not self._stop.is_set():
            try:
                self._sock.settimeout(1.0)
                conn, addr = self._sock.accept()
                server_logger.info(f"Cliente conectado ao CameraServer: {addr[0]}:{addr[1]}")
                
                # Fecha sender anterior se existir
                if self._sender is not None:
                    try:
                        server_logger.info("Fechando conexão anterior do CameraServer")
                        self._sender.close()
                    except Exception as e:
                        server_logger.debug(f"Erro ao fechar sender anterior: {e}")
                
                self._sender = FrameSender(conn, addr)
                
            except socket.timeout:
                continue
            except OSError as e:
                if not self._stop.is_set():
                    server_logger.error(f"Erro no accept loop: {e}")
                break
            except Exception as e:
                server_logger.error(f"Erro inesperado no accept loop: {e}")
                break
                
        server_logger.info("Loop de aceitação do CameraServer finalizado")

    def broadcast(self, jpeg_bytes: bytes):
        if not self.enabled:
            return
            
        if self._sender is not None:
            self._sender.send(jpeg_bytes)

    def stop(self):
        self._stop.set()
        server_logger.info("Parando CameraServer...")
        
        if self._sender is not None:
            self._sender.close()
            self._sender = None
            
        if self._sock is not None:
            try:
                self._sock.close()
                server_logger.info("Socket do CameraServer fechado")
            except Exception as e:
                server_logger.error(f"Erro ao fechar socket: {e}")
                
        if self._accept_th and self._accept_th.is_alive():
            self._accept_th.join(timeout=2.0)
            if self._accept_th.is_alive():
                server_logger.warning("Thread de accept não finalizou corretamente")
            else:
                server_logger.info("Thread de accept finalizada")