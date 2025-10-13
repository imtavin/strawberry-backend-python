"""
Script para diagnosticar problemas de streaming
"""

import sys
import os
import time
import threading
from pathlib import Path

# Adiciona o diretório atual ao path
sys.path.append(os.path.dirname(__file__))

from core.config import ConfigManager
from services.camera_service import CameraService
from protocols.frame_server import CameraServer
from utils.logger import setup_logger

# Logger específico para diagnóstico
diag_logger = setup_logger("strawberry.diagnose", log_to_file=False)

def test_camera_streaming():
    """Testa apenas o streaming da câmera"""
    diag_logger.info("🎥 TESTE DE CÂMERA E STREAMING")
    diag_logger.info("=" * 50)
    
    try:
        # Configuração
        config = ConfigManager()
        diag_logger.info("✅ ConfigManager carregado")
        
        # Câmera
        camera_service = CameraService(config)
        diag_logger.info("✅ CameraService inicializado")
        
        # Servidor de frames
        frame_server = CameraServer(
            host="127.0.0.1",
            port=5050, 
            enabled=True
        )
        frame_server.start()
        diag_logger.info("✅ CameraServer inicializado na porta 5050")
        
        # Estatísticas
        frame_count = 0
        last_stats_time = time.time()
        
        def frame_callback(frame_bytes):
            nonlocal frame_count
            frame_count += 1
            frame_server.broadcast(frame_bytes)
            
            # Log a cada segundo
            current_time = time.time()
            if current_time - last_stats_time >= 1.0:
                diag_logger.info(f"📊 Frames processados: {frame_count} | Último frame: {len(frame_bytes)} bytes")
                last_stats_time = current_time
        
        # Inicia streaming
        camera_service.start_streaming(frame_callback)
        diag_logger.info("✅ Streaming iniciado")
        
        # Aguarda por 10 segundos para teste
        diag_logger.info("⏰ Teste rodando por 10 segundos...")
        time.sleep(10)
        
        # Estatísticas finais
        diag_logger.info("=" * 50)
        diag_logger.info("📈 ESTATÍSTICAS FINAIS:")
        diag_logger.info(f"   Frames capturados: {frame_count}")
        diag_logger.info(f"   FPS aproximado: {frame_count / 10:.1f}")
        
        camera_stats = camera_service.camera_handler.get_stats() if camera_service.camera_handler else {}
        diag_logger.info(f"   Estatísticas da câmera: {camera_stats}")
        
        server_stats = frame_server.get_stats()
        diag_logger.info(f"   Estatísticas do servidor: {server_stats}")
        
    except Exception as e:
        diag_logger.error(f"❌ Erro no teste: {e}")
        import traceback
        diag_logger.error(traceback.format_exc())
    
    finally:
        diag_logger.info("🧹 Finalizando teste...")
        try:
            camera_service.stop()
            frame_server.stop()
        except:
            pass

def test_frame_sender_directly():
    """Testa o FrameSender diretamente"""
    diag_logger.info("\n🔧 TESTE DIRETO DO FRAMESENDER")
    diag_logger.info("=" * 50)
    
    import socket
    from protocols.frame_server import FrameSender
    
    # Cria um servidor de teste
    test_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    test_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    test_server.bind(('127.0.0.1', 5051))
    test_server.listen(1)
    
    diag_logger.info("Servidor de teste ouvindo na porta 5051")
    
    def client_handler():
        """Simula um cliente recebendo frames"""
        try:
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.connect(('127.0.0.1', 5051))
            diag_logger.info("✅ Cliente de teste conectado")
            
            frames_received = 0
            start_time = time.time()
            
            while frames_received < 5:  # Recebe 5 frames
                try:
                    # Lê header (4 bytes)
                    header = client_socket.recv(4)
                    if not header:
                        break
                    
                    frame_size = int.from_bytes(header, byteorder='big')
                    diag_logger.info(f"📦 Header recebido: {frame_size} bytes")
                    
                    # Lê frame
                    frame_data = b''
                    while len(frame_data) < frame_size:
                        chunk = client_socket.recv(min(4096, frame_size - len(frame_data)))
                        if not chunk:
                            break
                        frame_data += chunk
                    
                    if len(frame_data) == frame_size:
                        frames_received += 1
                        diag_logger.info(f"✅ Frame {frames_received} recebido: {len(frame_data)} bytes")
                    else:
                        diag_logger.error(f"❌ Frame incompleto: {len(frame_data)}/{frame_size} bytes")
                    
                except Exception as e:
                    diag_logger.error(f"Erro no cliente: {e}")
                    break
            
            elapsed = time.time() - start_time
            diag_logger.info(f"📈 Cliente recebeu {frames_received} frames em {elapsed:.2f}s")
            
            client_socket.close()
            
        except Exception as e:
            diag_logger.error(f"Erro no cliente de teste: {e}")
    
    # Inicia cliente em thread separada
    client_thread = threading.Thread(target=client_handler, daemon=True)
    client_thread.start()
    
    # Aceita conexão
    conn, addr = test_server.accept()
    diag_logger.info(f"✅ Conexão aceita de {addr}")
    
    # Cria FrameSender
    frame_sender = FrameSender(conn, addr)
    diag_logger.info("✅ FrameSender criado")
    
    # Envia frames de teste
    test_frame = b'test_frame_data_' * 100  # ~1.6KB
    
    for i in range(5):
        frame_sender.send(test_frame)
        diag_logger.info(f"📤 Frame de teste {i+1} enviado")
        time.sleep(0.1)
    
    # Aguarda um pouco
    time.sleep(1)
    
    # Estatísticas
    diag_logger.info(f"📊 Frames enviados: {frame_sender.frames_sent}")
    diag_logger.info(f"🔍 FrameSender ativo: {frame_sender.is_active()}")
    
    # Limpeza
    frame_sender.stop()
    test_server.close()
    diag_logger.info("✅ Teste direto finalizado")

if __name__ == "__main__":
    diag_logger.info("🔍 INICIANDO DIAGNÓSTICO DO STREAMING")
    
    # Teste 1: Streaming completo
    test_camera_streaming()
    
    # Teste 2: FrameSender direto
    test_frame_sender_directly()
    
    diag_logger.info("🎯 DIAGNÓSTICO CONCLUÍDO")