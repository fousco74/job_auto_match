import frappe
import httpx
import json
import requests
from google import genai
from google.genai import types
from frappe.utils.file_manager import get_file_path
import pathlib
from urllib.parse import urljoin


def send_candidate_not_matching_email(doc):
    try:
    
        settings = frappe.get_single('Job Matching Integration Settings')


        # Debug : affichage des champs clés
        frappe.logger().info(f"[NOT_MATCH_MAIL] doc.email_id: {getattr(doc, 'email_id', None)}")
        frappe.logger().info(f"[NOT_MATCH_MAIL] applicant_name: {getattr(doc, 'applicant_name', None)}")
        frappe.logger().info(f"[NOT_MATCH_MAIL] job_title: {getattr(doc, 'job_title', None)}")
        frappe.logger().info(f"[NOT_MATCH_MAIL] score: {getattr(doc, 'matching_score', None)}")
        frappe.logger().info(f"[NOT_MATCH_MAIL] justification: {getattr(doc, 'justification', None)}")

        # Vérification du champ email_id
        recipients = [getattr(doc, 'email_id', None)]
        if not recipients[0]:
            frappe.logger().error("[NOT_MATCH_MAIL] Aucun destinataire renseigné !")
            return

        context = {
            "applicant_name": getattr(doc, "applicant_name", ""),
            "job_title": getattr(doc, "job_title", ""),
            "score": getattr(doc, "matching_score", ""),
            "justification": getattr(doc, "justification", "")
        }
        
        subject = frappe.render_template(settings.candidate_not_matching_subject, context) or frappe._("Votre candidature n'est pas retenue pour le moment")
        header = frappe.render_template(settings.candidate_not_matching_email_header, context) or frappe._("Information sur votre candidature")
        body = frappe.render_template(settings.candidate_not_matching_email_template, context) or frappe.get_template('candidate_not_matching.html').render(context)


        frappe.sendmail(
            recipients=recipients,
            subject=subject,
            content=body,     
            header=header
        )

        frappe.logger().info(f"[NOT_MATCH_MAIL] Email envoyé à {recipients[0]} avec succès.")

    except Exception as e:
        frappe.logger().error(f"[NOT_MATCH_MAIL] ERREUR d'envoi du mail: {e}", exc_info=True)



def send_candidate_invite(doc, assessments: list) -> list:
    results = []
    try:
        # 1) Récupérer et afficher les settings
        settings = frappe.get_single('Job Matching Integration Settings')
        base = settings.testlify_base_url.rstrip('/') + '/'
        path = settings.testlify_candidate_invite.lstrip('/')
        api_url = urljoin(base, path)
        token = settings.testlify_token

        print("[INVITE] ▶️ Testlify API URL :", api_url)
        print(f"[INVITE] ▶️ Candidate : {doc.first_name} {doc.last_name} <{getattr(doc, 'email_id', None)}>")

        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        print("[INVITE] ▶️ Headers :", headers)

        # 2) Boucler sur chaque assessment
        for assessment in assessments:
            # Extraire l'ID et le nom
            if isinstance(assessment, dict):
                assessment_id = assessment.get('id')
                assessment_name = assessment.get('assessment_name')
            else:
                assessment_id = getattr(assessment, 'id', None)
                assessment_name = getattr(assessment, 'assessment_name', None)

            print(f"[INVITE] ➡️ Traitement assessment_id={assessment_id}, name={assessment_name}")

            if not assessment_id:
                print(f"[INVITE] ⚠️ Skip empty assessment id for {assessment!r}")
                continue

            # 3) Préparer le payload et l'afficher
            payload = {
                'candidateInvites': [{
                    'firstName': doc.first_name,
                    'lastName': doc.last_name,
                    'email': doc.email_id,
                }],
                'assessmentId': assessment_id,
            }
            print("[INVITE] 📤 Payload :", json.dumps(payload, indent=2))

            # 4) Envoyer la requête et afficher response/status
            response = requests.post(api_url, json=payload, headers=headers, timeout=30)
            print(f"[RESPONSE] 📥 HTTP RESPONSE :  {response} reçu")
            try:
                print("[INVITE] 📥 Response JSON :", response.json())
            except ValueError:
                print("[INVITE] 📥 Response text :", response.text)

            status = response.status_code
            body = {}
            try:
                body = response.json()
            except ValueError:
                pass

            # 5) Gestion du code HTTP
            if status == 200:
                print(f"[INVITE] ✅ Succès pour {assessment_id}")
                if hasattr(doc, "assessments"):
                    doc.append("assessments", {
                        "assessment_name": assessment_name,
                        "assessment_id": assessment_id,
                        "sent": True
                    })
                    doc.save(ignore_permissions=True)
                    frappe.db.commit()
                results.append({"assessment_id": assessment_id, "status": "success"})

            elif status == 404:
                msg = body.get('error', {}).get('message', response.text)
                print(f"[INVITE] ⚠️ Not Found (404) pour {assessment_id} : {msg}")
                results.append({"assessment_id": assessment_id, "status": "not_found", "message": msg})

            elif status == 403:
                msg = body.get('error', {}).get('message', response.text)
                print(f"[INVITE] 🚫 Forbidden (403) pour {assessment_id} : {msg}")
                results.append({"assessment_id": assessment_id, "status": "forbidden", "message": msg})

            else:
                msg = body.get('error', {}).get('message') or body.get('message') or f"HTTP {status}"
                print(f"[INVITE] ❗️ Error {status} pour {assessment_id} : {msg}")
                results.append({"assessment_id": assessment_id, "status": "error", "message": msg})

        print("[INVITE] 🏁 Résultats finaux :", results)

    except Exception as e:
        print(f"[INVITE] 💥 ERREUR GLOBALE : {e}")
        frappe.log_error(message=str(e), title="[INVITE] Fatal Error")
        results.append({"status": "fatal_error", "message": str(e)})

    return results



def process_job_applicant_matching(applicant_name):
    settings = frappe.get_single('Job Matching Integration Settings')
    API_KEY = settings.gemini_api_key
    client = genai.Client(api_key=API_KEY)
    qualified_status = settings.status_qualified
    status_not_qualified = settings.status_not_qualified
    qualification_score_threshold = settings.qualification_score_threshold
    doc = frappe.get_doc("Job Applicant", applicant_name)

    # --- PARAMS ---
    site_url = settings.site_url

    if not doc.resume_attachment:
        raise ValueError("Le candidat n'a pas de pièce jointe 'resume_attachment'")
    pdf_url = f"{site_url}/{doc.resume_attachment}"

    file_path = get_file_path(doc.resume_attachment)
    if not pathlib.Path(file_path).exists():
        raise FileNotFoundError(f"Fichier introuvable: {file_path}")

    with open(file_path, "rb") as f:
        pdf_data = f.read()

    # --- GEMINI EXTRACTION DU CV ---
    prompt1 = """
    Tu es un expert en recrutement technique.
    À partir du texte extrait d’un CV (PDF en pièce jointe), analyse toutes les informations pertinentes sur le candidat.
    Ta mission : structurer ces données en un fichier JSON parfaitement formaté, exhaustif et facile à lire, selon l’exemple ci-dessous.
    - Ignore la mise en page, concentre-toi uniquement sur le contenu utile.
    - Si une information n’est pas présente, indique une valeur estimée, ou "null"/vide si vraiment impossible.
    - Utilise STRICTEMENT la structure et les champs de l’exemple ci-dessous, sans rien ajouter ni retirer.

    Exemple de résultat attendu :
    {
    "candidate_info": {
        "first_name": "Nom",
        "last_name": "prénom",
        "title": "Titre/Profession",
        "age": "32",
        "email": "exemple@email.com",
        "phone": ["+22501234567"],
        "location": "Abidjan",
        "competences": ["Developpement web", "Gestion de projet"],
        "outils": ["Python", "java"],
        "experience_professionnelle": [
        {
            "annee": "2023",
            "titre": "Développeur",
            "description": "Développement de modules Frappe"
        }
        ],
        "diplomes": [
        {
            "annee": "2023",
            "diplome": "Master Informatique",
            "institution": "Université de Cocody",
            "level": "Graduate or Under Graduate or Post Graduate"
        }
        ],
        "annee_experience": 5,
        "niveau_etude": "BAC+3"
    }
    }
    le level doit etre entre ces trois valeurs( Graduate, Under Graduate, Post Graduate)
    Rends seulement le JSON final, sans explications, en français, et renseigne une valeur estimée partout, même si tu dois deviner logiquement.
    """

    response1 = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            types.Part.from_bytes(data=pdf_data, mime_type='application/pdf'),
            prompt1
        ]
    )
    try:
        candidate_json = json.loads(response1.text)
    except:
        candidate_json = json.loads(response1.text.strip("```json\n").strip("```").strip())

    print("=== CV STRUCTURÉ ===")
    print(json.dumps(candidate_json, indent=2, ensure_ascii=False))

    # --- MISE À JOUR DU CANDIDAT ---
    info = candidate_json.get("candidate_info", {})
    if info.get("age"):
        doc.old = info["age"]
    if info.get("first_name"):
        doc.first_name = info["first_name"]
    if info.get("last_name"):
        doc.last_name = info["last_name"]
    if info.get("annee_experience"):
        doc.minimum_experience = info["annee_experience"]
    if info.get("niveau_etude"):
        doc.study_level = info["niveau_etude"]

    if hasattr(doc, "outils"):
        doc.set("outils", [])
        for outil in info.get("outils", []):
            doc.append("outils", {"outil_name": outil})

    if hasattr(doc, "skills"):
        doc.set("skills", [])
        for skill in info.get("competences", []):
            doc.append("skills", {"skill_name": skill})
    
        # Gestion des expériences
    if hasattr(doc, "experiences"):
        doc.set("experiences", [])
        
        last_annee = ""
        last_title = ""
        last_description = ""

        for experience in info.get("experience_professionnelle", []):
            annee = experience.get("annee", last_annee)
            title = experience.get("titre", last_title)
            description = experience.get("description", last_description)

            # Mise à jour des valeurs précédentes si la clé existe et n'est pas vide
            if experience.get("annee"):  
                last_annee = experience["annee"]
            if experience.get("titre"):
                last_title = experience["titre"]
            if experience.get("description"):
                last_description = experience["description"]

            doc.append("experiences", {
                "annee": annee,
                "title": title,
                "description": description
            })

    # Gestion des diplômes
    if hasattr(doc, "diplomes"):
        doc.set("diplomes", [])
        
        last_annee = ""
        last_qualification = ""
        last_institution = ""
        last_level = ""

        for diplome in info.get("diplomes", []):
            annee = diplome.get("annee", last_annee)
            qualification = diplome.get("diplome", last_qualification)
            institution = diplome.get("institution", last_institution)
            level = diplome.get("level", last_level)

            # Mise à jour des dernières valeurs si elles sont présentes
            if diplome.get("annee"):
                last_annee = diplome["annee"]
            if diplome.get("diplome"):
                last_qualification = diplome["diplome"]
            if diplome.get("institution"):
                last_institution = diplome["institution"]
            if diplome.get("level"):
                last_level = diplome["level"]

            doc.append("diplomes", {
                "annee": annee,
                "qualification": qualification,
                "institution": institution,
                "level": level
            })


    doc.save(ignore_permissions=True)
    frappe.db.commit()

    # --- RÉCUP FICHE POSTE & MATCHING GEMINI ---
    fiche = frappe.get_doc("Job Opening", doc.job_title or "")
    job_json = {
        "skills": [r.skill for r in fiche.skills],
        "outils": [r.outil for r in fiche.outils],
        "minimum_experience": fiche.minimum_experience,
        "study_level": fiche.study_level,
        "fiche" : fiche.description
    }

    
    
    prompt2 = f"""
        Tu es un expert en recrutement technique.
        Compare le profil du candidat (JSON) à la fiche de poste (JSON) en tenant compte des PROJETS réalisés, des COMPÉTENCES, des OUTILS/TECHNOS et de l’EXPÉRIENCE. Analyse précise et factuelle, sans inventer d’informations.

        Barème (total = 100) :
        - Compétences (skills)  : correspondance avec les compétences requises (priorité aux indispensables). Bonus si démontrées dans des projets similaires au poste.
        - Outils (outils)  : correspondance exacte ou équivalente (synonymes/acronymes/versions proches acceptés si pertinents : p.ex. JS=JavaScript, React=React.js, Node=Node.js).
        - Niveau d’études (study_level) : adéquation au niveau requis (équivalences acceptées : Licence=Bachelor, Master=MSc/MS, Bac+5=M2, etc.).
        - Expérience (minimum_experience) : années pertinentes par rapport au domaine du poste ; si < minimum, pénalité proportionnelle ; si > minimum, pas de bonus automatique sans pertinence.
        -Fiche (fiche) : description de la fiche de note comprenant : Principales Missions, Activités Principales , Formations et Expériences Souhaitées

        Procédure d’évaluation :
        - Lis et normalise (minuscules, enlève pluriels simples/accents, tolère fautes minimes).
        -compare chaque elements (projet, Principales Missions , Activités Principales , Formations et Expériences Souhaitées, Expérience, Niveau d’études, Outils, Compétences ) de la fiche et du cv
        - Si la fiche distingue must-have vs nice-to-have, priorise must-have.
        - Prends en compte le contexte des projets (secteur, responsabilités, impact) pour juger la pertinence.
        - Si un critère est absent dans la fiche (ex. pas de study_level), redistribue son poids proportionnellement sur les autres critères.
        - N’utilise aucune source externe. Toute info manquante est considérée non satisfaite.
        - Calcule un score sur 100 (arrondi à l’entier le plus proche).

        Contraintes de sortie :
        - Réponds UNIQUEMENT avec ce JSON (aucun texte autour).
        - "score" : entier 0–100.
        - "justification" : 1 à 3 phrases maximum, en français, résumant objectivement les principaux points forts/faiblesses.

        Profil candidat :
        {json.dumps(candidate_json, ensure_ascii=False)}

        Fiche de poste :
        {json.dumps(job_json, ensure_ascii=False)}

        Rends UNIQUEMENT ce JSON :
        {{
        "score": <entier entre 0 et 100>,
        "justification": "<5 phrases maximum expliquant le score>"
        }}
        """


    response2 = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            types.Part.from_bytes(data=pdf_data, mime_type='application/pdf'),
            prompt2
        ]
    )
    try:
        matching_score = json.loads(response2.text)
    except:
        matching_score = json.loads(response2.text.strip("```json\n").strip("```").strip())
        print(" ERROR ERROR ERROR ERROR ERROR ERROR ERROR ERROR ERROR ERROR ERROR")

    if isinstance(matching_score, dict):
        score = matching_score.get("score", 0)
        doc.matching_score = score
        doc.justification = matching_score.get("justification")

        # Normalisation du score (0-100) vers (0.0-1.0)
        rating = score / 100

        # Forcer la plage 0.0 - 1.0
        rating = max(0.0, min(1.0, rating))

        # Formatage en DECIMAL(3,2) pour MariaDB
        doc.applicant_rating = float(f"{rating:.2f}")




        doc.status = qualified_status if score >= qualification_score_threshold else status_not_qualified
        doc.save(ignore_permissions=True)
        frappe.db.commit()

        
    if matching_score.get("score", 0) >= 70:
        send_candidate_invite(doc, fiche.assessments)
    else:
        send_candidate_not_matching_email(doc)

    print("=== SCORE DE MATCHING ===")
    print(json.dumps(matching_score, indent=2, ensure_ascii=False))