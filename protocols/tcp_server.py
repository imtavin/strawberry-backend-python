import socket
import time
import json
import errno
import netifaces
import requests
from typing import Optional, Tuple, Dict, Any
from utils.logger import tcp_logger

class TCPServerHandler:
    def __init__(self, config_manager):
        self.config = config_manager.get_network_config()
        self.enabled = self.config.get("enabled", True)

        self.server: Optional[socket.socket] = None
        self.conn: Optional[socket.socket] = None
        self.addr: Optional[Tuple[str, int]] = None
        self._last_log: Dict[str, float] = {}
        
        # Cache de informações da rede
        self._network_info_cache: Optional[Dict[str, Any]] = None
        self._cache_timeout = 300  # 5 minutos

        if not self.enabled:
            tcp_logger.info("Servidor TCP desabilitado via configuração")
            return

        self._initialize_server()

    def _initialize_server(self) -> None:
        """Inicializa o servidor TCP"""
        try:
            self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            
            # Configurações de performance
            self.server.settimeout(1.0)  # Timeout para aceitação
            
            host = self.config.get("host", "0.0.0.0")
            port = self.config.get("port", 5000)
            
            self.server.bind((host, port))
            self.server.listen(5)  # Aumentado para múltiplas conexões pendentes

            tcp_logger.info(f"Servidor TCP aguardando conexão em {host}:{port}")
            
            # Aceita conexão inicial em thread separada
            self._accept_connection()

        except Exception as e:
            tcp_logger.error(f"Erro ao inicializar servidor TCP: {e}")
            raise

    def _accept_connection(self) -> bool:
        """Aceita uma nova conexão de forma não-bloqueante"""
        if not self.enabled or not self.server or self.conn is not None:
            return False

        try:
            self.conn, self.addr = self.server.accept()
            
            # Otimizações de performance para a conexão
            self.conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)  # Disable Nagle
            self.conn.settimeout(0.5)  # Timeout para operações de socket
            
            tcp_logger.info(f"Cliente conectado: {self.addr[0]}:{self.addr[1]}")
            
            # Envia informações da Raspberry imediatamente
            self._send_raspberry_info()
            return True
            
        except socket.timeout:
            return False
        except BlockingIOError:
            return False
        except Exception as e:
            self._log_throttled("error", f"Erro ao aceitar conexão: {e}", "accept_error")
            return False

    def _get_network_info(self) -> Dict[str, Any]:
        """Obtém informações de rede com cache"""
        if (self._network_info_cache and 
            time.time() - self._network_info_cache.get('_timestamp', 0) < self._cache_timeout):
            return self._network_info_cache

        network_info = {
            "private_ip": self._get_private_ip(),
            "public_ip": self._get_public_ip(),
            "hostname": socket.gethostname(),
            "_timestamp": time.time()
        }
        
        self._network_info_cache = network_info
        return network_info

    def _get_private_ip(self) -> str:
        """Obtém o IP privado da Raspberry de forma otimizada"""
        try:
            # Prioridade: eth0 -> wlan0 -> fallback
            interfaces = ['eth0', 'wlan0']
            
            for interface in interfaces:
                try:
                    addrs = netifaces.ifaddresses(interface)
                    if netifaces.AF_INET in addrs:
                        ip_info = addrs[netifaces.AF_INET][0]
                        if ip_info.get('addr') and not ip_info['addr'].startswith('127.'):
                            return ip_info['addr']
                except (KeyError, ValueError):
                    continue
            
            # Fallbacks
            fallback_methods = [
                self._get_ip_from_socket,
                self._get_ip_from_hostname
            ]
            
            for method in fallback_methods:
                try:
                    ip = method()
                    if ip and not ip.startswith('127.'):
                        return ip
                except Exception:
                    continue
            
            return "Indisponível"
            
        except Exception as e:
            tcp_logger.error(f"Erro ao obter IP privado: {e}")
            return "Indisponível"

    def _get_ip_from_socket(self) -> str:
        """Obtém IP via conexão socket"""
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]

    def _get_ip_from_hostname(self) -> str:
        """Obtém IP via hostname"""
        return socket.gethostbyname(socket.gethostname())

    def _get_public_ip(self) -> str:
        """Obtém o IP público com timeout curto"""
        try:
            response = requests.get('https://api.ipify.org', timeout=3)
            if response.status_code == 200:
                return response.text.strip()
        except Exception as e:
            tcp_logger.debug(f"Erro ao obter IP público: {e}")
        return "Indisponível"

    def _send_raspberry_info(self) -> None:
        """Envia informações da Raspberry de forma otimizada"""
        if not self.conn:
            return

        try:
            network_info = self._get_network_info()
            raspberry_info = {
                "type": "raspberry_info",
                "private_ip": network_info["private_ip"],
                "public_ip": network_info["public_ip"],
                "ip": network_info["private_ip"],  # Para compatibilidade
                "hostname": network_info["hostname"],
                "timestamp": time.time()
            }
            
            message = json.dumps(raspberry_info) + "\n"
            self.conn.sendall(message.encode("utf-8"))
            
            tcp_logger.info(
                f"Informações enviadas - IP: {network_info['private_ip']}, "
                f"Hostname: {network_info['hostname']}"
            )
            
        except Exception as e:
            tcp_logger.error(f"Erro ao enviar informações: {e}")

    def _log_throttled(self, level: str, msg: str, key: Optional[str] = None) -> None:
        """Log com throttling para evitar spam"""
        now = time.time()
        if key and now - self._last_log.get(key, 0) < 2.0:  # 2 segundos
            return
            
        if key:
            self._last_log[key] = now
            
        getattr(tcp_logger, level)(msg)

    def poll_accept(self) -> bool:
        """Verifica e aceita novas conexões"""
        return self._accept_connection()

    def receive_command(self) -> Optional[str]:
        """Recebe comandos de forma não-bloqueante"""
        if not self.enabled or not self.conn:
            return None

        try:
            # Buffer maior para comandos complexos
            data = self.conn.recv(4096)
            if not data:
                tcp_logger.warning("Cliente desconectado (EOF)")
                self.close_conn_only()
                return None

            command = data.decode('utf-8', errors='ignore').strip()
            if command:
                self._log_throttled("debug", f"Comando recebido: {command}", "command_rx")
                return command
                
        except socket.timeout:
            pass  # Timeout é esperado em operações não-bloqueantes
        except BlockingIOError:
            pass  # Não há dados disponíveis
        except ConnectionResetError:
            tcp_logger.warning("Conexão resetada pelo cliente")
            self.close_conn_only()
        except Exception as e:
            self._log_throttled("error", f"Erro ao receber comando: {e}", "recv_error")
            self.close_conn_only()

        return None

    def send_text(self, text: str) -> bool:
        """Envia texto para o cliente de forma otimizada"""
        if not self.enabled or not self.conn:
            return False

        try:
            if not text.endswith("\n"):
                text += "\n"
                
            self.conn.sendall(text.encode("utf-8"))
            tcp_logger.debug(f"Texto enviado: {text.strip()}")
            return True
            
        except BrokenPipeError:
            tcp_logger.warning("Tentativa de envio para cliente desconectado")
            self.close_conn_only()
        except Exception as e:
            tcp_logger.error(f"Erro ao enviar texto: {e}")
            self.close_conn_only()
            
        return False

    def close_conn_only(self) -> None:
        """Fecha apenas a conexão do cliente"""
        if self.conn:
            try:
                self.conn.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass  # Socket já fechado
            
            try:
                self.conn.close()
            except Exception as e:
                tcp_logger.debug(f"Erro ao fechar conexão: {e}")
            finally:
                self.conn = None
                self.addr = None
                tcp_logger.info("Conexão com cliente fechada")

    def close(self) -> None:
        """Fecha completamente o servidor"""
        tcp_logger.info("Fechando servidor TCP...")
        self.close_conn_only()
        
        if self.server:
            try:
                self.server.close()
                tcp_logger.info("Servidor TCP fechado")
            except Exception as e:
                tcp_logger.error(f"Erro ao fechar servidor: {e}")
            finally:
                self.server = None