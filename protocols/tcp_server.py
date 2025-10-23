import socket
import time
import json
import threading
from typing import Optional, Tuple, Dict, Any, Callable
from utils.logger import tcp_logger

class TCPServerHandler:
    def __init__(self, config_manager):
        self.config = config_manager
        self.host = self.config.get('server.host', '0.0.0.0')
        self.port = self.config.get('server.port', 5000)
        
        self.server: Optional[socket.socket] = None
        self.conn: Optional[socket.socket] = None
        self.addr: Optional[Tuple[str, int]] = None
        self.is_running = True
        self.command_handler: Optional[Callable] = None
        
        self._initialize_server()

    def set_command_handler(self, handler: Callable):
        """Define o handler de comandos"""
        self.command_handler = handler

    def _initialize_server(self) -> None:
        """Inicializa o servidor TCP"""
        try:
            self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server.settimeout(1.0)
            
            self.server.bind((self.host, self.port))
            self.server.listen(5)
            
            tcp_logger.info(f"Servidor TCP aguardando conexão em {self.host}:{self.port}")
            
            # Thread para aceitar conexões
            self.accept_thread = threading.Thread(target=self._accept_connections, daemon=True)
            self.accept_thread.start()
            
        except Exception as e:
            tcp_logger.error(f"Erro ao inicializar servidor TCP: {e}")
            raise

    def _accept_connections(self):
        """Aceita conexões em loop"""
        while self.is_running:
            try:
                conn, addr = self.server.accept()
                tcp_logger.info(f"Cliente conectado: {addr[0]}:{addr[1]}")
                
                # Fecha conexão anterior se existir
                if self.conn:
                    try:
                        self.conn.close()
                    except Exception as e:
                        tcp_logger.error(f"Erro ao fechar conexao TCP: {e}")
                
                self.conn = conn
                self.addr = addr
                
                # Envia informações iniciais
                self._send_raspberry_info()
                
            except socket.timeout:
                continue
            except Exception as e:
                if self.is_running:
                    tcp_logger.error(f"Erro aceitando conexão: {e}")

    def _send_raspberry_info(self):
        """Envia informações da Raspberry"""
        try:
            import socket as sock
            hostname = sock.gethostname()
            
            # Obtém IP local
            local_ip = "127.0.0.1"
            try:
                # Conecta a um IP externo para descobrir o IP local
                with sock.socket(sock.AF_INET, sock.SOCK_DGRAM) as s:
                    s.connect(("8.8.8.8", 80))
                    local_ip = s.getsockname()[0]
            except Exception as e:
                tcp_logger.error(f"Erro ao tentar descobrir IP: {e}")
            
            info = {
                "type": "raspberry_info",
                "hostname": hostname,
                "ip": local_ip,
                "private_ip": local_ip,
                "timestamp": time.time()
            }
            
            self.send_text(json.dumps(info))
            tcp_logger.info(f"Informações enviadas: {hostname} - {local_ip}")
            
        except Exception as e:
            tcp_logger.error(f"Erro enviando informações: {e}")

    def receive_command(self) -> Optional[str]:
        """Recebe comandos do cliente"""
        if not self.conn:
            return None
            
        try:
            self.conn.settimeout(0.5)
            data = self.conn.recv(4096)
            
            if data:
                command = data.decode('utf-8').strip()
                tcp_logger.debug(f"Comando recebido: {command}")
                return command
                
        except socket.timeout:
            pass
        except ConnectionResetError:
            tcp_logger.warning("Cliente desconectado")
            self.conn = None
        except Exception as e:
            tcp_logger.error(f"Erro recebendo comando: {e}")
            self.conn = None
            
        return None

    def send_text(self, text: str) -> bool:
        """Envia texto para o cliente"""
        if not self.conn:
            return False
            
        try:
            if not text.endswith("\n"):
                text += "\n"
                
            self.conn.sendall(text.encode('utf-8'))
            return True
            
        except Exception as e:
            tcp_logger.error(f"Erro enviando texto: {e}")
            self.conn = None
            return False

    def poll_accept(self) -> bool:
        """Verifica se há nova conexão (para compatibilidade)"""
        return self.conn is not None

    def close(self):
        """Fecha o servidor"""
        self.is_running = False
        if self.conn:
            self.conn.close()
        if self.server:
            self.server.close()
        tcp_logger.info("Servidor TCP fechado")