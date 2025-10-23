import logging
import logging.handlers
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

class CustomFormatter(logging.Formatter):
    """Formatação colorida para console"""
    
    # Cores ANSI
    GREY = "\x1b[38;20m"
    GREEN = "\x1b[32;20m"
    YELLOW = "\x1b[33;20m"
    RED = "\x1b[31;20m"
    BOLD_RED = "\x1b[31;1m"
    BLUE = "\x1b[34;20m"
    RESET = "\x1b[0m"
    
    FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    FORMATS = {
        logging.DEBUG: GREY + FORMAT + RESET,
        logging.INFO: GREEN + FORMAT + RESET,
        logging.WARNING: YELLOW + FORMAT + RESET,
        logging.ERROR: RED + FORMAT + RESET,
        logging.CRITICAL: BOLD_RED + FORMAT + RESET
    }
    
    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt, datefmt='%Y-%m-%d %H:%M:%S')
        return formatter.format(record)

def setup_logger(
    name: str, 
    log_level: int = logging.INFO, 
    log_to_file: bool = True,
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5
) -> logging.Logger:
    """Configura logger com console e arquivo"""
    
    logger = logging.getLogger(name)
    
    # Evitar configuração duplicada
    if logger.handlers:
        return logger
        
    logger.setLevel(log_level)
    logger.propagate = False
    
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
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        log_file = log_dir / f"strawberry_ai_{datetime.now().strftime('%Y%m%d')}.log"
        
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
    
    return logger

# Loggers específicos para cada módulo
main_logger = setup_logger("strawberry.main")
camera_logger = setup_logger("strawberry.camera")
capture_logger = setup_logger("strawberry.capture")
server_logger = setup_logger("strawberry.server")
ml_logger = setup_logger("strawberry.ml")
udp_logger = setup_logger("strawberry.udp")
tcp_logger = setup_logger("strawberry.tcp")
system_logger = setup_logger("strawberry.system")

def log_system_info() -> None:
    """Log de informações do sistema de forma otimizada"""
    import platform
    import psutil
    
    try:
        system_info = {
            "Sistema": f"{platform.system()} {platform.release()}",
            "Python": platform.python_version(),
            "Processador": platform.processor() or "N/A",
            "RAM Total": f"{psutil.virtual_memory().total / (1024**3):.1f} GB",
            "RAM Livre": f"{psutil.virtual_memory().available / (1024**3):.1f} GB",
            "Disco Livre": f"{psutil.disk_usage('/').free / (1024**3):.1f} GB"
        }
        
        main_logger.info("=" * 60)
        main_logger.info("🚀 Strawberry AI Iniciando - Informações do Sistema")
        for key, value in system_info.items():
            main_logger.info(f"📋 {key}: {value}")
        main_logger.info("=" * 60)
        
    except Exception as e:
        main_logger.warning(f"Erro ao obter informações do sistema: {e}")