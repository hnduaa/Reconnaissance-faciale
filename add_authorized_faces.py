import cv2
import os
import paho.mqtt.client as mqtt # type: ignore
import json
import time
import base64
import numpy as np

REFERENCE_FOLDER = "authorized_faces"
VIDEO_URL = "http://192.168.11.112:4747/video"  # URL DroidCam
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_TOPIC_ADD_FACE = "home/security/add_face"
MQTT_TOPIC_ADD_FACE_RESULT = "home/security/add_face_result"

os.makedirs(REFERENCE_FOLDER, exist_ok=True)

# Configuration MQTT
client = mqtt.Client()

def on_connect(client, userdata, flags, rc):
    print(f"Connecté au broker MQTT avec le code: {rc}")
    client.subscribe(MQTT_TOPIC_ADD_FACE)

def on_message(client, userdata, msg):
    print(f"Message reçu sur le topic {msg.topic}")
    if msg.topic == MQTT_TOPIC_ADD_FACE:
        try:
            payload = json.loads(msg.payload.decode())
            name = payload.get("name", "").strip().replace(" ", "_")
            capture_mode = payload.get("capture_mode", "auto")
            
            if not name:
                publish_result(False, "Le nom ne peut pas être vide")
                return
                
            if capture_mode == "auto":
                # Capture automatique
                result, message = capture_and_save_auto(name)
            elif capture_mode == "manual" and "image_data" in payload:
                # Image fournie directement
                result, message = save_from_base64(name, payload["image_data"])
            else:
                result, message = False, "Mode de capture non valide"
                
            publish_result(result, message)
        except Exception as e:
            publish_result(False, f"Erreur: {str(e)}")

def publish_result(success, message):
    result = {
        "success": success,
        "message": message,
        "timestamp": time.time()
    }
    client.publish(MQTT_TOPIC_ADD_FACE_RESULT, json.dumps(result))

def save_from_base64(name, image_data):
    """Sauvegarde une image à partir de données base64"""
    try:
        # Décoder l'image base64
        img_bytes = base64.b64decode(image_data)
        np_arr = np.frombuffer(img_bytes, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        
        if frame is None:
            return False, "Image incorrecte ou corrompue"
        
        # Sauvegarder l'image
        filename = os.path.join(REFERENCE_FOLDER, f"{name}.jpg")
        cv2.imwrite(filename, frame)
        return True, f"Visage de {name} ajouté avec succès"
    except Exception as e:
        return False, f"Erreur lors de l'ajout du visage: {e}"

def capture_and_save_auto(name):
    """Capture automatiquement une image depuis la caméra et la sauvegarde"""
    try:
        cap = cv2.VideoCapture(VIDEO_URL)
        if not cap.isOpened():
            return False, "Impossible d'accéder à la caméra"
        
        # Attendre que la caméra s'initialise
        time.sleep(2)
        
        # Capturer plusieurs images et choisir la meilleure
        best_frame = None
        for _ in range(5):  # Prendre 5 images
            ret, frame = cap.read()
            if ret:
                if best_frame is None or has_better_quality(frame, best_frame):
                    best_frame = frame
            time.sleep(0.5)
        
        cap.release()
        
        if best_frame is None:
            return False, "Impossible de capturer une image de qualité"
        
        # Sauvegarder l'image
        filename = os.path.join(REFERENCE_FOLDER, f"{name}.jpg")
        cv2.imwrite(filename, best_frame)
        
        # Convertir l'image en base64 pour la renvoyer
        _, buffer = cv2.imencode('.jpg', best_frame)
        img_base64 = base64.b64encode(buffer).decode('utf-8')
        
        return True, {"message": f"Visage de {name} ajouté avec succès", "image": img_base64}
    
    except Exception as e:
        return False, f"Erreur lors de la capture: {str(e)}"

def has_better_quality(new_frame, old_frame):
    """Détermine si la nouvelle image est de meilleure qualité"""
    # Une heuristique simple: comparer la variance (plus de variance = plus de détails)
    new_var = cv2.Laplacian(new_frame, cv2.CV_64F).var()
    old_var = cv2.Laplacian(old_frame, cv2.CV_64F).var()
    return new_var > old_var

def start_mqtt_service():
    client.on_connect = on_connect
    client.on_message = on_message
    
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_forever()
    except Exception as e:
        print(f"Erreur de connexion MQTT: {e}")

if __name__ == "__main__":
    print("Démarrage du service d'ajout de visages autorisés...")
    start_mqtt_service()