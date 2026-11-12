# Marchés Intelligence V3 — Solution locale Windows pour HTTP 888 (12 novembre 2026)

## Ce qui est réellement établi

- Un canary Github hébergé le 9 novembre atteignait FORM_READY / HTTP 200 avec l'URL publique exacte: https://github.com/said1994lk-eng/marches-v3-probe-lab/actions/runs/42723203468
- Deux contrôles indépendants le 12 novembre, depuis un GitHub Runner, recevaient HTTP **888** avant toute recherche:
  - Recherche publique: https://github.com/said1994lk-eng/marches-v3-probe-lab/actions/runs/43267252895
  - Page publique /pmmp/: https://github.com/said1994lk-eng/marches-v3-probe-lab/actions/runs/43267773877
- Le statut 888 n'est pas un code HTTP standard. Il ne prouve pas une panne globale ni une restriction IP spécifique.
- L'accès normal depuis un navigateur personnel peut différer de l'accès d'un navigateur automatisé sur le réseau GitHub. Cette différence doit être **testée**, pas supposée.
- Le portail officiel est publiquement consultable: https://www.marchespublics.gov.ma/pmmp/?lang=fr&page=plan

## Solution opérationnelle proposée — PC Windows de l'utilisateur

Utiliser le PC et la connexion réseau légitimes de l'utilisateur comme **poste de test local**. Aucun VPS, proxy, changement d'IP, CAPTCHA bypass, connexion au compte, téléchargement DCE, soumission ou pagination.

**Téléchargement du projet (une seule fois)**

1. Ouvrir https://github.com/said1994lk-eng/marches-v3-probe-lab
2. Cliquer **Code > Download ZIP** et extraire le dossier sur le PC.
3. Installer Python 3.12 depuis python.org si absent (cocher « Add Python to PATH » pendant l'installation).
4. Double-cliquer `scripts/01-Test-Connexion-Windows.cmd` depuis le dossier extrait.
5. Au premier démarrage, le programme crée `.venv`, installe uniquement `playwright==1.56.0` et Chromium, puis exécute une vérification publique à usage unique.
6. Le statut et le chemin du rapport s'affichent à l'écran. Retrouver `local-reports/local_connection_*.json`. **Ce rapport reste sur le PC** tant que l'utilisateur ne le partage pas lui-même.

**Interprétation**

- `FORM_READY_CONFIRMED_ONCE` et `form_ready=true`: formulaire accessible via Chromium automatisé sur ce réseau, une fois. Cela ne prouve ni la stabilité permanente ni la validité du filtre.
- `FORM_NOT_CONFIRMED` et statut 888 ou ERROR_PAGE: la route semble aussi inaccessible depuis ce poste avec le navigateur automatisé; ne pas relancer en boucle. Comparer seulement avec un navigateur personnel et demander des conditions d'accès aux responsables si besoin.
- `FORM_NOT_CONFIRMED`, `BLANK_OR_LOADING`: forme non établie; prendre note du rapport sans déduire « zéro marché ».
- Une réussite dans Google Chrome **ne garantit pas** que Chromium automatisé sera accepté.

**Deuxième étape uniquement si le test de connexion a réussi:**

L'utilisateur peut lancer volontairement `scripts/02-Fournitures-Une-Fiche-Windows.cmd` puis valider **O**. Cela fait au plus deux navigations publiques vers le formulaire, **un seul POST** Fournitures et **une seule consultation** de détail. Le rapport est `local-reports/local_category_*.json`. Ce script n'est pas exécuté par le premier test ni par un workflow cron.

- `DIRECT_SPOT_CHECK_ONLY` indique qu'une seule consultation publique a une catégorie source-officielle Fournitures; ce n'est PAS la preuve de toutes les annonces.
- `SAMPLED_CONFIRMED` exige les labels sources du nombre d'éléments explicitement contrôlés, et reste une preuve d'échantillon uniquement.
- Les autres statuts restent non confirmés ou contradictoires selon le code.

## Recommandation d'exploitation si la connexion locale réussit

- Garder GitHub Actions pour les tests offline et la traçabilité technique.
- Ne PAS installer GitHub self-hosted runner sur un poste de travail privé/public sans examen de sécurité préalable; une tâche Windows Task Scheduler pour un vérificateur local limité serait moins complexe **après** validation des étapes et autorisation.
- Ne pas lancer de scan quotidien, 100/page, pagination ou DCE tant que les règles d'accès et l'attestation Fournitures ne sont pas validées.
- Si le site impose des restrictions aux navigateurs automatisés, demander une autorisation ou une interface publique officielle à la TGR: `marchespublics@tgr.gov.ma`. Ne pas contourner ces restrictions.

## Contrôles de confidentialité

`scripts/local_connection_check.py` n'accepte que deux modes, masque les URLs et tout texte qui ressemble à du HTML ou à un secret, et n'écrit que du JSON agrégé. Les rapports et l'environnement sont ajoutés à `.gitignore`. Il ne transmet aucun rapport à GitHub. Aucun compte personnel n'est nécessaire pour les tests du formulaire public.

Ce plan ne garantit pas la résolution du statut 888; c'est une **méthode testable pour isoler l'environnement**, et un chemin d'exécution locale autorisé si la source est accessible.
