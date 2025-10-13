import socket
import struct
import time
import threading
from typing import Set, Tuple, Optional, List
from utils.logger import udp_logger

class UDPStreamer:
    def __init__(self, config_manager):
        self.config = config_manager.get('udp', {})
        self.max_packet_size = self.config.get("max_packet_size", 4096)
        self.clients: Set[Tuple[str, int]] = set()
        self._clients_lock = threading.Lock()
        self.running = True
        
        # Estatísticas
        self.stats = {
            'frames_sent': 0,
            'packets_sent': 0,
            'clients_served': 0
        }
        
        self._initialize_socket()

    def _initialize_socket(self) -> None:
        """Inicializa o socket UDP com otimizações"""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            
            # Otimizações de performance
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)  # Buffer maior
            
            # Reutilizar endereço
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            udp_logger.info(
                f"UDP Streamer inicializado | "
                f"Max packet: {self.max_packet_size} bytes | "
                f"Buffer size: {self.sock.getsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF)}"
            )
            
        except Exception as e:
            udp_logger.error(f"Erro ao inicializar UDP Streamer: {e}")
            raise

    def add_client(self, addr: Tuple[str, int]) -> None:
        """Adiciona cliente de forma thread-safe"""
        with self._clients_lock:
            if addr not in self.clients:
                self.clients.add(addr)
                self.stats['clients_served'] += 1
                udp_logger.info(f"Cliente UDP registrado: {addr[0]}:{addr[1]}")
            else:
                udp_logger.debug(f"Cliente UDP já registrado: {addr[0]}:{addr[1]}")

    def remove_client(self, addr: Tuple[str, int]) -> None:
        """Remove cliente de forma thread-safe"""
        with self._clients_lock:
            if addr in self.clients:
                self.clients.remove(addr)
                udp_logger.info(f"Cliente UDP removido: {addr[0]}:{addr[1]}")

    def send_frame(self, frame_bytes: bytes) -> None:
        """Envia frame para todos os clientes de forma otimizada"""
        if not frame_bytes:
            udp_logger.warning("Frame vazio recebido para envio UDP")
            return

        # Obtém lista de clientes de forma thread-safe
        with self._clients_lock:
            current_clients = list(self.clients)
        
        if not current_clients:
            udp_logger.debug("Nenhum cliente UDP conectado")
            return

        try:
            frame_id = int(time.time() * 1000) & 0xFFFFFFFF
            total_packets = (len(frame_bytes) + self.max_packet_size - 1) // self.max_packet_size
            
            # Log a cada 100 frames para não poluir
            if self.stats['frames_sent'] % 100 == 0:
                udp_logger.debug(
                    f"Enviando frame UDP: {len(frame_bytes)} bytes, "
                    f"{total_packets} pacotes para {len(current_clients)} clientes"
                )

            # Prepara pacotes uma única vez (otimização)
            packets = []
            for i in range(total_packets):
                start_idx = i * self.max_packet_size
                end_idx = start_idx + self.max_packet_size
                chunk = frame_bytes[start_idx:end_idx]
                header = struct.pack("!IHH", frame_id, total_packets, i)
                packets.append(header + chunk)

            # Envia para todos os clientes
            failed_clients = []
            for client in current_clients:
                try:
                    for packet in packets:
                        self.sock.sendto(packet, client)
                        self.stats['packets_sent'] += 1
                        
                except Exception as e:
                    udp_logger.error(f"Falha ao enviar para {client[0]}:{client[1]}: {e}")
                    failed_clients.append(client)

            # Remove clientes com falha
            for failed_client in failed_clients:
                self.remove_client(failed_client)

            self.stats['frames_sent'] += 1
            
        except Exception as e:
            udp_logger.error(f"Erro no envio de frame UDP: {e}")

    def get_stats(self) -> dict:
        """Retorna estatísticas atuais"""
        with self._clients_lock:
            return {
                **self.stats,
                'active_clients': len(self.clients)
            }

    def stop(self) -> None:
        """Para o streamer UDP"""
        self.running = False
        try:
            with self._clients_lock:
                self.clients.clear()
                
            if self.sock:
                self.sock.close()
                
            udp_logger.info(
                f"UDP Streamer encerrado | "
                f"Estatísticas finais: {self.get_stats()}"
            )
            
        except Exception as e:
            udp_logger.error(f"Erro ao fechar UDP Streamer: {e}")