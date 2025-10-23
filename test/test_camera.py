#!/usr/bin/env python3
"""
DIAGNÓSTICO UNIFICADO - CÂmera Raspberry Pi
Combina todas as verificações em um único script completo
"""
import os
import cv2
import subprocess
import shutil
import time

def run_command(cmd, timeout=10):
    """Executa comando e retorna (success, stdout, stderr)"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return False, "", f"Timeout após {timeout}s"
    except Exception as e:
        return False, "", str(e)

def run_cmd(cmd, timeout=5):
    """Executa comando shell e retorna (stdout, stderr, returncode)"""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except Exception as e:
        return "", str(e), 1

def check_raspberry_pi():
    """Verifica se é Raspberry Pi e obtém modelo"""
    print("🔍 Verificando hardware...")
    is_rpi, model, _ = run_command("cat /proc/device-tree/model")
    if is_rpi and model:
        print(f"✅ Raspberry Pi detectada: {model}")
        return True
    else:
        print("❌ Não é Raspberry Pi ou modelo não detectado")
        return False

def check_boot_config():
    """Verifica configuração do /boot/firmware/config.txt"""
    print("\n🔧 Verificando configuração do boot...")
    config_file = "/boot/firmware/config.txt"
    if not os.path.exists(config_file):
        print("⚠️  /boot/firmware/config.txt não encontrado")
        return False
        
    config_keys = ["start_x", "gpu_mem", "camera_auto_detect"]
    for key in config_keys:
        exists, output, _ = run_command(f"grep -i '^{key}=' {config_file} || echo 'Não configurado'")
        print(f"   {key}: {output}")

def check_kernel_modules():
    """Verifica módulos do kernel carregados"""
    print("\n📦 Verificando módulos do kernel...")
    
    # Verifica bcm2835-v4l2 (legacy)
    legacy_loaded, legacy_out, _ = run_command("lsmod | grep bcm2835_v4l2")
    if legacy_loaded:
        print("✅ Módulo bcm2835-v4l2 carregado (modo Legacy V4L2)")
    else:
        print("❌ Módulo bcm2835-v4l2 não carregado")
        print("   ➜ Execute: sudo modprobe bcm2835-v4l2")

def check_user_permissions():
    """Verifica permissões do usuário"""
    print("\n👥 Verificando permissões de usuário...")
    user = os.getenv('USER')
    has_video, groups_out, _ = run_command(f"groups {user} | grep -E '(video|plugdev)'")
    
    if has_video:
        print("✅ Usuário está no grupo 'video'")
    else:
        print("❌ Usuário NÃO está no grupo 'video'")
        print(f"   ➜ Execute: sudo usermod -aG video {user}")

def check_camera_status():
    """Verifica status da câmera via vcgencmd"""
    print("\n📊 Verificando status da câmera...")
    success, output, _ = run_command("vcgencmd get_camera")
    if success and output:
        print(f"📷 Status: {output}")
    else:
        print("⚠️  Não foi possível obter status com vcgencmd")

def list_video_devices():
    """Lista dispositivos de vídeo disponíveis"""
    print("\n🎥 Dispositivos de vídeo detectados:")
    success, output, _ = run_command("v4l2-ctl --list-devices")
    if success and output:
        print(output)
    else:
        print("⚠️  Nenhum dispositivo listado com v4l2-ctl")

def check_camera_processes():
    """Verifica processos usando a câmera"""
    print("\n📊 Verificando processos usando câmera...")
    success, output, _ = run_command("sudo fuser -v /dev/video0 /dev/video1 /dev/video10 2>/dev/null || echo 'Nenhum processo encontrado'")
    print(output)

def test_opencv_devices(max_devices=5):
    """Testa captura com OpenCV"""
    print(f"\n🔍 Testando {max_devices} dispositivos via OpenCV (V4L2)...")
    found_any = False
    
    for i in range(max_devices):
        try:
            cap = cv2.VideoCapture(i, cv2.CAP_V4L2)
            if cap.isOpened():
                ret, frame = cap.read()
                found_any = True
                if ret and frame is not None:
                    print(f"✅ /dev/video{i}: Captura OK - {frame.shape[1]}x{frame.shape[0]}")
                else:
                    print(f"⚠️  /dev/video{i}: Aberto, mas sem frames válidos")
            else:
                print(f"❌ /dev/video{i}: Não disponível")
            cap.release()
        except Exception as e:
            print(f"❌ /dev/video{i}: Erro - {e}")
    
    if not found_any:
        print("⚠️  Nenhum dispositivo acessível via OpenCV")

def test_libcamera_cli():
    """Testa libcamera via linha de comando"""
    print("\n🎯 Testando libcamera (CLI)...")
    
    # Verifica se libcamera está instalado
    libcamera_installed, _, _ = run_command("which rpicam-still")
    if not libcamera_installed:
        print("❌ libcamera não instalado")
        return False
    
    # Testa listagem de câmeras
    success, stdout, stderr = run_command("timeout 5 libcamera-hello --list-cameras")
    if success:
        print("✅ libcamera-hello funcionando")
        if stdout:
            for line in stdout.split('\n'):
                if 'detected' in line.lower():
                    print(f"   📷 {line.strip()}")
    else:
        print(f"❌ libcamera-hello falhou: {stderr}")
    
    # Testa captura de foto
    print("\n🖼️  Testando captura de foto com libcamera...")
    success, _, stderr = run_command("rpicam-still -o /tmp/test_libcamera.jpg --nopreview --timeout 1000")
    if success and os.path.exists('/tmp/test_libcamera.jpg'):
        size = os.path.getsize('/tmp/test_libcamera.jpg')
        print(f"✅ libcamera capturou imagem ({size} bytes)")
        os.remove('/tmp/test_libcamera.jpg')
        return True
    else:
        print(f"❌ Falha na captura libcamera: {stderr}")
        return False

def test_picamera2_python():
    """Testa Picamera2 via Python"""
    print("\n🐍 Testando Picamera2 (Python)...")
    
    try:
        from picamera2 import Picamera2
        PICAMERA2_AVAILABLE = True
    except ImportError:
        print("❌ Picamera2 não disponível")
        print("   ➜ Instale: sudo apt install python3-picamera2")
        return False
    
    try:
        picam2 = Picamera2()
        config = picam2.create_preview_configuration()
        picam2.configure(config)
        picam2.start()
        
        # Aguarda estabilização
        time.sleep(2)
        
        # Captura frame
        frame = picam2.capture_array()
        picam2.stop()
        picam2.close()
        
        if frame is not None and frame.size > 0:
            print(f"✅ Picamera2 funcionando - Frame: {frame.shape[1]}x{frame.shape[0]}")
            return True
        else:
            print("❌ Picamera2 retornou frame vazio")
            return False
            
    except Exception as e:
        print(f"❌ Picamera2 falhou: {e}")
        return False

def generate_recommendations(libcamera_ok, picamera2_ok, is_rpi):
    """Gera recomendações baseadas nos resultados dos testes"""
    print("\n" + "="*50)
    print("📋 RECOMENDAÇÕES E PRÓXIMOS PASSOS")
    print("="*50)
    
    if not is_rpi:
        print("❌ Este não é um Raspberry Pi - algumas verificações podem não se aplicar")
        return
    
    if libcamera_ok and picamera2_ok:
        print("🎉 TUDO FUNCIONANDO PERFEITAMENTE!")
        print("✅ Use Picamera2 no seu código Python")
        print("✅ libcamera está operacional")
        
    elif libcamera_ok and not picamera2_ok:
        print("⚠️  libcamera funciona mas Picamera2 tem problemas")
        print("🔧 Soluções:")
        print("   ➜ Verifique a instalação: sudo apt install python3-picamera2")
        print("   ➜ Reinicie o sistema após instalação")
        
    elif not libcamera_ok and not picamera2_ok:
        print("🚨 PROBLEMAS GRAVES DETECTADOS")
        print("🔧 Ações necessárias:")
        print("   1. Edite /boot/firmware/config.txt:")
        print("      start_x=1")
        print("      gpu_mem=128")
        print("      camera_auto_detect=1")
        print("   2. Reinicie: sudo reboot")
        print("   3. Verifique o cabo da câmera CSI")
        print("   4. Execute este diagnóstico novamente")
    
    print("\n🎯 MÉTODO RECOMENDADO PARA SEU PROJETO:")
    print("   ✅ Use APENAS Picamera2 (libcamera) no Raspberry Pi OS moderno")
    print("   ❌ NÃO use OpenCV com câmera CSI - causa conflitos!")
    print("   ✅ Para outros sistemas (Windows/Linux não-RPi), use OpenCV")
    
    print("\n🔧 COMANDOS ÚTEIS:")
    print("   ➜ Instalar Picamera2: sudo apt install python3-picamera2")
    print("   ➜ Adicionar ao grupo video: sudo usermod -aG video $USER")
    print("   ➜ Teste rápido: rpicam-still -o test.jpg --nopreview")
    print("   ➜ Reiniciar serviço câmera: sudo systemctl restart systemd-udevd")

def main():
    print("="*60)
    print("🧠 DIAGNÓSTICO UNIFICADO - CÂMERA RASPBERRY PI")
    print("="*60)
    
    # Verificação básica do sistema
    is_rpi = check_raspberry_pi()
    
    # Executar todas as verificações
    check_boot_config()
    check_kernel_modules()
    check_user_permissions()
    check_camera_status()
    list_video_devices()
    check_camera_processes()
    
    # Testes de funcionamento
    test_opencv_devices()
    libcamera_ok = test_libcamera_cli()
    picamera2_ok = test_picamera2_python()
    
    # Recomendações finais
    generate_recommendations(libcamera_ok, picamera2_ok, is_rpi)
    
    print("\n" + "="*60)
    print("✅ DIAGNÓSTICO COMPLETO")
    print("="*60)

if __name__ == "__main__":
    main()