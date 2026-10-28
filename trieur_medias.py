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
    source = None
    cible = None
    with open(chemin_config, 'r', encoding='utf-8') as f:
        for ligne in f:
            ligne = ligne.strip()
            if not ligne or ligne.startswith('#'):
                continue
            if '=' in ligne:
                cle, valeur = ligne.split('=', 1)
                cle = cle.strip().upper()
                valeur = valeur.strip()
                if cle == 'SOURCE':
                    source = valeur
                elif cle == 'CIBLE':
                    cible = valeur
    return source, cible

def obtenir_annee_creation(chemin_fichier):
    extension = os.path.splitext(chemin_fichier)[1].lower()
    
    # 1. Tentative EXIF pour les images
    if extension in ['.jpg', '.jpeg', '.png', '.tiff']:
        try:
            with Image.open(chemin_fichier) as img:
                exif_data = img._getexif()
                if exif_data:
                    for tag_id, value in exif_data.items():
                        tag = TAGS.get(tag_id, tag_id)
                        if tag in ['DateTimeOriginal', 'DateTime']:
                            return value.split(':')[0]
        except Exception:
            pass

    # 2. Tentative MEDIA pour les vidéos
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

def copier_securise(source, cible, fichier_log):
    for tentative in range(2):
        try:
            shutil.copy2(source, cible)
            return True
        except Exception:
            time.sleep(0.5)
            
    # Échec après 2 tentatives
    with open(fichier_log, 'a', encoding='utf-8') as log:
        log.write(f"ECHEC COPIE : {source}\n")
    return False

def indexer_cible(dossier_cible):
    # Crée un dictionnaire des fichiers déjà présents dans la cible
    # Format : { "nom_fichier.ext": [taille1, taille2, ...] }
    index = {}
    if not os.path.exists(dossier_cible):
        return index
        
    print("Analyse de la CIBLE existante en cours...")
    for dossier_actuel, _, fichiers in os.walk(dossier_cible):
        for nom_fichier in fichiers:
            chemin = os.path.join(dossier_actuel, nom_fichier)
            try:
                taille = os.path.getsize(chemin)
                if nom_fichier in index:
                    if taille not in index[nom_fichier]:
                        index[nom_fichier].append(taille)
                else:
                    index[nom_fichier] = [taille]
            except Exception:
                pass
    return index

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
    
    # Création du fichier de log horodaté
    nom_log = datetime.now().strftime("log-%d%m%y_%H-%M-%S.txt")
    fichier_log = os.path.join(cible, nom_log)
    
    dossier_duplicat = os.path.join(cible, 'DUPLICAT')
    dossier_non_traite = os.path.join(cible, 'NON_TRAITE')
    os.makedirs(dossier_duplicat, exist_ok=True)
    os.makedirs(dossier_non_traite, exist_ok=True)

    # Indexation pour permettre les exécutions cumulatives
    fichiers_traites = indexer_cible(cible)

    for dossier_actuel, sous_dossiers, fichiers in os.walk(source):
        print(f"Traitement du dossier : {dossier_actuel}")
        
        for nom_fichier in fichiers:
            chemin_source = os.path.join(dossier_actuel, nom_fichier)
            
            try:
                taille_fichier = os.path.getsize(chemin_source)
            except Exception:
                # Impossible de lire la taille, fichier bloqué par le système
                continue
            
            est_vrai_doublon = False
            est_faux_doublon = False
            
            # Vérification des doublons grâce à l'index global
            if nom_fichier in fichiers_traites:
                if taille_fichier in fichiers_traites[nom_fichier]:
                    est_vrai_doublon = True
                else:
                    est_faux_doublon = True
                    fichiers_traites[nom_fichier].append(taille_fichier)
            else:
                fichiers_traites[nom_fichier] = [taille_fichier]

            if est_vrai_doublon:
                chemin_cible_base = os.path.join(dossier_duplicat, nom_fichier)
                chemin_final = generer_nom_unique(chemin_cible_base)
                copier_securise(chemin_source, chemin_final, fichier_log)
                continue

            # Extraction de l'année
            annee = obtenir_annee_creation(chemin_source)
            
            if not annee:
                # Aucun métadonnée valide ou format non supporté -> NON_TRAITE
                chemin_cible_base = os.path.join(dossier_non_traite, nom_fichier)
            else:
                # Métadonnées valides -> Dossier de l'année
                dossier_annee = os.path.join(cible, annee)
                os.makedirs(dossier_annee, exist_ok=True)
                chemin_cible_base = os.path.join(dossier_annee, nom_fichier)

            # Si c'est un faux doublon, on garantit l'ajout d'un suffixe
            if est_faux_doublon:
                chemin_final = generer_nom_unique(chemin_cible_base)
            else:
                # Ultime vérification système (sécurité anti-écrasement au cas où)
                chemin_final = generer_nom_unique(chemin_cible_base)

            copier_securise(chemin_source, chemin_final, fichier_log)

    print("\nOpération terminée.")

if __name__ == "__main__":
    main()