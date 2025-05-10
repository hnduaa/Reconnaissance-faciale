import cv2
from deepface import DeepFace
import requests
import datetime
import csv
import os
import uuid
import time
import paho.mqtt.client as mqtt # type: ignore
import json
import threading
import base64
import numpy as np

# Configuration
REFERENCE_FOLDER = "authorized_faces"
LOG_FILE = "access_log.csv"
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_TOPIC_MOVEMENT = "home/security/movement"
MQTT_TOPIC_RESULT = "home/security/access_result"
MQTT_TOPIC_ANALYZE = "home/security/analyze_image"

# Créer le dossier pour les visages autorisés s'il n'existe pas
os.makedirs(REFERENCE_FOLDER, exist_ok=True)

# Créer le fichier de log s'il n'existe pas
if not os.path.exists(LOG_FILE):
    with open(LOG_FILE, mode='w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["Date", "Identité", "Résultat"])

# Configuration MQTT
client = mqtt.Client()

def on_connect(client, userdata, flags, rc):
    print(f"Connecté au broker MQTT avec le code: {rc}")
    client.subscribe(MQTT_TOPIC_MOVEMENT)
    client.subscribe(MQTT_TOPIC_ANALYZE)

def on_message(client, userdata, msg):
    print(f"Message reçu sur le topic {msg.topic}")
    
    if msg.topic == MQTT_TOPIC_MOVEMENT:
        payload = json.loads(msg.payload.decode())
        if payload.get("detected", False):
            print("Mouvement détecté! Surveillance activée...")
            # Le service de capture s'occupera de prendre l'image
    
    elif msg.topic == MQTT_TOPIC_ANALYZE:
        # Traiter l'image reçue du service de capture
        try:
            payload = json.loads(msg.payload.decode())
            image_path = payload.get("image_path")
            
            if image_path and os.path.exists(image_path):
                # Lancer l'analyse du visage dans un thread séparé
                threading.Thread(target=process_image, args=(image_path, payload.get("image_data"))).start()
            else:
                print(f"Erreur: Fichier image introuvable - {image_path}")
                publish_result("error", "image_not_found", None)
        except Exception as e:
            print(f"Erreur lors du traitement du message d'analyse: {e}")
            publish_result("error", str(e), None)

def log_access(result, identity):
    with open(LOG_FILE, mode='a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([datetime.datetime.now(), identity, result])

def verify_face(img_path):
    for file in os.listdir(REFERENCE_FOLDER):
        if not file.lower().endswith(('.png', '.jpg', '.jpeg')):
            continue
        
        ref_path = os.path.join(REFERENCE_FOLDER, file)
        try:
            result = DeepFace.verify(img_path, ref_path, enforce_detection=False)
            if result["verified"]:
                identity = os.path.splitext(file)[0]  # Nom sans extension
                return True, identity
        except Exception as e:
            print(f"Erreur lors de la vérification avec {file}: {e}")
            continue
    
    return False, "unknown"

def publish_result(status, identity, image_data):
    payload = {
        "status": status,
        "identity": identity,
        "timestamp": datetime.datetime.now().isoformat(),
    }
    
    # Si l'image existe, l'ajouter au payload
    if image_data:
        payload["image"] = image_data
    
    client.publish(MQTT_TOPIC_RESULT, json.dumps(payload))
    print(f"Résultat publié: {status} - {identity}")

def process_image(image_path, image_data):
    """Traite l'image pour vérifier l'identité"""
    try:
        # Vérifier le visage
        is_trusted, identity = verify_face(image_path)
        
        # Enregistrer et publier le résultat
        status = "trusted" if is_trusted else "untrusted"
        log_access(status, identity)
        publish_result(status, identity, image_data)
        
    except Exception as e:
        print(f"Erreur lors du traitement de l'image: {e}")
        publish_result("error", str(e), None)

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
    print("Démarrage du service de reconnaissance faciale...")
    start_mqtt_service()