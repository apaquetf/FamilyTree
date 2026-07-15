# Arbre familial

Site interactif (arbre + carte des lieux) généré à partir d'un export Gramps.

## Comment ça marche

```
Gramps (export GEDCOM)
        │
        ▼
data/raw/family.ged  ──┐
data/places.json     ──┼──►  sync/gedcom_to_json.py  ──►  site/data/*.json  ──►  site/index.html
(coordonnées connues)  ┘
```

1. Vous exportez votre arbre depuis Gramps au format GEDCOM (`.ged`), en cochant
   l'option **"ne pas inclure les personnes marquées privées"** dans les
   options d'export. Ça garde tout le filtrage de confidentialité côté
   Gramps — le script ne fait aucun tri lui-même.
2. Vous remplacez `data/raw/family.ged` par ce nouvel export et vous poussez
   sur `main`.
3. GitHub Actions lance automatiquement `sync/gedcom_to_json.py`, qui
   régénère `site/data/tree.json`, `site/data/marriages.json` et
   `site/data/places.json`, puis republie le site sur GitHub Pages.
4. Aucune étape manuelle après l'export — pas de script à lancer soi-même.

## Coordonnées des lieux

Le script ne géocode rien automatiquement. Il regarde, pour chaque lieu de
naissance/décès rencontré :

1. si Gramps a déjà des coordonnées enregistrées pour ce lieu (elles sortent
   alors dans le GEDCOM et sont prioritaires) ;
2. sinon, si `data/places.json` a déjà une entrée pour ce nom de lieu exact.

Tout lieu qui n'a ni l'un ni l'autre apparaît dans le journal de l'action
GitHub ("X lieu(x) sans coordonnées") mais n'empêche rien de fonctionner —
il n'apparaîtra simplement pas sur la carte. Deux façons de corriger ça :

- Remplir les coordonnées du lieu directement dans Gramps (solution durable —
  ça ne demande plus rien ensuite).
- Ajouter l'entrée à la main dans `data/places.json` :
  `"Nom du lieu": [latitude, longitude]`.

Le fichier `data/places.json` s'auto-enrichit aussi : si Gramps fournit des
coordonnées pour un lieu qui n'y était pas encore, l'action les y ajoute
automatiquement à chaque synchronisation.

## Lancer en local

Les navigateurs bloquent `fetch()` sur des fichiers ouverts directement
(`file://`). Il faut donc un petit serveur local :

```bash
python3 sync/gedcom_to_json.py data/raw/family.ged --places data/places.json --out site/data
cd site
python3 -m http.server 8000
# puis ouvrir http://localhost:8000
```

## Activer GitHub Pages

Dans les paramètres du dépôt : **Settings → Pages → Source → GitHub Actions**.
Le premier push sur `main` avec ce workflow suffit ensuite à publier le site.

## Structure

```
data/
  raw/family.ged      export Gramps le plus récent (à remplacer à chaque sync)
  places.json         coordonnées connues, s'enrichit automatiquement
sync/
  gedcom_to_json.py   parseur GEDCOM → JSON
site/
  index.html          le site (arbre + carte)
  data/               généré automatiquement, ne pas éditer à la main
.github/workflows/
  build-and-deploy.yml
```
