import socket
import struct
import time
import errno
import threading

LOG_THROTTLE_SEC = 1.0  # evita spam de logs repetidos em loops apertados


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

        # Cria socket do servidor
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind((self.config["host"], self.config["port"]))
        self.server.listen(1)
        self._log("info", f"Servidor TCP aguardando conexão em {self.config['host']}:{self.config['port']}...")

        # Aceita o primeiro cliente (bloqueante apenas aqui)
        self.conn, self.addr = self.server.accept()
        self._log("info", f"✅ Cliente conectado: {self.addr}")

        # Leitura não-bloqueante para não travar o loop principal
        self.conn.setblocking(False)

    # -------------------------------------------------------------------------
    # Logs com throttling
    # -------------------------------------------------------------------------
    def _log(self, level, msg, key=None):
        """
        level: "info" | "warn" | "error" | "debug"
        key: se fornecido, limita logs iguais por LOG_THROTTLE_SEC (anti-spam)
        """
        now = time.time()
        if key:
            last = self._last_log.get(key, 0)
            if now - last < LOG_THROTTLE_SEC:
                return
            self._last_log[key] = now

        prefix = {"info": "ℹ️", "warn": "⚠️", "error": "❌", "debug": "🐞"}.get(level, "•")
        print(f"{prefix} {msg}")

    # -------------------------------------------------------------------------
    # Aceitar reconexões sem bloquear
    # -------------------------------------------------------------------------
    def poll_accept(self):
        """
        Tenta aceitar um novo cliente (após desconexões) sem bloquear.
        Chame em cada iteração do loop principal.
        """
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
            # ninguém tentando conectar agora
            return False
        except OSError as e:
            self._log("warn", f"Falha ao aceitar conexão: {e}", key="accept_oserr")
            return False

    # -------------------------------------------------------------------------
    # Envio de frames (resiliente a EAGAIN/timeout)
    # -------------------------------------------------------------------------
    def send_frame(self, data):
        """
        Envia o frame serializado no formato: [L | payload], onde L = tamanho do payload.
        Retorna True se enviou, False se pulou (sem derrubar a conexão).
        """
        if not self.enabled:
            return False

        conn = self.conn  # referência local evita corrida caso self.conn mude
        if not conn:
            self._log("debug", "Nenhum cliente conectado (send_frame).", key="no_conn_send")
            return False

        header = struct.pack("L", len(data))
        payload = header + data

        # Damos um timeout curtinho *apenas durante o envio*.
        # Mantemos leitura não-bloqueante para receive_command().
        prev_timeout = None
        try:
            prev_timeout = conn.gettimeout()  # None (bloq.), 0.0 (non-block), >0 (timeout)
            conn.settimeout(0.02)  # ~20 ms — ajuste conforme necessário

            conn.sendall(payload)
            self._log("debug", f"Frame enviado ({len(data)} bytes).", key="frame_sent")
            return True

        except socket.timeout:
            # Sem espaço p/ enviar agora — dropa o frame e mantém a conexão
            self._log("warn", "send_frame timeout (dropping frame)", key="send_timeout")
            return False

        except OSError as e:
            if e.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                # Buffer de envio cheio — dropa o frame, sem fechar
                self._log("warn", "send_frame EAGAIN (dropping frame)", key="send_eagain")
                return False
            # Erros reais de conexão: fecha somente a conexão
            self._log("warn", f"OSError em send_frame(): {e}", key="send_oserr_fatal")
            self.close_conn_only()
            return False

        except (BrokenPipeError, ConnectionResetError) as e:
            self._log("warn", f"Cliente desconectou durante send_frame(): {e}")
            self.close_conn_only()
            return False

        finally:
            # Restaura o timeout anterior (mantendo comportamento de leitura)
            try:
                if prev_timeout is not None:
                    conn.settimeout(prev_timeout)
            except Exception:
                pass

    # -------------------------------------------------------------------------
    # Recebimento de comandos (não-bloqueante)
    # -------------------------------------------------------------------------
    def receive_command(self):
        """
        Lê comando do cliente **sem bloquear**.
        Retorna:
          - str com o comando (ex.: "CAPTURE" | "FOTO")
          - None se não há dados agora ou se não há conexão
        """
        if not self.enabled or not self.conn:
            return None

        try:
            data = self.conn.recv(1024)
            if not data:
                # EOF — cliente fechou a conexão de forma limpa
                self._log("warn", "Cliente fechou a conexão (EOF) em receive_command().")
                self.close_conn_only()
                return None

            cmd = data.decode(errors="ignore").strip()
            if cmd:
                self._log("info", f"Comando recebido: {cmd}", key="cmd_rx")
            return cmd or None

        except (BlockingIOError, InterruptedError):
            # sem dados disponíveis no momento
            return None
        except ConnectionResetError as e:
            self._log("warn", f"Conexão resetada em receive_command(): {e}")
            self.close_conn_only()
            return None
        except OSError as e:
            self._log("warn", f"OSError em receive_command(): {e}", key="recv_oserr")
            self.close_conn_only()
            return None

    # -------------------------------------------------------------------------
    # Fechamento / limpeza
    # -------------------------------------------------------------------------
    def close_conn_only(self):
        """Fecha apenas a conexão atual, mantendo o servidor para futuras reconexões."""
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
        """Fecha conexão e servidor (use ao encerrar a aplicação)."""
        self.close_conn_only()
        try:
            if self.server:
                self.server.close()
        finally:
            self.server = None
            self._log("info", "Servidor encerrado.")

class UDPStreamer:
    """
    Streamer UDP de frames para múltiplos clientes.
    Backend envia frames para frontends que escutam a porta UDP.
    """

    def __init__(self, config):
        udp_cfg = config.get("udp", {})
        self.max_packet = udp_cfg.get("max_packet_size", 4096)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Backend não precisa bindar — apenas envia
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

    def send_frame(self, frame_bytes):
        """Fragmenta e envia o frame para todos os clientes registrados."""
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
                    # Cabeçalho: frame_id (4 bytes), total (2 bytes), índice (2 bytes)
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



