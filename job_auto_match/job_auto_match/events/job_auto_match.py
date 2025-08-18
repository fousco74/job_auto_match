import frappe
from google import genai
from google.genai import types
import httpx   # For fetching files from a URL


def auto_match(doc, method):
    # import frappe # Uncomment if frappe.get_doc is part of your environment
    # --- IMPORTANT: Replace 'YOUR_API_KEY' with your actual Gemini API Key ---
    # You can get your API key from the Google AI Studio: https://aistudio.google.com/app/apikey
    API_KEY = "AIzaSyBJPXFY6QE5wiHNkazfHD1-AoJF2GJaF9g"
    # Initialize the Gemini client with your API key
    client = genai.Client(api_key=API_KEY)
    # Assuming frappe.get_doc works in your environment to get the document object
    # If you are running this outside a Frappe/ERPNext environment, you might need to
    # mock or replace this line with how you obtain the resume_attachment URL.
    try:
        doc = frappe.get_doc("Job Applicant","HR-APP-2025-00001")
        # For demonstration, let's use a dummy object if frappe is not available
        #class MockDoc:
            #def __init__(self, resume_attachment):
                #self.resume_attachment = resume_attachment
        # Replace this with your actual attachment path from frappe if available
        # For testing, you can use a public PDF URL directly here:
        # resume_attachment_path = "https://www.africau.edu/images/default/sample.pdf"
        #resume_attachment_path = "files/your_resume_document.pdf" # This is a placeholder, replace with actual path from doc.resume_attachment
        #doc = MockDoc(resume_attachment_path)
        # Construct the full URL to the PDF
        # Make sure 'amoaman.com:8000' is the correct base URL for your attachments
        pdf_url = f"http://amoaman.com:8000/{doc.resume_attachment}"
        print(f"Attempting to fetch PDF from URL: {pdf_url}")

    
        try:
        doc = frappe.get_doc("Job Applicant","HR-APP-2025-00001")
        # For demonstration, let's use a dummy object if frappe is not available
        #class MockDoc:
            #def __init__(self, resume_attachment):
                #self.resume_attachment = resume_attachment
        # Replace this with your actual attachment path from frappe if available
        # For testing, you can use a public PDF URL directly here:
        # resume_attachment_path = "https://www.africau.edu/images/default/sample.pdf"
        #resume_attachment_path = "files/your_resume_document.pdf" # This is a placeholder, replace with actual path from doc.resume_attachment
        #doc = MockDoc(resume_attachment_path)
            # Construct the full URL to the PDF
        # Make sure 'amoaman.com:8000' is the correct base URL for your attachments
        pdf_url = f"http://amoaman.com:8000/{doc.resume_attachment}"
        print(f"Attempting to fetch PDF from URL: {pdf_url}")
            # Use httpx to fetch the PDF content from the URL
        try:
            response_httpx = httpx.get(pdf_url)
            response_httpx.raise_for_status() # Rai
            pdf_data = response_httpx.content # Get the PDF content as bytes
            print("PDF fetched successfully.")
        except httpx.RequestError as e:
            print(f"Error fetching PDF from URL: {e}")
            # If the PDF cannot be fetched, you might want to exit or handle it differently
            exit()
        except httpx.HTTPStatusError as e:
        print(f"HTTP Error fetching PDF: {e.response.status_code} - {e.response.text}")
        exit()
        prompt_text1 = """
    Tu es un expert en recrutement technique.

    À partir du texte extrait d’un CV (PDF en pièce jointe), analyse toutes les informations pertinentes sur le candidat.  
    Ta mission : structurer ces données en un fichier JSON parfaitement formaté, exhaustif et facile à lire, selon l’exemple ci-dessous.

    - Ignore la mise en page, concentre-toi uniquement sur le contenu utile.
    - Si une information n’est pas présente, indique "null" ou une valeur vide.
    - Utilise les mêmes champs et structure que l’exemple ci-dessous, sans rien ajouter ni retirer.

    Exemple de résultat attendu :
    {
    "candidate_info": {
        "name": "",
        "title": "",
        "age": "",
        "email": "",
        "phone": [],
        "location": "",
        "competences": [],
        "outils": [],
        "experience_professionnelle": [
        {
            "annee": "",
            "titre": "",
            "description": ""
        }
        ],
        "diplomes": [
        {
            "annee": "",
            "diplome": "",
            "institution": "",
            "level": ""
        }
        ],
        "annee_experience": null,
        "formation": ""
    }
    }

    Rends seulement le JSON final, sans explications, en français.
    """

    
    
    # Send the PDF data and the prompt to the Gemini API
        response1 = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    types.Part.from_bytes(
                    data=pdf_data,
                    mime_type='application/pdf',
                    ),
                    prompt_text1 # Your text prompt comes after the PDF
                ]
        )
        
        print("\n--- Gemini API Response ---")
        cv_data = response1.text
        print(cv_data)
        
        ficheDoc = frappe.db.get_doc('Job Opening',doc.job_title)
    
        # Get parent fields
        min_exp = ficheDoc.minimum_experience
        study_lvl = ficheDoc.study_level
    
        # Get child table records (these are lists of dicts/objects)
        skills = ficheDoc.skills  # e.g. list of skills rows
        outils = ficheDoc.outils  # e.g. list of outils rows
    
    
        print("competences :")
        for row in skills:
            print(row.skill)
        print("outils :")
    
        for row in outils:
        print(row.outil)
        print("min_exp :") 
        print(min_exp)
    
        print("study_level :")
        print(study_lvl)
        prompt_text2 = f"""
    Tu es un expert en recrutement.  
    Compare le profil du candidat ci-dessous (donné sous forme de JSON) aux exigences de la fiche de poste suivante (également donnée en JSON).

    Consigne :
    - Analyse précisément l’adéquation entre :  
    • compétences (skills)  
    • outils (outils)  
    • niveau d’études (study_level)  
    • expérience (minimum_experience)  
    - Attribue un score de correspondance sur 100, en fonction de la similarité et de la pertinence.
    - Rends uniquement ce JSON :

    {{
    "score_sur_100": <score>,
    "justification_breve": "<2 phrases maximum expliquant le score>"
    }}

    Voici le profil candidat :  
    {cv_data}

    Voici la fiche de poste :  
    {{
    "skills": {[row.skill for row in skills]},
    "outils": {[row.outil for row in outils]},
    "minimum_experience": {min_exp},
    "study_level": "{study_lvl}"
    }}

    Réponds uniquement avec le JSON demandé.
    """

        # Send the PDF data and the prompt to the Gemini API
        response2 = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    types.Part.from_bytes(
                    data=pdf_data,
                    mime_type='application/pdf',
                    ),
                    prompt_text2 # Your text prompt comes after the PDF
                ]
        )
        pourcentage = response2.text
        
        print("le candidat à ", pourcentage, "comme valeur ")
    except Exception as e:
    print(f"An unexpected error occurred: {e}")



