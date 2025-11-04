#!/usr/bin/env python3
"""
TESTE MEGA ROBUSTO - PICAMERA2 RASPBERRY PI (VERSÃO CORRIGIDA)
Teste completo de todos os parâmetros da câmera para Strawberry AI
"""

import os
import sys
import time
import json
import statistics
from pathlib import Path
from datetime import datetime
from picamera2 import Picamera2
import libcamera

class TestCamera:
    def __init__(self):
        self.picam2 = None
        self.test_dir = None
        self.resultados = {}
        self.performance_data = {}
        
    def setup_test_environment(self):
        """Configura ambiente de teste"""
        print(" MEGA TESTE PICAMERA2 - RASPBERRY PI (CORRIGIDO)")
        print("=" * 65)
        
        # Criar diretório com timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.test_dir = f"mega_test_{timestamp}"
        os.makedirs(self.test_dir, exist_ok=True)
        
        # Verificar sistema
        self.check_system_info()
        
    def check_system_info(self):
        """Coleta informações do sistema"""
        print(" Coletando informações do sistema...")
        try:
            with open('/proc/device-tree/model', 'r') as f:
                model = f.read()
                print(f"   Modelo: {model.strip()}")
        except Exception as e:
            print(f"     Não foi possível ler modelo: {e}")
            
        try:
            import platform
            print(f"    Python: {platform.python_version()}")
            print(f"    Sistema: {platform.system()} {platform.release()}")
        except Exception as e:
            print(f"     Erro nas informações da plataforma: {e}")

    def initialize_camera(self):
        """Inicializa a câmera com configuração básica"""
        print("\n Inicializando câmera...")
        try:
            self.picam2 = Picamera2()
            
            # Configuração inicial padrão
            config = self.picam2.create_preview_configuration(
                main={"size": (640, 480)},
                controls={"FrameRate": 30}
            )
            self.picam2.configure(config)
            self.picam2.start()
            time.sleep(3)  # Aquecimento mais longo
            
            print("    Câmera inicializada com sucesso")
            return True
            
        except Exception as e:
            print(f"    Falha na inicialização: {e}")
            return False

    def test_basic_functionality(self):
        """Teste básico de funcionalidade"""
        print("\n TESTE 1: Funcionalidade Básica")
        print("-" * 40)
        
        # Teste de captura simples
        frames_capturados = 0
        tempos_captura = []
        
        for i in range(10):
            try:
                start_time = time.time()
                frame = self.picam2.capture_array()
                capture_time = (time.time() - start_time) * 1000
                tempos_captura.append(capture_time)
                
                if frame is not None and frame.size > 0:
                    frames_capturados += 1
                    if i == 0:
                        print(f"    Primeiro frame: {frame.shape[1]}x{frame.shape[0]} - {frame.dtype}")
                else:
                    print(f"    Frame {i+1}: Vazio")
                    
            except Exception as e:
                print(f"    Erro no frame {i+1}: {e}")
            
            time.sleep(0.1)
        
        # Estatísticas de performance
        avg_time = statistics.mean(tempos_captura) if tempos_captura else 0
        max_time = max(tempos_captura) if tempos_captura else 0
        min_time = min(tempos_captura) if tempos_captura else 0
        
        self.performance_data["capture_times"] = {
            "average_ms": avg_time,
            "max_ms": max_time,
            "min_ms": min_time,
            "frames_captured": frames_capturados
        }
        
        print(f"    Performance: {frames_capturados}/10 frames")
        print(f"     Tempo médio: {avg_time:.2f}ms (min: {min_time:.2f}ms, max: {max_time:.2f}ms)")

    def test_exposure_controls(self):
        """Teste COMPLETO de controles de exposição"""
        print("\n TESTE 2: Controles de Exposição Completo")
        print("-" * 50)
        
        # Salvar baseline atual
        self.picam2.capture_file(f"{self.test_dir}/01_baseline_auto.jpg")
        self.resultados["01_baseline_auto"] = "Configuração automática inicial"
        print("    Baseline automática salva")

        # TESTE 2.1: Tempos de exposição EXTREMOS
        print("\n     TESTE 2.1: Tempos de Exposição (Extremos)")
        tempos_exposicao = [100, 500, 1000, 2000, 5000, 10000, 20000, 50000, 100000]
        
        for exp_time in tempos_exposicao:
            try:
                controls = {
                    "AeEnable": False,
                    "ExposureTime": exp_time,
                    "AnalogueGain": 1.0,
                    "AwbEnable": False
                }
                self.picam2.set_controls(controls)
                time.sleep(2)  # Mais tempo para estabilização
                
                filename = f"{self.test_dir}/02_exposure_{exp_time:06d}us.jpg"
                self.picam2.capture_file(filename)
                self.resultados[f"02_exposure_{exp_time}us"] = f"ExposureTime: {exp_time}µs, AnalogueGain: 1.0"
                print(f"       {exp_time:6d}µs")
                
            except Exception as e:
                print(f"       {exp_time:6d}µs: {e}")

        # TESTE 2.2: Ganhos Analógicos
        print("\n    TESTE 2.2: Ganhos Analógicos")
        ganhos = [0.5, 1.0, 2.0, 4.0, 8.0, 16.0]
        
        for gain in ganhos:
            try:
                controls = {
                    "AeEnable": False,
                    "ExposureTime": 10000,  # Tempo fixo
                    "AnalogueGain": gain,
                    "AwbEnable": False
                }
                self.picam2.set_controls(controls)
                time.sleep(1.5)
                
                filename = f"{self.test_dir}/03_gain_{gain:.1f}x.jpg"
                self.picam2.capture_file(filename)
                self.resultados[f"03_gain_{gain}x"] = f"ExposureTime: 10000µs, AnalogueGain: {gain}"
                print(f"       {gain:4.1f}x")
                
            except Exception as e:
                print(f"       {gain:4.1f}x: {e}")

        # TESTE 2.3: Compensação de Exposição
        print("\n     TESTE 2.3: Compensação de Exposição (EV)")
        ev_values = [-3.0, -2.0, -1.5, -1.0, -0.5, 0, 0.5, 1.0, 1.5, 2.0, 3.0]
        
        for ev in ev_values:
            try:
                # Voltar para automático
                self.picam2.set_controls({"AeEnable": True, "AwbEnable": True})
                time.sleep(1)
                
                controls = {
                    "AeEnable": True,
                    "ExposureValue": ev
                }
                self.picam2.set_controls(controls)
                time.sleep(2)
                
                filename = f"{self.test_dir}/04_ev_{ev:+.1f}.jpg"
                self.picam2.capture_file(filename)
                self.resultados[f"04_ev_{ev:+.1f}"] = f"ExposureValue: {ev}"
                print(f"       EV {ev:+.1f}")
                
            except Exception as e:
                print(f"       EV {ev:+.1f}: {e}")

    def test_white_balance_corrected(self):
        """Teste CORRIGIDO de balanço de branco usando enums"""
        print("\n TESTE 3: Balanço de Branco (Corrigido)")
        print("-" * 45)
        
        # TESTE 3.1: Modos de AWB usando enums CORRETOS
        print("\n    TESTE 3.1: Modos de Balanço de Branco (Enums)")
        
        # Mapeamento correto usando enums do libcamera
        awb_modes = [
            (libcamera.controls.AwbModeEnum.Auto, "Auto"),
            (libcamera.controls.AwbModeEnum.Tungsten, "Tungsten"),
            (libcamera.controls.AwbModeEnum.Fluorescent, "Fluorescent"),
            (libcamera.controls.AwbModeEnum.Indoor, "Indoor"),
            (libcamera.controls.AwbModeEnum.Daylight, "Daylight"),
            (libcamera.controls.AwbModeEnum.Cloudy, "Cloudy"),
        ]
        
        for awb_enum, descricao in awb_modes:
            try:
                controls = {
                    "AeEnable": True,
                    "AwbEnable": True,
                    "AwbMode": awb_enum
                }
                self.picam2.set_controls(controls)
                time.sleep(2.5)  # Tempo extra para AWB
                
                filename = f"{self.test_dir}/05_awb_{descricao.lower()}.jpg"
                self.picam2.capture_file(filename)
                self.resultados[f"05_awb_{descricao.lower()}"] = f"AWB: {descricao} (Enum)"
                print(f"       {descricao:12}")
                
            except Exception as e:
                print(f"       {descricao:12}: {e}")

    def test_image_quality(self):
        """Teste de controles de qualidade de imagem"""
        print("\n  TESTE 4: Controles de Qualidade de Imagem")
        print("-" * 50)
        
        # Voltar para automático primeiro
        self.picam2.set_controls({"AeEnable": True, "AwbEnable": True})
        time.sleep(1)

        # TESTE 4.1: Diferentes qualidades JPEG
        print("\n   💾 TESTE 4.1: Qualidades JPEG Diferentes")
        qualidades = [30, 50, 70, 85, 95, 100]
        
        for qualidade in qualidades:
            try:
                # Para teste de qualidade, usamos capture_file que aplica compressão JPEG
                filename = f"{self.test_dir}/07_jpeg_quality_{qualidade}.jpg"
                self.picam2.capture_file(filename, quality=qualidade)
                
                # Obter tamanho do arquivo
                file_size = os.path.getsize(filename) / 1024  # KB
                
                self.resultados[f"07_jpeg_quality_{qualidade}"] = f"JPEG Quality: {qualidade}%, Size: {file_size:.1f}KB"
                print(f"       Quality {qualidade}% - {file_size:6.1f}KB")
                
            except Exception as e:
                print(f"       Quality {qualidade}%: {e}")

    def test_advanced_controls_corrected(self):
        """Teste CORRIGIDO de controles avançados"""
        print("\n TESTE 5: Controles Avançados (Corrigido)")
        print("-" * 45)
        
        # TESTE 5.1: Modos de Exposição usando enums
        print("\n    TESTE 5.1: Modos de Exposição")
        ae_modes = [
            (libcamera.controls.AeExposureModeEnum.Normal, "Normal"),
            (libcamera.controls.AeExposureModeEnum.Short, "Short"),
            (libcamera.controls.AeExposureModeEnum.Long, "Long"),
        ]
        
        for ae_enum, descricao in ae_modes:
            try:
                controls = {
                    "AeEnable": True,
                    "AeExposureMode": ae_enum
                }
                self.picam2.set_controls(controls)
                time.sleep(2)
                
                filename = f"{self.test_dir}/08_ae_mode_{descricao.lower()}.jpg"
                self.picam2.capture_file(filename)
                self.resultados[f"08_ae_mode_{descricao.lower()}"] = f"AE Mode: {descricao}"
                print(f"       AE Mode: {descricao}")
                
            except Exception as e:
                print(f"       AE Mode {descricao}: {e}")

        # TESTE 5.2: Medição de Exposição usando enums
        print("\n    TESTE 5.2: Modos de Medição")
        meter_modes = [
            (libcamera.controls.AeMeteringModeEnum.Centre, "Centre"),
            (libcamera.controls.AeMeteringModeEnum.Spot, "Spot"),
            (libcamera.controls.AeMeteringModeEnum.Matrix, "Matrix"),
        ]
        
        for meter_enum, descricao in meter_modes:
            try:
                controls = {
                    "AeEnable": True,
                    "AeMeteringMode": meter_enum
                }
                self.picam2.set_controls(controls)
                time.sleep(2)
                
                filename = f"{self.test_dir}/09_metering_{descricao.lower()}.jpg"
                self.picam2.capture_file(filename)
                self.resultados[f"09_metering_{descricao.lower()}"] = f"Metering: {descricao}"
                print(f"       Metering: {descricao}")
                
            except Exception as e:
                print(f"       Metering {descricao}: {e}")

    def test_optimized_combinations_corrected(self):
        """Teste CORRIGIDO de combinações otimizadas"""
        print("\n TESTE 6: Combinações Otimizadas (Corrigido)")
        print("-" * 50)
        
        # Combinações usando enums CORRETOS
        combinacoes = [
            {
                "nome": "exterior_sol_forte", 
                "desc": "Exterior - Sol Forte",
                "controls": {
                    "AeEnable": False, 
                    "ExposureTime": 500, 
                    "AnalogueGain": 1.0, 
                    "AwbMode": libcamera.controls.AwbModeEnum.Daylight
                }
            },
            {
                "nome": "exterior_nublado", 
                "desc": "Exterior - Nublado", 
                "controls": {
                    "AeEnable": False, 
                    "ExposureTime": 2000, 
                    "AnalogueGain": 1.5, 
                    "AwbMode": libcamera.controls.AwbModeEnum.Cloudy
                }
            },
            {
                "nome": "interior_luz_led", 
                "desc": "Interior - LED",
                "controls": {
                    "AeEnable": False, 
                    "ExposureTime": 8000, 
                    "AnalogueGain": 2.0, 
                    "AwbMode": libcamera.controls.AwbModeEnum.Fluorescent
                }
            },
            {
                "nome": "interior_incandescente", 
                "desc": "Interior - Incandescente",
                "controls": {
                    "AeEnable": False, 
                    "ExposureTime": 15000, 
                    "AnalogueGain": 3.0, 
                    "AwbMode": libcamera.controls.AwbModeEnum.Tungsten
                }
            },
            {
                "nome": "balanced_geral", 
                "desc": "Balanceado - Geral",
                "controls": {
                    "AeEnable": False, 
                    "ExposureTime": 5000, 
                    "AnalogueGain": 1.8, 
                    "AwbMode": libcamera.controls.AwbModeEnum.Auto
                }
            },
            {
                "nome": "alta_velocidade", 
                "desc": "Alta Velocidade",
                "controls": {
                    "AeEnable": False, 
                    "ExposureTime": 100, 
                    "AnalogueGain": 8.0, 
                    "AwbMode": libcamera.controls.AwbModeEnum.Auto
                }
            },
        ]
        
        for combo in combinacoes:
            try:
                self.picam2.set_controls(combo["controls"])
                time.sleep(2)
                
                filename = f"{self.test_dir}/10_combo_{combo['nome']}.jpg"
                self.picam2.capture_file(filename)
                
                # Converter controles para string legível
                controls_str = {k: str(v) for k, v in combo["controls"].items()}
                self.resultados[f"10_combo_{combo['nome']}"] = f"Combo: {combo['desc']} - {controls_str}"
                print(f"    {combo['desc']}")
                
            except Exception as e:
                print(f"    {combo['desc']}: {e}")

    def test_sensor_modes(self):
        """Teste de diferentes modos do sensor"""
        print("\n📡 TESTE 7: Modos do Sensor")
        print("-" * 30)
        
        try:
            # Obter modos disponíveis do sensor
            camera_config = self.picam2.camera_configuration()
            print(f"   📋 Modos disponíveis: {len(camera_config)}")
            
            # Testar alguns tamanhos comuns
            sizes = [(320, 240), (640, 480), (800, 600), (1024, 768)]
            
            for i, size in enumerate(sizes, 1):
                try:
                    # Parar câmera temporariamente
                    self.picam2.stop()
                    time.sleep(0.5)
                    
                    # Nova configuração
                    new_config = self.picam2.create_preview_configuration(
                        main={"size": size},
                        controls={"FrameRate": 30}
                    )
                    self.picam2.configure(new_config)
                    self.picam2.start()
                    time.sleep(1.5)  # Estabilização
                    
                    # Capturar frame
                    frame = self.picam2.capture_array()
                    if frame is not None:
                        filename = f"{self.test_dir}/11_sensor_{size[0]}x{size[1]}.jpg"
                        self.picam2.capture_file(filename)
                        self.resultados[f"11_sensor_{size[0]}x{size[1]}"] = f"Size: {size[0]}x{size[1]}"
                        print(f"    Sensor {size[0]}x{size[1]}")
                    else:
                        print(f"    Sensor {size[0]}x{size[1]}: Frame vazio")
                        
                except Exception as e:
                    print(f"    Sensor {size[0]}x{size[1]}: {e}")
            
            # Voltar para configuração original
            self.picam2.stop()
            original_config = self.picam2.create_preview_configuration(
                main={"size": (640, 480)},
                controls={"FrameRate": 30}
            )
            self.picam2.configure(original_config)
            self.picam2.start()
            time.sleep(1)
            
        except Exception as e:
            print(f"    Teste de modos do sensor: {e}")

    def generate_report(self):
        """Gera relatório completo do teste"""
        print("\n GERANDO RELATÓRIO COMPLETO...")
        
        # Salvar dados de performance
        report_data = {
            "test_timestamp": datetime.now().isoformat(),
            "test_directory": self.test_dir,
            "performance": self.performance_data,
            "results": self.resultados,
            "summary": {
                "total_tests": len(self.resultados),
                "performance_avg_capture_time": self.performance_data.get("capture_times", {}).get("average_ms", 0),
                "recommendations": self.generate_recommendations()
            }
        }
        
        # Salvar JSON
        with open(f"{self.test_dir}/full_report.json", "w") as f:
            json.dump(report_data, f, indent=4, ensure_ascii=False)
        
        # Gerar relatório HTML
        self.generate_html_report(report_data)
        
        print(" MEGA TESTE CONCLUÍDO!")
        print("=" * 60)
        print(f" Diretório: {self.test_dir}/")
        print(f" Relatório: {self.test_dir}/full_report.json")
        print(f" HTML: {self.test_dir}/report.html")
        print(f"  Total de imagens: {len(self.resultados)}")
        
    def generate_recommendations(self):
        """Gera recomendações baseadas nos testes"""
        return {
            "para_ambientes_claros": "Use ExposureTime baixo (500-2000µs) com AnalogueGain 1.0 e AWB 'Daylight'",
            "para_ambientes_escuros": "Use ExposureTime alto (8000-20000µs) com AnalogueGain 2.0-4.0 e AWB 'Fluorescent'",
            "para_cores_naturais": "Mantenha AWB no modo 'Auto' para maior flexibilidade",
            "para_performance": "Mantenha AnalogueGain abaixo de 4.0 para melhor qualidade",
            "qualidade_jpeg": "Use qualidade 70-85% para equilíbrio entre tamanho e qualidade"
        }
    
    def generate_html_report(self, report_data):
        """Gera relatório HTML visual"""
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Mega Teste Picamera2 - Strawberry AI</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .header {{ background: #2c3e50; color: white; padding: 20px; border-radius: 10px; }}
                .test-group {{ margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }}
                .images {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px; }}
                .image-card {{ border: 1px solid #ccc; padding: 5px; text-align: center; }}
                .image-card img {{ max-width: 100%; height: auto; }}
                .recommendation {{ background: #e8f5e8; padding: 15px; border-radius: 5px; margin: 10px 0; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1> Mega Teste Picamera2 - Strawberry AI</h1>
                <p>Teste completo realizado em: {report_data['test_timestamp']}</p>
            </div>
            
            <div class="recommendation">
                <h2> Recomendações</h2>
                <ul>
        """
        
        for key, recommendation in report_data['summary']['recommendations'].items():
            html_content += f'<li><strong>{key.replace("_", " ").title()}:</strong> {recommendation}</li>'
        
        html_content += """
                </ul>
            </div>
            
            <h2> Performance</h2>
            <p>Tempo médio de captura: {:.2f}ms</p>
            <p>Frames capturados no teste básico: {}/10</p>
        """.format(
            report_data['performance'].get('capture_times', {}).get('average_ms', 0),
            report_data['performance'].get('capture_times', {}).get('frames_captured', 0)
        )
        
        # Adicionar imagens por grupo
        test_groups = {}
        for test_name in report_data['results']:
            group = test_name.split('_')[0]
            if group not in test_groups:
                test_groups[group] = []
            test_groups[group].append(test_name)
        
        for group, tests in test_groups.items():
            html_content += f'<div class="test-group"><h3>Grupo {group}</h3><div class="images">'
            for test in tests:
                img_path = f"{test}.jpg"
                if os.path.exists(f"{self.test_dir}/{img_path}"):
                    html_content += f'''
                    <div class="image-card">
                        <img src="{img_path}" alt="{test}">
                        <div><small>{test}</small></div>
                    </div>
                    '''
            html_content += '</div></div>'
        
        html_content += "</body></html>"
        
        with open(f"{self.test_dir}/report.html", "w") as f:
            f.write(html_content)

    def run_complete_test(self):
        """Executa todos os testes"""
        self.setup_test_environment()
        
        if not self.initialize_camera():
            return False
            
        try:
            # Executar todos os testes
            self.test_basic_functionality()
            self.test_exposure_controls()
            self.test_white_balance_corrected()  # CORRIGIDO
            self.test_image_quality()
            self.test_advanced_controls_corrected()  # CORRIGIDO
            self.test_optimized_combinations_corrected()  # CORRIGIDO
            self.test_sensor_modes()  # NOVO TESTE
            
            # Gerar relatórios
            self.generate_report()
            
            return True
            
        except Exception as e:
            print(f" Erro durante os testes: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            if self.picam2:
                self.picam2.stop()
                self.picam2.close()
                print(" Câmera liberada")

def main():
    """Função principal"""
    test_suite = TestCamera()
    success = test_suite.run_complete_test()
    
    if success:
        print("\n TODOS OS TESTES FORAM CONCLUÍDOS COM SUCESSO!")
        print("Agora analise as imagens e identifique as melhores configurações")
        print(" Use o relatório HTML para visualizar todas as imagens facilmente")
    else:
        print("\n ALGUNS TESTES FALHARAM!")
        print(" Verifique os logs acima para troubleshooting")

if __name__ == "__main__":
    main()
