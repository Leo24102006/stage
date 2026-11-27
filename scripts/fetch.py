#!/usr/bin/env python3
"""Récupère les offres de stage en informatique dans le Nord (59) et le
Pas-de-Calais (62) depuis les APIs officielles France Travail et Adzuna,
les trie, et écrit docs/offres.json (lu par la page docs/index.html).

Clés lues dans les variables d'environnement (secrets GitHub) :
  FT_CLIENT_ID, FT_CLIENT_SECRET     -> France Travail (francetravail.io)
  ADZUNA_APP_ID, ADZUNA_APP_KEY      -> Adzuna (developer.adzuna.com)
Une source sans clés est simplement ignorée.

Aucune dépendance : uniquement la bibliothèque standard de Python.
"""

from __future__ import annotations

import html
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "offres.json"

DEPARTEMENTS = {"59": "Nord", "62": "Pas-de-Calais"}
# Une offre qui n'apparaît plus dans les APIs depuis ce nombre de jours est retirée.
RETIRER_APRES_JOURS = 7
# Une offre est marquée « nouvelle » pendant ce nombre de jours.
NOUVELLE_PENDANT_JOURS = 3
EXTRAIT_MAX = 700

FT_TOKEN_URL = "https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=%2Fpartenaire"
FT_SEARCH_URL = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"
FT_OFFRE_URL = "https://candidat.francetravail.fr/offres/recherche/detail/"
ADZUNA_URL = "https://api.adzuna.com/v1/api/jobs/fr/search/{page}"

USER_AGENT = "stages-59-62/1.0 (recherche de stage personnelle)"


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------

class HttpError(Exception):
    def __init__(self, status: int):
        super().__init__(f"HTTP {status}")
        self.status = status


def http(method: str, url: str, params: dict | None = None, form: dict | None = None,
         headers: dict | None = None, timeout: int = 30):
    """Renvoie (status, json|None). Les clés ne sont jamais affichées en cas d'erreur."""
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    body = urllib.parse.urlencode(form).encode() if form else None
    h = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    h.update(headers or {})
    for tentative in range(3):
        req = urllib.request.Request(url, data=body, method=method, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
                return r.status, (json.loads(raw) if raw.strip() else None)
        except urllib.error.HTTPError as e:
            if e.code == 429 and tentative < 2:  # trop de requêtes : on attend et on réessaie
                time.sleep(int(e.headers.get("Retry-After", "5") or 5))
                continue
            raise HttpError(e.code) from None
        except urllib.error.URLError as e:
            if tentative < 2:
                time.sleep(3)
                continue
            raise HttpError(0) from None
    raise HttpError(0)


# --------------------------------------------------------------------------
# Analyse du texte
# --------------------------------------------------------------------------

def norm(texte: str) -> str:
    """Minuscules, sans accents, espaces simplifiés."""
    t = unicodedata.normalize("NFKD", texte or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t.lower()).strip()


def nettoyer_html(texte: str) -> str:
    t = re.sub(r"<[^>]+>", " ", texte or "")
    return re.sub(r"\s+", " ", html.unescape(t)).strip()


RE_STAGE = re.compile(r"\b(stage|stages|stagiaire|stagiaires|internship|intern)\b")
RE_ALTERNANCE = re.compile(r"\b(alternance|alternant|alternante|apprenti|apprentie|apprentissage|contrat pro|contrat de professionnalisation)\b")
RE_INFO_TITRE = re.compile(
    r"(develop|informati|logiciel|software|\bweb\b|full ?-?stack|front ?-?end|back ?-?end|devops|"
    r"\bdata\b|donnees|cyber|reseau|systemes? d.information|\bsi\b|\bit\b|cloud|python|\bjava\b|"
    r"javascript|typescript|\bphp\b|react|angular|vue\.?js|symfony|laravel|\.net|\bc#|\bc\+\+|mobile|"
    r"android|\bios\b|\bia\b|intelligence artificielle|machine learning|\bqa\b|testeur|test logiciel|"
    r"technicien support|support informatique|helpdesk|administrat\w* (systeme|reseau)|\bsql\b|"
    r"base de donnees|\bbi\b|programm|code|\bux\b|\bui\b|integrat\w* web|wordpress|ingenieur logiciel)"
)
RE_PAS_INFO_TITRE = re.compile(
    r"(marketing|commercial|commerciale|communication|vente|vendeu|comptab|ressources humaines|\brh\b|"
    r"juridique|achat|logistique|assistant\w* (de direction|administrati)|community manager|graphis|"
    r"chef de rayon|caisse|serveu|cuisin)"
)
RE_NIVEAU_BUT = re.compile(r"(\bBUT\b|\bDUT\b|\bIUT\b|[Bb]ac ?\+ ?[23]\b|[Ll]icence (pro|professionnelle|3|informatique)|[Bb]achelor)")
RE_NIVEAU_HAUT = re.compile(r"\b(bac ?\+ ?[45]|master|m1|m2|ecole d.ingenieurs?|cycle ingenieur|eleve ingenieur|fin d.etudes)\b")

NOMBRES = {"un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7, "huit": 8}
_N = r"(\d{1,2}|un|une|deux|trois|quatre|cinq|six|sept|huit)"
RE_DUREE_PLAGE = re.compile(_N + r"\s*(?:a|-|/|ou|et)\s*" + _N + r"\s*(semaines?|mois)\b")
RE_DUREE_SIMPLE = re.compile(_N + r"\s*(semaines?|mois)\b")
RE_CONTEXTE_DUREE = re.compile(r"(stage|duree|periode|pendant)")


def _nombre(s: str) -> int:
    return int(s) if s.isdigit() else NOMBRES[s]


def _semaines(n: int, unite: str) -> float:
    return n * 4.35 if unite.startswith("mois") else float(n)


def analyser_duree(texte: str) -> dict:
    """Cherche la durée du stage dans le texte (titre + description).

    Ne retient une durée que si elle est proche des mots « stage », « durée »,
    « période »..., pour éviter « 6 mois d'expérience ». Renvoie la catégorie et
    l'extrait trouvé, pour que l'utilisateur puisse vérifier lui-même.
    """
    t = norm(texte)
    for regex in (RE_DUREE_PLAGE, RE_DUREE_SIMPLE):
        for m in regex.finditer(t):
            avant = t[max(0, m.start() - 60):m.start()]
            apres = t[m.end():m.end() + 25]
            if not RE_CONTEXTE_DUREE.search(avant):
                continue
            if re.match(r"\s*(d.experience|minimum d.experience|d.anciennete)", apres):
                continue
            if regex is RE_DUREE_PLAGE:
                a, b, unite = m.group(1), m.group(2), m.group(3)
                mini, maxi = _semaines(_nombre(a), unite), _semaines(_nombre(b), unite)
            else:
                n, unite = m.group(1), m.group(2)
                mini = maxi = _semaines(_nombre(n), unite)
            if mini > maxi:
                mini, maxi = maxi, mini
            if mini == 0 or maxi > 60:
                continue
            if mini <= 15 and maxi >= 13:
                categorie = "compatible"
            elif mini > 18:
                categorie = "trop_longue"
            elif maxi < 10:
                categorie = "trop_courte"
            else:
                categorie = "proche"
            debut = max(0, m.start() - 25)
            if debut > 0 and " " in t[debut:m.start()]:
                debut = t.index(" ", debut) + 1  # commencer sur un mot entier
            return {"categorie": categorie, "extrait": t[debut:m.end()].strip()}
    return {"categorie": "non_precisee", "extrait": ""}


def est_stage(titre: str, description: str, contrat: str) -> bool:
    nt, nd, nc = norm(titre), norm(description), norm(contrat)
    if RE_STAGE.search(nt):
        return True
    if RE_ALTERNANCE.search(nt):
        return False  # alternance uniquement
    # « stage » seulement dans la description : on refuse les vrais contrats de travail
    if any(x in nc for x in ("cdi", "cdd", "interim", "mission", "permanent", "contract", "saisonnier")):
        return False
    return bool(RE_STAGE.search(nd))


def est_informatique(titre: str, description: str, rome: str = "", categorie: str = "") -> bool:
    nt = norm(titre)
    if RE_PAS_INFO_TITRE.search(nt) and not re.search(r"(develop|informati|logiciel|software|data|devops|cyber)", nt):
        return False
    if (rome or "").upper().startswith("M18"):  # ROME M18xx = métiers de l'informatique
        return True
    if RE_INFO_TITRE.search(nt):
        return True
    if categorie == "it-jobs":
        return True
    return False


def niveau(texte: str) -> list[str]:
    t = norm(texte)
    tags = []
    if RE_NIVEAU_BUT.search(texte):  # texte d'origine : « BUT » en majuscules, pas « dans le but de »
        tags.append("BUT / Bac+2-3 mentionné")
    if RE_NIVEAU_HAUT.search(t):
        tags.append("Vise aussi Bac+4/5")
    return tags


def cle_doublon(titre: str, entreprise: str) -> str:
    return re.sub(r"[^a-z0-9]", "", norm(titre)) + "|" + re.sub(r"[^a-z0-9]", "", norm(entreprise))


# --------------------------------------------------------------------------
# Sources
# --------------------------------------------------------------------------

def fetch_france_travail() -> tuple[list[dict], str]:
    cid, secret = os.environ.get("FT_CLIENT_ID"), os.environ.get("FT_CLIENT_SECRET")
    if not cid or not secret:
        return [], "non configurée (clés manquantes)"
    try:
        _, tok = http("POST", FT_TOKEN_URL, form={
            "grant_type": "client_credentials",
            "client_id": cid,
            "client_secret": secret,
            "scope": "api_offresdemploiv2 o2dsoffre",
        }, headers={"Content-Type": "application/x-www-form-urlencoded"})
    except HttpError as e:
        return [], f"erreur d'authentification ({e}) : vérifie les clés et l'abonnement à « Offres d'emploi v2 »"
    auth = {"Authorization": f"Bearer {tok['access_token']}"}

    brutes: dict[str, dict] = {}
    for dep in DEPARTEMENTS:
        for mot in ("stage", "stagiaire"):
            for debut in range(0, 1150, 150):
                try:
                    status, data = http("GET", FT_SEARCH_URL, params={
                        "departement": dep, "motsCles": mot, "range": f"{debut}-{debut + 149}", "sort": 1,
                    }, headers=auth)
                except HttpError as e:
                    print(f"  France Travail {dep}/{mot} : {e}", file=sys.stderr)
                    break
                resultats = (data or {}).get("resultats", []) if status != 204 else []
                for o in resultats:
                    brutes[o["id"]] = o
                time.sleep(0.25)
                if len(resultats) < 150:
                    break

    offres = []
    for o in brutes.values():
        lieu = o.get("lieuTravail") or {}
        libelle = lieu.get("libelle") or ""
        dep = (lieu.get("codePostal") or "")[:2] or libelle[:2]
        offres.append({
            "id": "ft-" + o["id"],
            "source": "France Travail",
            "titre": o.get("intitule") or "",
            "entreprise": (o.get("entreprise") or {}).get("nom") or "",
            "lieu": re.sub(r"^\d{2,3}\s*-\s*", "", libelle).title(),
            "departement": dep,
            "date": o.get("dateCreation") or "",
            "url": FT_OFFRE_URL + urllib.parse.quote(o["id"]),
            "description": o.get("description") or "",
            "contrat": o.get("typeContratLibelle") or o.get("typeContrat") or "",
            "rome": o.get("romeCode") or "",
            "categorie": "",
        })
    return offres, f"{len(brutes)} offres lues"


def fetch_adzuna() -> tuple[list[dict], str]:
    app_id, app_key = os.environ.get("ADZUNA_APP_ID"), os.environ.get("ADZUNA_APP_KEY")
    if not app_id or not app_key:
        return [], "non configurée (clés manquantes)"
    requetes = []
    for nom_dep in DEPARTEMENTS.values():
        # 1) tous les stages classés « informatique » par Adzuna
        requetes.append(({"what_or": "stage stagiaire internship", "category": "it-jobs", "where": nom_dep}, 5))
        # 2) stages dont le titre parle d'info mais mal classés
        requetes.append(({"what": "stage", "what_or": "développeur informatique web logiciel data", "where": nom_dep}, 3))
    brutes: dict[str, dict] = {}
    erreurs = 0
    for params, pages in requetes:
        for page in range(1, pages + 1):
            try:
                _, data = http("GET", ADZUNA_URL.format(page=page), params={
                    "app_id": app_id, "app_key": app_key, "results_per_page": 50,
                    "max_days_old": 60, "sort_by": "date", **params,
                })
            except HttpError as e:
                erreurs += 1
                print(f"  Adzuna {params.get('where')} p{page} : {e}", file=sys.stderr)
                if e.status in (401, 403):
                    return [], f"erreur d'authentification ({e}) : vérifie les clés"
                break
            resultats = (data or {}).get("results", [])
            for o in resultats:
                brutes[str(o.get("id"))] = o
            time.sleep(1)
            if len(resultats) < 50:
                break

    offres = []
    for o in brutes.values():
        loc = o.get("location") or {}
        zones = loc.get("area") or []
        affiche = loc.get("display_name") or ""
        dep = ""
        for code, nom in DEPARTEMENTS.items():
            if nom in zones or norm(nom) in norm(affiche):
                dep = code
        offres.append({
            "id": "az-" + str(o.get("id")),
            "source": "Adzuna",
            "titre": nettoyer_html(o.get("title") or ""),
            "entreprise": (o.get("company") or {}).get("display_name") or "",
            "lieu": zones[-1] if zones else affiche,
            "departement": dep,
            "date": o.get("created") or "",
            "url": o.get("redirect_url") or "",
            "description": nettoyer_html(o.get("description") or ""),
            "contrat": " ".join(x for x in (o.get("contract_type"), o.get("contract_time")) if x),
            "rome": "",
            "categorie": (o.get("category") or {}).get("tag") or "",
        })
    statut = f"{len(brutes)} offres lues" + (f", {erreurs} requête(s) en erreur" if erreurs else "")
    return offres, statut


# --------------------------------------------------------------------------
# Tri, fusion avec les jours précédents, écriture
# --------------------------------------------------------------------------

def garder(o: dict) -> bool:
    return (
        o["departement"] in DEPARTEMENTS
        and o["url"].startswith(("https://", "http://"))
        and est_stage(o["titre"], o["description"], o["contrat"])
        and est_informatique(o["titre"], o["description"], o["rome"], o["categorie"])
    )


def preparer(o: dict) -> dict:
    texte = o["titre"] + " . " + o["description"]
    desc = o["description"]
    return {
        "id": o["id"],
        "source": o["source"],
        "titre": o["titre"],
        "entreprise": o["entreprise"] or "Entreprise non communiquée",
        "lieu": o["lieu"],
        "departement": o["departement"],
        "date": o["date"][:10],
        "url": o["url"],
        "extrait": desc[:EXTRAIT_MAX] + ("…" if len(desc) > EXTRAIT_MAX else ""),
        "duree": analyser_duree(texte),
        "niveau": niveau(texte),
    }


def fusionner(nouvelles: list[dict], anciennes: list[dict], aujourdhui: str) -> list[dict]:
    precedentes = {o["id"]: o for o in anciennes}
    vues: dict[str, dict] = {}
    doublons: set[str] = set()
    for o in sorted(nouvelles, key=lambda x: x["source"] != "France Travail"):
        cle = cle_doublon(o["titre"], o["entreprise"])
        if cle in doublons:
            continue
        doublons.add(cle)
        ancienne = precedentes.get(o["id"])
        o["premiere_vue"] = ancienne["premiere_vue"] if ancienne else aujourdhui
        o["derniere_vue"] = aujourdhui
        vues[o["id"]] = o
    # Offres absentes aujourd'hui (API en panne, quota...) : gardées quelques jours
    limite = (datetime.fromisoformat(aujourdhui) - timedelta(days=RETIRER_APRES_JOURS)).date().isoformat()
    for oid, o in precedentes.items():
        if oid not in vues and o.get("derniere_vue", "") >= limite:
            cle = cle_doublon(o["titre"], o["entreprise"])
            if cle not in doublons:
                doublons.add(cle)
                vues[oid] = o
    nouvelle_limite = (datetime.fromisoformat(aujourdhui) - timedelta(days=NOUVELLE_PENDANT_JOURS - 1)).date().isoformat()
    for o in vues.values():
        o["nouvelle"] = o["premiere_vue"] >= nouvelle_limite
    return sorted(vues.values(), key=lambda x: (x["premiere_vue"], x["date"]), reverse=True)


def main() -> int:
    maintenant = datetime.now(timezone.utc)
    aujourdhui = maintenant.date().isoformat()
    anciennes = []
    if OUT.exists():
        try:
            anciennes = json.loads(OUT.read_text(encoding="utf-8")).get("offres", [])
        except (json.JSONDecodeError, OSError):
            anciennes = []

    sources, brutes = {}, []
    for nom, fonction in (("France Travail", fetch_france_travail), ("Adzuna", fetch_adzuna)):
        print(f"→ {nom}…")
        offres, statut = fonction()
        print(f"  {statut}")
        sources[nom] = statut
        brutes.extend(offres)

    retenues = [preparer(o) for o in brutes if garder(o)]
    offres = fusionner(retenues, anciennes, aujourdhui)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "mis_a_jour": maintenant.isoformat(timespec="minutes"),
        "sources": sources,
        "offres": offres,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"✓ {len(retenues)} stages info 59/62 retenus aujourd'hui, {len(offres)} au total dans {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
