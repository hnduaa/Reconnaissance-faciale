import cv2
import paho.mqtt.client as mqtt # type: ignore
import json
import time
import datetime
import base64
import os
import threading

# Configuration
VIDEO_URL = "http://192.168.11.112:4747/video"  # URL DroidCam
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_TOPIC_CAPTURE = "home/security/capture"
MQTT_TOPIC_MOVEMENT = "home/security/movement"
MQTT_TOPIC_RESULT = "home/security/access_result"

# Créer le dossier pour les captures temporaires s'il n'existe pas
os.makedirs("captures", exist_ok=True)

# Configuration MQTT
client = mqtt.Client()

def on_connect(client, userdata, flags, rc):
    print(f"Connecté au broker MQTT avec le code: {rc}")
    client.subscribe(MQTT_TOPIC_CAPTURE)
    client.subscribe(MQTT_TOPIC_MOVEMENT)

def on_message(client, userdata, msg):
    print(f"Message reçu sur le topic {msg.topic}")
    
    if msg.topic == MQTT_TOPIC_CAPTURE:
        # Déclencher la capture manuellement
        threading.Thread(target=capture_and_send_image).start()
    
    elif msg.topic == MQTT_TOPIC_MOVEMENT:
        try:
            payload = json.loads(msg.payload.decode())
            if payload.get("detected", False):
                print("Mouvement détecté! Capture d'image en cours...")
                
                # Attendre un court instant avant de capturer (simulation caméra qui se tourne)
                time.sleep(1)
                threading.Thread(target=capture_and_send_image).start()
        except Exception as e:
            print(f"Erreur lors du traitement du message de mouvement: {e}")

def capture_and_send_image():
    try:
        # Initialiser la capture vidéo
        cap = cv2.VideoCapture(VIDEO_URL)
        if not cap.isOpened():
            print("Erreur: Impossible d'ouvrir la caméra")
            publish_error("camera_error", "Impossible d'accéder à la caméra")
            return
        
        # Attendre que la caméra s'initialise
        time.sleep(1)
        
        # Capturer une image
        ret, frame = cap.read()
        cap.release()
        
        if not ret:
            print("Erreur: Impossible de capturer l'image")
            publish_error("capture_error", "Échec de capture d'image")
            return
        
        # Sauvegarder l'image
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"captures/capture_{timestamp}.jpg"
        cv2.imwrite(filename, frame)
        
        # Convertir l'image en base64 pour l'envoyer via MQTT
        with open(filename, "rb") as img_file:
            img_data = base64.b64encode(img_file.read()).decode('utf-8')
        
        # Envoyer l'image et son chemin pour analyse au service de reconnaissance
        # Le service principal utilisera cette image pour la reconnaissance
        payload = {
            "timestamp": datetime.datetime.now().isoformat(),
            "image_path": filename,
            "image_data": img_data
        }
        
        # Publier l'image pour analyse (le service principal utilisera ces données)
        client.publish("home/security/analyze_image", json.dumps(payload))
        print(f"Image capturée et envoyée pour analyse: {filename}")
        
    except Exception as e:
        print(f"Erreur lors de la capture: {e}")
        publish_error("general_error", str(e))

def publish_error(error_type, error_message):
    """Publie un message d'erreur sur le topic des résultats"""
    payload = {
        "status": "error",
        "error_type": error_type,
        "message": error_message,
        "timestamp": datetime.datetime.now().isoformat()
    }
    client.publish(MQTT_TOPIC_RESULT, json.dumps(payload))

def start_mqtt_service():
    client.on_connect = on_connect
    client.on_message = on_message
    
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_forever()
    except Exception as e:
        print(f"Erreur de connexion MQTT: {e}")
        time.sleep(10)  # Attendre avant de réessayer
        start_mqtt_service()  # Tentative de reconnexion

if __name__ == "__main__":
    print("Démarrage du service de capture d'images...")
    start_mqtt_service()