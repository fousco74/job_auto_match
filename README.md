# RecrutIA — v1.0.0

Automatisation du recrutement pour ERPNext/HRMS avec scoring IA (Google Gemini) et intégration Testlify.

## Fonctionnement

```
Candidature soumise
      │
      ▼
Validation CV (format PDF/Word + dédoublonnage)
      │
      ▼
Extraction structurée du CV par Gemini IA
      │
      ▼
Scoring CV ↔ Fiche de poste (0–100)
      │
      ├─ Score ≥ seuil qualification ──► Invitation test Testlify
      │                                          │
      │                               Webhook "completed"
      │                                          │
      │                               Score ≥ seuil test ──► Statut "après test"
      │                               Score < seuil test ──► Email rejet
      │
      └─ Score < seuil qualification ──► Email "non retenu"
```

---

## Prérequis

- Frappe Framework ≥ 15
- ERPNext + **HRMS** installés
- Python ≥ 3.11
- LibreOffice installé sur le serveur (conversion DOC → PDF)
- Compte Google AI Studio (clé Gemini)
- Compte Testlify (optionnel)

---

## Installation

```bash
# 1. Ajouter l'app
bench get-app job_auto_match https://github.com/AMOAMAN/job_auto_match

# 2. Installer sur le site
bench --site <nom_du_site> install-app job_auto_match

# 3. Migrer (applique fixtures et migrations)
bench --site <nom_du_site> migrate

# 4. Construire les assets
bench build --app job_auto_match

# 5. Redémarrer
bench restart
```

---

## Paramétrage

### 1. Job Matching Integration Settings

Aller dans : **RecrutIA → Job Matching Integration Settings**

#### Gemini IA

| Champ | Obligatoire | Description |
|-------|-------------|-------------|
| Clé API Gemini | Oui | Obtenue sur [aistudio.google.com](https://aistudio.google.com) |
| URL du site | Non | URL de base pour les liens fichiers (ex: `https://erp.monentreprise.com`) |

#### Testlify

| Champ | Description |
|-------|-------------|
| URL de base Testlify | Ex: `https://api.testlify.com` |
| Token API Testlify | Token Bearer pour l'API |
| Endpoint invitation | Ex: `v1/testlify_candidate_invite` |
| Token webhook | Token de sécurité reçu dans `X-Webhook-Token` |
| Utilisateur de service | Utilisateur Frappe pour les webhooks (défaut: `Administrator`) |

#### Seuils et statuts

| Champ | Défaut | Description |
|-------|--------|-------------|
| Seuil qualification IA | 70 | Score minimum pour inviter au test |
| Seuil réussite test | 40 | Score Testlify minimum pour valider |
| Score max avant rejet direct | 40 | En dessous = rejet immédiat |
| Statut qualifié | `En Cours de qualification` | Score ≥ seuil IA |
| Statut non qualifié | `Top Profil` | Score entre rejet et seuil |
| Statut après test | `Accepté` | Test Testlify réussi |
| Statut rejeté | `Rejecté` | Score ≤ seuil rejet |
| Statut erreur Gemini | `Open` | En cas d'indisponibilité IA |

#### Emails

Deux sections configurables avec templates Jinja2 :

**Non retenu (après scoring IA) :**
```
{{ applicant_name }}, {{ job_title }}, {{ score }}, {{ justification }}
```

**Rejeté (après test Testlify) :**
```
{{ applicant_name }}, {{ job_title }}, {{ score }}
```

---

### 2. Configurer les offres (Job Opening)

Pour chaque offre, renseigner dans l'onglet dédié :

| Champ | Description |
|-------|-------------|
| `custom_active_cv_auto_matching` | Activer le matching automatique |
| `custom_skills` | Compétences requises |
| `custom_outils` | Outils/Technologies requis |
| `custom_minimum_experience` | Années d'expérience minimales |
| `custom_study_level` | Niveau d'études requis |
| `custom_assessments` | Assessments Testlify (colonne `id` = assessmentId Testlify) |

> L'`id` de la table `custom_assessments` est la clé de liaison avec Testlify.
> Il doit correspondre exactement à l'`assessmentId` de votre workspace.

---

### 3. Webhook Testlify

Dans votre interface Testlify → **Settings → Webhooks** :

- **URL** : `https://<votre-site>/api/v2/method/job_auto_match.api.completed`
- **Événement** : `candidate.completed`
- **Header** : `X-Webhook-Token: <votre_token_webhook>`

---

### 4. Permissions

L'utilisateur de service (`webhook_service_user`) doit avoir les droits **Write** sur `Job Applicant`.

---

## Statuts Job Applicant

```
Open
 ├── Vivrier                   (vivier, à traiter)
 ├── Top Profil                (profil intéressant)
 ├── En Cours de qualification (test Testlify envoyé)
 ├── Accepté                   (test réussi)
 └── Rejecté                   (rejet IA ou test)
```

---

## Mise à jour des fixtures

Après modification de Custom Fields, Property Setters ou Workflow :

```bash
bench --site <nom_du_site> export-fixtures --app job_auto_match
git add job_auto_match/fixtures/
git commit -m "chore: mise à jour fixtures"
```

---

## Désinstallation

```bash
bench --site <nom_du_site> uninstall-app job_auto_match
bench --site <nom_du_site> migrate
```

---

## Licence

MIT — AMOAMAN
