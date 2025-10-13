import socket
import threading
import queue
import struct
import time
from typing import Optional, Tuple, List
from utils.logger import server_logger

class FrameSender:
    def __init__(self, conn: socket.socket, client_addr: Tuple[str, int]):
        self.conn = conn
        self.client_addr = client_addr
        self.conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.queue: queue.Queue[bytes] = queue.Queue(maxsize=2)  # Buffer pequeno
        self._stop_event = threading.Event()
        self.frames_sent = 0
        self.last_sent_time = time.time()  # Inicializa com tempo atual
        self._active = True  # Flag explícita de atividade
        
        # Thread de envio
        self._sender_thread = threading.Thread(
            target=self._run,
            daemon=True,
            name=f"FrameSender-{client_addr[0]}:{client_addr[1]}"
        )
        self._sender_thread.start()
        
        server_logger.info(f"FrameSender iniciado para {client_addr[0]}:{client_addr[1]}")

    def send(self, jpeg_bytes: bytes) -> None:
        """Enfileira frame para envio (não-bloqueante)"""
        if not self._active or self._stop_event.is_set():
            server_logger.debug("FrameSender inativo, ignorando frame")
            return

        try:
            # Tenta colocar na queue sem bloquear
            if self.queue.full():
                try:
                    discarded = self.queue.get_nowait()  # Descarta frame mais antigo
                    server_logger.debug(f"Queue cheia - descartado frame de {len(discarded)} bytes")
                except queue.Empty:
                    pass
            
            self.queue.put_nowait(jpeg_bytes)
            server_logger.debug(f"Frame enfileirado: {len(jpeg_bytes)} bytes")
            
        except Exception as e:
            server_logger.error(f"Erro ao enfileirar frame: {e}")
            self._active = False

    def _run(self) -> None:
        """Loop principal de envio de frames"""
        server_logger.info(f"Iniciando loop de envio para {self.client_addr}")
        
        try:
            while not self._stop_event.is_set() and self._active:
                try:
                    # Timeout mais curto para responder mais rápido ao stop
                    frame_data = self.queue.get(timeout=0.1)
                    
                    if frame_data:
                        success = self._send_frame(frame_data)
                        if success:
                            self.frames_sent += 1
                            self.last_sent_time = time.time()
                            
                            # Log informativo
                            if self.frames_sent == 1:
                                server_logger.info(f" Primeiro frame enviado para {self.client_addr}: {len(frame_data)} bytes")
                            elif self.frames_sent % 30 == 0:
                                server_logger.debug(f" Frames enviados para {self.client_addr}: {self.frames_sent}")
                        else:
                            server_logger.error(f"Falha no envio do frame para {self.client_addr}")
                            self._active = False
                            break
                            
                except queue.Empty:
                    continue  # Timeout normal
                    
        except Exception as e:
            server_logger.error(f"Erro crítico no FrameSender {self.client_addr}: {e}")
            self._active = False
        finally:
            server_logger.info(f"Loop de envio finalizado para {self.client_addr} - frames: {self.frames_sent}")
            self._cleanup()

    def _send_frame(self, frame_data: bytes) -> bool:
        """Envia um frame individual"""
        try:
            header = struct.pack("!I", len(frame_data))
            
            # Envia header e dados separadamente (como no código antigo que funcionava)
            self.conn.sendall(header)
            self.conn.sendall(frame_data)
            
            server_logger.debug(f"Frame enviado: {len(frame_data)} bytes para {self.client_addr}")
            return True
            
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError) as e:
            server_logger.warning(f"Cliente desconectado: {self.client_addr} - {e}")
            self._active = False
            return False
        except (socket.error, OSError) as e:
            server_logger.error(f"Erro de socket para {self.client_addr}: {e}")
            self._active = False
            return False
        except Exception as e:
            server_logger.error(f"Erro inesperado no envio para {self.client_addr}: {e}")
            self._active = False
            return False

    def stop(self) -> None:
        """Para o FrameSender"""
        if self._stop_event.is_set():
            return
            
        server_logger.info(f"Parando FrameSender para {self.client_addr}")
        self._stop_event.set()
        self._active = False
        
        try:
            self.conn.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass  # Socket já fechado
            
        try:
            self.conn.close()
        except Exception:
            pass
            
        server_logger.info(f"FrameSender finalizado para {self.client_addr} | Total frames: {self.frames_sent}")

    def _cleanup(self) -> None:
        """Limpeza final"""
        try:
            # Limpa queue completamente
            while not self.queue.empty():
                try:
                    self.queue.get_nowait()
                except queue.Empty:
                    break
        except Exception:
            pass

    def is_active(self) -> bool:
        """Verifica se o sender está ativo"""
        # Critérios mais flexíveis como no código antigo
        return (self._active and 
                not self._stop_event.is_set() and 
                self._sender_thread.is_alive() and
                (time.time() - self.last_sent_time < 10.0))  # Timeout de 10s em vez de 30s


class CameraServer:
    def __init__(self, host: str = "127.0.0.1", port: int = 5050, enabled: bool = False):
        self.host = host
        self.port = port
        self.enabled = enabled
        self._socket: Optional[socket.socket] = None
        self._accept_thread: Optional[threading.Thread] = None
        self._current_sender: Optional[FrameSender] = None
        self._stop_event = threading.Event()
        self._sender_lock = threading.Lock()
        
        # Estatísticas
        self.stats = {
            'connections_accepted': 0,
            'frames_broadcasted': 0,
            'last_broadcast_time': 0
        }

    def start(self) -> None:
        """Inicia o servidor de frames"""
        if not self.enabled:
            server_logger.info("CameraServer desabilitado via configuração")
            return

        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._socket.settimeout(1.0)
            
            self._socket.bind((self.host, self.port))
            self._socket.listen(1)
            
            # Thread de aceitação
            self._accept_thread = threading.Thread(
                target=self._accept_loop,
                daemon=True,
                name="CameraServer-Accept"
            )
            self._accept_thread.start()
            
            server_logger.info(f"CameraServer ouvindo em {self.host}:{self.port}")
            
        except Exception as e:
            server_logger.error(f"Erro ao iniciar CameraServer: {e}")
            raise

    def _accept_loop(self) -> None:
        """Loop de aceitação de conexões"""
        server_logger.info("Loop de aceitação do CameraServer iniciado")
        
        while not self._stop_event.is_set():
            try:
                conn, addr = self._socket.accept()
                server_logger.info(f" Cliente conectado ao CameraServer: {addr[0]}:{addr[1]}")
                
                # Gerencia sender anterior
                self._replace_sender(conn, addr)
                self.stats['connections_accepted'] += 1
                
            except socket.timeout:
                continue
            except OSError as e:
                if not self._stop_event.is_set():
                    server_logger.error(f"Erro no accept: {e}")
                break
            except Exception as e:
                server_logger.error(f"Erro inesperado no accept: {e}")
                break
                
        server_logger.info("Loop de aceitação do CameraServer finalizado")

    def _replace_sender(self, conn: socket.socket, addr: Tuple[str, int]) -> None:
        """Substitui o sender atual por um novo"""
        with self._sender_lock:
            # Para e limpa sender anterior
            old_sender = self._current_sender
            if old_sender:
                server_logger.info("Fechando conexão anterior do CameraServer")
                old_sender.stop()
                # Aguarda um pouco para garantir que parou
                time.sleep(0.1)
            
            # Cria novo sender
            self._current_sender = FrameSender(conn, addr)
            server_logger.info(f" Novo FrameSender criado para {addr}")

    def broadcast(self, jpeg_bytes: bytes) -> None:
        """Transmite frame para o cliente conectado"""
        if not self.enabled or not jpeg_bytes:
            return

        # Atualiza estatísticas
        self.stats['frames_broadcasted'] += 1
        self.stats['last_broadcast_time'] = time.time()

        # Log do primeiro frame
        if self.stats['frames_broadcasted'] == 1:
            server_logger.info(f"🎥 Primeiro frame para broadcast: {len(jpeg_bytes)} bytes")
        elif self.stats['frames_broadcasted'] % 50 == 0:
            server_logger.debug(f" Frames broadcasted: {self.stats['frames_broadcasted']}")

        with self._sender_lock:
            if self._current_sender and self._current_sender.is_active():
                try:
                    self._current_sender.send(jpeg_bytes)
                    server_logger.debug(f" Frame {self.stats['frames_broadcasted']} enviado para sender")
                except Exception as e:
                    server_logger.error(f" Erro ao enviar frame para sender: {e}")
                    self._current_sender = None
            else:
                # Sender inativo ou não existe
                if self._current_sender:
                    server_logger.warning("  FrameSender inativo, limpando...")
                    self._current_sender = None
                else:
                    server_logger.debug("  Nenhum FrameSender ativo disponível")

    def stop(self) -> None:
        """Para o servidor de forma limpa"""
        self._stop_event.set()
        server_logger.info("Parando CameraServer...")
        
        # Para sender atual
        with self._sender_lock:
            if self._current_sender:
                self._current_sender.stop()
                self._current_sender = None
        
        # Fecha socket
        if self._socket:
            try:
                self._socket.close()
                server_logger.info("Socket do CameraServer fechado")
            except Exception as e:
                server_logger.error(f"Erro ao fechar socket: {e}")
        
        # Aguarda thread de aceitação
        if self._accept_thread and self._accept_thread.is_alive():
            self._accept_thread.join(timeout=3.0)
            if self._accept_thread.is_alive():
                server_logger.warning("Thread de accept não finalizou corretamente")
            else:
                server_logger.info("Thread de accept finalizada")
                
        server_logger.info(f"CameraServer parado | Estatísticas: {self.stats}")

    def get_stats(self) -> dict:
        """Retorna estatísticas atuais"""
        with self._sender_lock:
            sender_active = self._current_sender is not None and self._current_sender.is_active()
            sender_frames = self._current_sender.frames_sent if self._current_sender else 0
            
        return {
            **self.stats,
            'sender_active': sender_active,
            'sender_frames': sender_frames,
            'sender_exists': self._current_sender is not None
        }