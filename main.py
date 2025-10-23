#!/usr/bin/env python3
"""
Ponto de entrada principal da aplicação Strawberry AI - Backend CORRIGIDO
"""
import os
import sys
import time
import signal
import logging

# Configurar path para imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.app import StrawberryAIApp
from utils.logger import log_system_info

def signal_handler(signum, frame):
    """Handler para sinais de sistema"""
    logging.info(f"Recebido sinal {signum}, encerrando aplicação...")
    sys.exit(0)

def main():
    """Função principal"""
    try:
        # Registrar handlers de sinal
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Log informações do sistema
        log_system_info()
        
        # Criar e inicializar aplicação
        app = StrawberryAIApp()
        
        logging.info("Inicializando aplicação Strawberry AI...")
        
        if app.initialize():
            logging.info(" Aplicação inicializada com sucesso")
            app.run()
        else:
            logging.error(" Falha na inicialização da aplicação")
            sys.exit(1)
            
    except KeyboardInterrupt:
        logging.info("Aplicação interrompida pelo usuário")
    except Exception as e:
        logging.critical(f"Erro crítico na aplicação: {e}")
        import traceback
        logging.critical(traceback.format_exc())
        sys.exit(1)
    finally:
        logging.info("Aplicação encerrada")

if __name__ == "__main__":
    main()