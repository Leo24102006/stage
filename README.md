# Stages informatique · Nord (59) & Pas-de-Calais (62)

Une page web qui regroupe chaque matin les offres de **stage en informatique** du 59 et du 62,
avec une étiquette de durée par rapport à un stage de **14 semaines** (BUT Informatique).

- **Sources** : API Adzuna et API Jooble, deux agrégateurs qui reprennent les offres de nombreux sites d'emploi.
  Le code France Travail est conservé mais inactif : l'API « Offres d'emploi » n'est plus en accès libre (voir data.gouv.fr).
  LinkedIn et Indeed ne sont pas inclus : Indeed n'a plus d'API publique de recherche, et LinkedIn interdit la collecte automatique.
- **Mise à jour** : tous les jours vers 6-7 h (heure de Paris), via GitHub Actions. Gratuit.
- **Affichage** : GitHub Pages. Gratuit.

## Ce que fait la page

- Filtres : recherche libre, département, durée, nouvelles offres seulement.
- Étiquettes de durée, détectées dans le texte de l'offre :
  - **Compatible** : la durée annoncée inclut 13-15 semaines (ex. « 3 mois », « 2 à 3 mois », « 14 semaines »)
  - **Proche** : 10 à 18 semaines (ex. « 4 mois »), ça peut se négocier
  - **Trop longue** : plus de 18 semaines (ex. « 6 mois »), masquée par défaut
  - **Trop courte** : moins de 10 semaines, masquée par défaut
  - **Non précisée** : rien trouvé dans le texte (le cas le plus fréquent)
  
  La phrase qui a servi à décider est affichée sous l'offre. **Vérifie toujours sur l'annonce.**
- Repères de niveau : « BUT / Bac+2-3 mentionné » (bon signe) ou « Vise aussi Bac+4/5 ».
- Onglets **À traiter / Postulées / Ignorées / Toutes**, et compteur de candidatures en bâtons en haut de page.
  Enregistrés dans ton navigateur uniquement (pas synchronisés entre ton PC et ton téléphone).
- Une offre qui disparaît des APIs reste affichée 7 jours, puis elle est retirée.

## Installation (environ 20 minutes)

### 1. Créer les clés d'API (gratuit)

**Adzuna** : compte sur <https://developer.adzuna.com>, puis Dashboard → API Access Details
(Application ID et Application Key).

**Jooble** : demande une clé sur <https://fr.jooble.org/api/about>. Prends bien la version **fr** :
une clé demandée sur jooble.org ne donne que des offres américaines. Offre gratuite : 100 requêtes par jour,
le script en utilise au plus 61.

Une seule source suffit pour démarrer : une source sans clé est simplement ignorée.

### 2. Mettre le projet sur GitHub

1. Crée un dépôt **public** (GitHub Pages est gratuit pour les dépôts publics).
   Le dépôt ne contient que le code et les offres publiques. Tes clés restent dans les secrets GitHub, jamais dans le code.
2. Envoie-y tous les fichiers de ce dossier.

### 3. Ajouter les clés dans GitHub

Dans le dépôt : **Settings → Secrets and variables → Actions → New repository secret**, crée :

| Nom du secret      | Valeur                           |
|--------------------|----------------------------------|
| `ADZUNA_APP_ID`    | Application ID Adzuna            |
| `ADZUNA_APP_KEY`   | Application Key Adzuna           |
| `JOOBLE_KEY`       | clé API Jooble (fr.jooble.org)   |

### 4. Activer la page

**Settings → Pages** → Source : *Deploy from a branch* → Branche `main`, dossier `/docs` → Save.
L'adresse s'affiche en haut de la page, du type `https://<ton-pseudo>.github.io/<nom-du-depot>/`.

### 5. Lancer la première mise à jour

**Actions → Mise à jour des offres → Run workflow**. Ensuite, la mise à jour tourne seule chaque matin.
Si une source a un problème (clé fausse, API indisponible), c'est écrit en haut de la page.

## Tester en local

```bash
python -m unittest discover -s tests -v
```

```bash
ADZUNA_APP_ID=... ADZUNA_APP_KEY=... JOOBLE_KEY=... python scripts/fetch.py
```

```bash
cd docs && python -m http.server 8000
```

Puis ouvre <http://localhost:8000>.

## Limites connues

- La détection de durée et le tri « informatique » reposent sur des mots-clés. Quelques offres hors sujet peuvent passer,
  et quelques bonnes offres peuvent être manquées.
- Adzuna et Jooble ne renvoient qu'un extrait de la description, donc la durée est le plus souvent « non précisée ».
- Le département vient d'Adzuna, ou du nom de la ville pour Jooble (liste des communes du 59 et du 62 dans
  `scripts/communes_59_62.json`). Les villes au nom ambigu (Montreuil, Saint-Aubin…) sont écartées.
- Les plateformes d'école (JobTeaser, etc.) et les sites carrière des entreprises ne sont pas couverts.
