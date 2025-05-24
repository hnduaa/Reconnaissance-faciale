import cv2
from deepface import DeepFace
import requests
import datetime
import csv
import os
import uuid
import time
import paho.mqtt.client as mqtt
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
    # client.subscribe(MQTT_TOPIC_MOVEMENT)
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

def find_face(img_path):
    try:
        # Utiliser DeepFace.find() au lieu de DeepFace.verify()
        # Cette fonction recherche dans tout le dossier de référence
        result = DeepFace.find(
            img_path=img_path,
            db_path=REFERENCE_FOLDER,
            enforce_detection=False,
            silent=True
        )
        
        # Vérifier si des correspondances ont été trouvées
        if len(result) > 0 and len(result[0]) > 0:
            # Obtenir la meilleure correspondance (la première)
            best_match = result[0].iloc[0]
            
            # Extraire le nom du fichier de la meilleure correspondance
            identity_path = best_match["identity"]
            identity = os.path.splitext(os.path.basename(identity_path))[0]
            
            # Vérifier si la distance est inférieure à un seuil
            # Plus la distance est faible, plus la correspondance est bonne
            threshold = 0.5  # Vous pouvez ajuster ce seuil selon vos besoins
            if best_match["distance"] < threshold:
                return True, identity, best_match["distance"]
            else:
                return False, "unknown", best_match["distance"]
        else:
            return False, "unknown", None
            
    except Exception as e:
        print(f"Erreur lors de la recherche du visage: {e}")
        return False, "error", None

def publish_result(status, identity, image_data, confidence=None):
    payload = {
        "status": status,
        "identity": identity,
        "timestamp": datetime.datetime.now().isoformat(),
    }
    
    # Ajouter le niveau de confiance si disponible
    if confidence is not None:
        payload["confidence"] = confidence
    
    # Si l'image existe, l'ajouter au payload
    if image_data:
        payload["image"] = image_data
    
    client.publish(MQTT_TOPIC_RESULT, json.dumps(payload))
    print(f"Résultat publié: {status} - {identity} - Confiance: {confidence}")

def process_image(image_path, image_data):
    """Traite l'image pour trouver l'identité en utilisant DeepFace.find()"""
    try:
        # Rechercher le visage dans la base de données
        is_trusted, identity, confidence = find_face(image_path)
        
        # Enregistrer et publier le résultat
        status = "trusted" if is_trusted else "untrusted"
        log_access(status, identity)
        publish_result(status, identity, image_data, confidence)
        
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
    print("Démarrage du service de reconnaissance faciale avec DeepFace.find()...")
    start_mqtt_service()