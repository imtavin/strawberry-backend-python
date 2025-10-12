import logging
import logging.handlers
import os
import sys
from datetime import datetime
from pathlib import Path

class CustomFormatter(logging.Formatter):
    """Formatação colorida para console e simples para arquivos"""
    
    # Cores ANSI
    grey = "\x1b[38;20m"
    green = "\x1b[32;20m"
    yellow = "\x1b[33;20m"
    red = "\x1b[31;20m"
    bold_red = "\x1b[31;1m"
    blue = "\x1b[34;20m"
    reset = "\x1b[0m"
    
    # Formatos
    format_str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    FORMATS = {
        logging.DEBUG: grey + format_str + reset,
        logging.INFO: green + format_str + reset,
        logging.WARNING: yellow + format_str + reset,
        logging.ERROR: red + format_str + reset,
        logging.CRITICAL: bold_red + format_str + reset
    }
    
    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt, datefmt='%Y-%m-%d %H:%M:%S')
        return formatter.format(record)

def setup_logger(name, log_level=logging.INFO, log_to_file=True):
    """Configura um logger com console e arquivo"""
    
    # Criar logger
    logger = logging.getLogger(name)
    logger.setLevel(log_level)
    
    # Evitar logs duplicados
    if logger.handlers:
        return logger
    
    # Formatter para arquivo (sem cores)
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Handler para console
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(CustomFormatter())
    logger.addHandler(console_handler)
    
    # Handler para arquivo
    if log_to_file:
        # Criar diretório de logs se não existir
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        # Arquivo com data
        log_file = log_dir / f"strawberry_ai_{datetime.now().strftime('%Y%m%d')}.log"
        
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)  # Arquivo guarda tudo
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
    
    return logger

# Loggers específicos para cada módulo
main_logger = setup_logger("strawberry.main")
camera_logger = setup_logger("strawberry.camera")
server_logger = setup_logger("strawberry.server")
ml_logger = setup_logger("strawberry.ml")
udp_logger = setup_logger("strawberry.udp")
tcp_logger = setup_logger("strawberry.tcp")
system_logger = setup_logger("strawberry.system")

def log_system_info():
    """Log de informações do sistema"""
    import platform
    import psutil
    
    main_logger.info("=" * 50)
    main_logger.info("🚀 Strawberry AI Iniciando")
    main_logger.info(f"📋 Sistema: {platform.system()} {platform.release()}")
    main_logger.info(f"🐍 Python: {platform.python_version()}")
    main_logger.info(f"💾 RAM: {psutil.virtual_memory().total / (1024**3):.1f} GB")
    main_logger.info(f"💿 Disk: {psutil.disk_usage('/').free / (1024**3):.1f} GB livre")
    main_logger.info("=" * 50)