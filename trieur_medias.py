import os
import shutil
import time
from datetime import datetime
from PIL import Image
from PIL.ExifTags import TAGS
from hachoir.parser import createParser
from hachoir.metadata import extractMetadata

# Désactivation des logs parasites de hachoir
import hachoir.core.config
hachoir.core.config.quiet = True

def lire_config(chemin_config):
    config = {}
    with open(chemin_config, 'r', encoding='utf-8') as f:
        for ligne in f:
            if '=' in ligne:
                cle, valeur = ligne.split('=', 1)
                config[cle.strip().upper()] = valeur.strip()
    return config.get('SOURCE'), config.get('CIBLE')

def obtenir_annee_creation(chemin_fichier):
    extension = os.path.splitext(chemin_fichier)[1].lower()
    
    # 1. Tentative d'extraction EXIF pour les images
    if extension in ['.jpg', '.jpeg', '.png', '.tiff']:
        try:
            with Image.open(chemin_fichier) as img:
                exif_data = img._getexif()
                if exif_data:
                    for tag_id, value in exif_data.items():
                        tag = TAGS.get(tag_id, tag_id)
                        if tag == 'DateTimeOriginal' or tag == 'DateTime':
                            # Format EXIF: YYYY:MM:DD HH:MM:SS
                            return value.split(':')[0]
        except Exception:
            pass

    # 2. Tentative d'extraction des métadonnées MEDIA pour vidéos (et fallback)
    try:
        parser = createParser(chemin_fichier)
        if parser:
            with parser:
                metadata = extractMetadata(parser)
                if metadata and metadata.has('creation_date'):
                    date_creation = metadata.get('creation_date')
                    return str(date_creation.year)
    except Exception:
        pass

    return None

def generer_nom_unique(chemin_cible):
    if not os.path.exists(chemin_cible):
        return chemin_cible
    
    dossier, nom_fichier = os.path.split(chemin_cible)
    nom, ext = os.path.splitext(nom_fichier)
    
    compteur = 1
    nouveau_chemin = os.path.join(dossier, f"{nom}_{compteur}{ext}")
    while os.path.exists(nouveau_chemin):
        compteur += 1
        nouveau_chemin = os.path.join(dossier, f"{nom}_{compteur}{ext}")
        
    return nouveau_chemin

def copier_securise(source, cible):
    for tentative in range(2):
        try:
            shutil.copy2(source, cible)
            return True
        except Exception:
            time.sleep(0.5) # Attente avant la deuxième tentative
    return False

def main():
    fichier_config = 'config.txt'
    
    if not os.path.exists(fichier_config):
        print(f"Erreur : Le fichier de configuration '{fichier_config}' est introuvable.")
        return

    source, cible = lire_config(fichier_config)
    
    if not source or not cible:
        print("Erreur : Le fichier de configuration doit contenir SOURCE=... et CIBLE=...")
        return
        
    print(f"Source = {source}")
    print(f"Cible = {cible}")

    os.makedirs(cible, exist_ok=True)
    fichier_log = os.path.join(cible, 'log.txt')
    dossier_duplicat = os.path.join(cible, 'DUPLICAT')
    os.makedirs(dossier_duplicat, exist_ok=True)

    # Dictionnaire pour le suivi des fichiers déjà traités : { "nom_fichier.ext": [taille1, taille2, ...] }
    fichiers_traites = {}

    for dossier_actuel, sous_dossiers, fichiers in os.walk(source):
        print(f"\nTraitement du dossier : {dossier_actuel}")
        
        for nom_fichier in fichiers:
            chemin_source = os.path.join(dossier_actuel, nom_fichier)
            taille_fichier = os.path.getsize(chemin_source)
            
            # Gestion des doublons
            est_vrai_doublon = False
            est_faux_doublon = False
            
            if nom_fichier in fichiers_traites:
                if taille_fichier in fichiers_traites[nom_fichier]:
                    est_vrai_doublon = True
                else:
                    est_faux_doublon = True
                    fichiers_traites[nom_fichier].append(taille_fichier)
            else:
                fichiers_traites[nom_fichier] = [taille_fichier]

            if est_vrai_doublon:
                chemin_final = generer_nom_unique(os.path.join(dossier_duplicat, nom_fichier))
                if not copier_securise(chemin_source, chemin_final):
                    with open(fichier_log, 'a', encoding='utf-8') as log:
                        log.write(f"ECHEC COPIE (Vrai Doublon) : {chemin_source}\n")
                continue

            # Extraction de l'année
            annee = obtenir_annee_creation(chemin_source)
            
            if not annee:
                with open(fichier_log, 'a', encoding='utf-8') as log:
                    log.write(f"SANS METADONNEES : {chemin_source}\n")
                continue

            # Création du dossier de l'année
            dossier_annee = os.path.join(cible, annee)
            os.makedirs(dossier_annee, exist_ok=True)

            # Définition du chemin cible final (gestion des faux doublons incluse via generer_nom_unique)
            chemin_cible_base = os.path.join(dossier_annee, nom_fichier)
            chemin_final = generer_nom_unique(chemin_cible_base) if est_faux_doublon else chemin_cible_base

            # En cas de collision fortuite dans le dossier de destination
            chemin_final = generer_nom_unique(chemin_final)

            # Copie finale
            if not copier_securise(chemin_source, chemin_final):
                with open(fichier_log, 'a', encoding='utf-8') as log:
                    log.write(f"ECHEC COPIE : {chemin_source}\n")

    print("\nOpération terminée.")

if __name__ == "__main__":
    main()