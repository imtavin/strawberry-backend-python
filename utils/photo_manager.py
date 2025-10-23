"""
Gerenciador de fotos para salvar no formato: classificação-confiança-data_hora.jpg
"""
import os
import cv2
import json
from datetime import datetime
from typing import Optional, Dict, Any
from utils.logger import main_logger

class PhotoManager:
    def __init__(self, base_dir: str = "capture"):
        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        CAPTURES_DIR = os.path.join(BASE_DIR, "../" + base_dir)
        self.base_dir = os.path.abspath(CAPTURES_DIR)
        self._ensure_directory()
    
    def _ensure_directory(self):
        """Garante que o diretório de capturas existe"""
        try:
            os.makedirs(self.base_dir, exist_ok=True)
            main_logger.info(f"✅ Diretório de capturas verificado: {self.base_dir}")
        except Exception as e:
            main_logger.error(f"❌ Erro ao criar diretório {self.base_dir}: {e}")
            raise
    
    def save_photo_with_inference(
        self, 
        frame, 
        inference_result: Dict[str, Any],
        subfolder: Optional[str] = None
    ) -> bool:
        """
        Salva foto com base no resultado da inferência
        Formato: classificação-confiança-data_hora.jpg
        """
        try:
            # Extrai dados da inferência
            label = inference_result.get("label", "indeterminado")
            confidence = inference_result.get("confidence", 0.0)
            
            # Limpa label para nome de arquivo
            label_clean = self._sanitize_filename(label)
            
            # Formata confiança
            confidence_str = self._format_confidence(confidence)
            
            # Data/hora atual
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Monta nome do arquivo
            filename = f"{label_clean}-{confidence_str}-{timestamp}.jpg"
            
            # Diretório final
            if subfolder:
                final_dir = os.path.join(self.base_dir, subfolder)
                os.makedirs(final_dir, exist_ok=True)
            else:
                final_dir = self.base_dir
            
            full_path = os.path.join(final_dir, filename)
            
            # Salva a imagem
            success = cv2.imwrite(full_path, frame)
            
            if success:
                main_logger.info(f"📸 Foto salva: {filename}")
                
                # Salva metadados como JSON
                self._save_metadata(full_path, inference_result, label_clean, confidence_str)
                return True
            else:
                main_logger.error(f"❌ Falha ao salvar foto: {full_path}")
                return False
                
        except Exception as e:
            main_logger.error(f"❌ Erro ao salvar foto com inferência: {e}")
            return False
    
    def _sanitize_filename(self, text: str) -> str:
        """Remove caracteres inválidos para nome de arquivo"""
        import re
        # Substitui caracteres não alfanuméricos por underscore
        sanitized = re.sub(r'[^a-zA-Z0-9\u00C0-\u00FF]', '_', text)
        # Remove underscores múltiplos
        sanitized = re.sub(r'_+', '_', sanitized)
        # Remove underscores no início e fim
        sanitized = sanitized.strip('_')
        return sanitized if sanitized else "indeterminado"
    
    def _format_confidence(self, confidence) -> str:
        """Formata confiança para string padronizada"""
        if isinstance(confidence, float):
            return f"{confidence:.2f}"
        elif isinstance(confidence, (int, str)):
            try:
                confidence_float = float(confidence)
                return f"{confidence_float:.2f}"
            except:
                return "0.00"
        else:
            return "0.00"
    
    def _save_metadata(self, image_path: str, inference_result: Dict[str, Any], 
                      label_clean: str, confidence_str: str):
        """Salva metadados da inferência como arquivo JSON"""
        try:
            metadata = {
                "original_label": inference_result.get("label", "indeterminado"),
                "clean_label": label_clean,
                "confidence": inference_result.get("confidence", 0.0),
                "confidence_str": confidence_str,
                "timestamp": datetime.now().isoformat(),
                "image_file": os.path.basename(image_path),
                "inference_data": inference_result
            }
            
            json_path = os.path.splitext(image_path)[0] + ".json"
            
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
                
            main_logger.debug(f"Metadados salvos: {json_path}")
            
        except Exception as e:
            main_logger.warning(f"Erro ao salvar metadados: {e}")
    
    def list_photos(self, subfolder: Optional[str] = None) -> list:
        """Lista todas as fotos no diretório"""
        try:
            target_dir = os.path.join(self.base_dir, subfolder) if subfolder else self.base_dir
            photos = []
            
            for filename in os.listdir(target_dir):
                if filename.lower().endswith(('.jpg', '.jpeg', '.png')):
                    photos.append({
                        'filename': filename,
                        'path': os.path.join(target_dir, filename),
                        'created_time': os.path.getctime(os.path.join(target_dir, filename))
                    })
            
            return sorted(photos, key=lambda x: x['created_time'], reverse=True)
            
        except Exception as e:
            main_logger.error(f"Erro ao listar fotos: {e}")
            return []