"""Tests du tri des offres. Les offres ci-dessous sont FICTIVES (données de test).

Lancer : python -m unittest discover -s tests -v
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import fetch  # noqa: E402


class Duree(unittest.TestCase):
    def cat(self, texte):
        return fetch.analyser_duree(texte)["categorie"]

    def test_categories(self):
        self.assertEqual(self.cat("Stage de 14 semaines à partir d'avril"), "compatible")
        self.assertEqual(self.cat("Stage de 3 mois"), "compatible")
        self.assertEqual(self.cat("Durée : 2 à 3 mois"), "compatible")
        self.assertEqual(self.cat("Stage d'une durée de 3 à 4 mois"), "compatible")
        self.assertEqual(self.cat("Stage de 4 mois"), "proche")
        self.assertEqual(self.cat("Stage de 6 mois, fin d'études"), "trop_longue")
        self.assertEqual(self.cat("Durée du stage : six mois"), "trop_longue")
        self.assertEqual(self.cat("Stage de 2 mois cet été"), "trop_courte")
        self.assertEqual(self.cat("Stage développeur web"), "non_precisee")

    def test_ignore_experience(self):
        # « 6 mois » sans lien avec la durée du stage
        self.assertEqual(self.cat("Développeur. Vous avez 6 mois d'expérience en PHP."), "non_precisee")


class Filtres(unittest.TestCase):
    def test_stage(self):
        self.assertTrue(fetch.est_stage("Stage Développeur Web", "", ""))
        self.assertTrue(fetch.est_stage("Stagiaire développeur", "", "CDD"))
        self.assertFalse(fetch.est_stage("Alternance développeur web", "stage possible", ""))
        self.assertFalse(fetch.est_stage("Développeur Java", "après un stage chez nous", "CDI"))

    def test_informatique(self):
        self.assertTrue(fetch.est_informatique("Stage Développeur Full-Stack", ""))
        self.assertTrue(fetch.est_informatique("Stage assistant", "", rome="M1805"))
        self.assertFalse(fetch.est_informatique("Stage marketing digital web", ""))
        self.assertTrue(fetch.est_informatique("Stage développeur web marketing", ""))
        self.assertFalse(fetch.est_informatique("Stage vendeur", ""))

    def test_niveau(self):
        self.assertIn("BUT / Bac+2-3 mentionné", fetch.niveau("Profil : étudiant en BUT Informatique"))
        self.assertEqual(fetch.niveau("Dans le but de renforcer l'équipe"), [])
        self.assertIn("Vise aussi Bac+4/5", fetch.niveau("Étudiant en Master 2"))


FT_REPONSE = {"resultats": [
    {"id": "TEST001", "intitule": "Stage Développeur Web H/F", "description": "Stage de 3 mois. Étudiant BUT informatique.",
     "dateCreation": "2026-11-20T10:00:00.000Z", "lieuTravail": {"libelle": "59 - LILLE", "codePostal": "59000"},
     "entreprise": {"nom": "Entreprise Test A"}, "typeContrat": "CDD", "romeCode": "M1805"},
    {"id": "TEST002", "intitule": "Stage commercial", "description": "Stage 3 mois",
     "dateCreation": "2026-11-20T10:00:00.000Z", "lieuTravail": {"libelle": "62 - ARRAS", "codePostal": "62000"},
     "entreprise": {"nom": "Entreprise Test B"}, "typeContrat": "CDD", "romeCode": "D1402"},
    {"id": "TEST003", "intitule": "Stagiaire administrateur réseau", "description": "Stage de 6 mois",
     "dateCreation": "2026-11-21T10:00:00.000Z", "lieuTravail": {"libelle": "62 - LENS", "codePostal": "62300"},
     "entreprise": {}, "typeContrat": "CDD", "romeCode": "M1801"},
]}
AZ_REPONSE = {"results": [
    {"id": 9001, "title": "Stage <strong>Développeur</strong> Python", "description": "Stage de 14 semaines...",
     "created": "2026-11-22T08:00:00Z", "redirect_url": "https://www.adzuna.fr/details/9001",
     "company": {"display_name": "Entreprise Test C"},
     "location": {"display_name": "Roubaix, Nord", "area": ["France", "Hauts-de-France", "Nord", "Roubaix"]},
     "category": {"tag": "it-jobs"}},
    {"id": 9002, "title": "Stage Développeur Web H/F", "description": "doublon de TEST001",
     "created": "2026-11-20T08:00:00Z", "redirect_url": "https://www.adzuna.fr/details/9002",
     "company": {"display_name": "Entreprise Test A"},
     "location": {"display_name": "Lille, Nord", "area": ["France", "Hauts-de-France", "Nord", "Lille"]},
     "category": {"tag": "it-jobs"}},
    {"id": 9003, "title": "Stage développeur", "description": "Hors zone",
     "created": "2026-11-22T08:00:00Z", "redirect_url": "https://www.adzuna.fr/details/9003",
     "company": {"display_name": "Entreprise Test D"},
     "location": {"display_name": "Paris", "area": ["France", "Ile-de-France", "Paris"]},
     "category": {"tag": "it-jobs"}},
]}


def faux_http(method, url, params=None, form=None, headers=None, timeout=30):
    if "access_token" in url:
        assert form["scope"] == "api_offresdemploiv2 o2dsoffre"
        return 200, {"access_token": "jeton-test", "expires_in": 1499}
    if "francetravail" in url:
        if params["departement"] == "59" and params["motsCles"] == "stage":
            return 206, {"resultats": [FT_REPONSE["resultats"][0]]}
        if params["departement"] == "62" and params["motsCles"] == "stage":
            return 206, {"resultats": FT_REPONSE["resultats"][1:]}
        return 204, None
    if "adzuna" in url:
        return 200, AZ_REPONSE if url.endswith("/1") else {"results": []}
    raise AssertionError(url)


class Pipeline(unittest.TestCase):
    def test_complet(self):
        env = {"FT_CLIENT_ID": "x", "FT_CLIENT_SECRET": "y", "ADZUNA_APP_ID": "a", "ADZUNA_APP_KEY": "b"}
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.dict(os.environ, env), \
                mock.patch.object(fetch, "http", faux_http), \
                mock.patch.object(fetch, "OUT", Path(d) / "offres.json"), \
                mock.patch.object(fetch, "ROOT", Path(d)), \
                mock.patch.object(fetch.time, "sleep", lambda s: None):
            self.assertEqual(fetch.main(), 0)
            data = json.loads((Path(d) / "offres.json").read_text(encoding="utf-8"))
            ids = {o["id"] for o in data["offres"]}
            # gardées : FT dev web (59), FT réseau (62), Adzuna Python (59)
            # rejetées : stage commercial, doublon Adzuna de TEST001, offre à Paris
            self.assertEqual(ids, {"ft-TEST001", "ft-TEST003", "az-9001"})
            par_id = {o["id"]: o for o in data["offres"]}
            self.assertEqual(par_id["ft-TEST001"]["duree"]["categorie"], "compatible")
            self.assertEqual(par_id["ft-TEST003"]["duree"]["categorie"], "trop_longue")
            self.assertEqual(par_id["ft-TEST003"]["entreprise"], "Entreprise non communiquée")
            self.assertEqual(par_id["az-9001"]["titre"], "Stage Développeur Python")
            self.assertEqual(par_id["ft-TEST001"]["url"], "https://candidat.francetravail.fr/offres/recherche/detail/TEST001")
            self.assertTrue(all(o["nouvelle"] for o in data["offres"]))

    def test_sans_cles(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            offres, statut = fetch.fetch_france_travail()
            self.assertEqual(offres, [])
            self.assertIn("non configurée", statut)

    def test_fusion_garde_date_et_retire_vieilles(self):
        ancienne = {"id": "a", "titre": "Stage dev", "entreprise": "X", "premiere_vue": "2026-11-01",
                    "derniere_vue": "2026-11-26"}
        perimee = {"id": "b", "titre": "Stage data", "entreprise": "Y", "premiere_vue": "2026-10-01",
                   "derniere_vue": "2026-11-10"}
        revue = {"id": "a", "source": "Adzuna", "titre": "Stage dev", "entreprise": "X", "date": "2026-11-01"}
        res = fetch.fusionner([revue], [ancienne, perimee], "2026-11-27")
        self.assertEqual([o["id"] for o in res], ["a"])
        self.assertEqual(res[0]["premiere_vue"], "2026-11-01")
        self.assertFalse(res[0]["nouvelle"])


if __name__ == "__main__":
    unittest.main()


class ErreursAuth(unittest.TestCase):
    def _lancer(self, reponses):
        appels = []

        def faux(method, url, params=None, form=None, headers=None, timeout=30):
            if "access_token" in url:
                appels.append(form["scope"])
                r = reponses.pop(0)
                if isinstance(r, Exception):
                    raise r
                return 200, r
            return 204, None
        env = {"FT_CLIENT_ID": " id-test ", "FT_CLIENT_SECRET": "secret-test"}
        with mock.patch.dict(os.environ, env), mock.patch.object(fetch, "http", faux), \
                mock.patch.object(fetch.time, "sleep", lambda s: None):
            offres, statut = fetch.fetch_france_travail()
        return appels, statut

    def test_scope_alternatif(self):
        appels, statut = self._lancer([fetch.HttpError(400, "invalid_scope"), {"access_token": "t"}])
        self.assertEqual(appels[1], "application_id-test api_offresdemploiv2 o2dsoffre")
        self.assertIn("offres lues", statut)

    def test_mauvaise_cle(self):
        appels, statut = self._lancer([fetch.HttpError(400, "invalid_client")])
        self.assertEqual(len(appels), 1)
        self.assertIn("identifiant client ou clé secrète incorrects", statut)
        self.assertNotIn("secret-test", statut)

    def test_code_erreur_lu(self):
        import io
        import urllib.error
        e = urllib.error.HTTPError("u", 400, "Bad", {}, io.BytesIO(b'{"error":"invalid_scope","error_description":"x"}'))
        self.assertEqual(fetch._code_erreur(e), "invalid_scope")


class CasReelsAdzuna(unittest.TestCase):
    """Cas repérés lors du premier vrai passage (titres réels, tri attendu)."""

    def garde(self, titre, description="", categorie="it-jobs"):
        return fetch.est_stage(titre) and fetch.est_informatique(titre, description, "", categorie)

    def test_rejets(self):
        self.assertFalse(self.garde("Front End Power Electronics Engineer", "internship stage"))
        self.assertFalse(self.garde("Développeur .Net H/F", "stage possible"))
        self.assertFalse(self.garde("Stage : Stage Business Développement et études stratégiques F/H"))
        self.assertFalse(self.garde("Stage - Venture Capital & Impact Investing Proparco- F/H", "data"))
        self.assertFalse(self.garde("Stage 2027 Assistant Excellence Relationnelle, documentation et qualité", "web"))
        # catégorie it-jobs mais aucun mot informatique nulle part
        self.assertFalse(self.garde("Stage chargé de mission RSE", "accompagner les équipes"))

    def test_gardes(self):
        self.assertTrue(self.garde("Stage : Développeur .net/React (F/H) - stage"))
        self.assertTrue(self.garde("Stage : Stage – Data Engineer (F/H) – Lille"))
        self.assertTrue(self.garde("Ingénieure / Ingénieur Cybersécurité GRC - Stage H/F (Stage)"))
        self.assertTrue(self.garde("Stage Business Analyst - Défense & Sécurité - Lille", "projet informatique"))

    def test_doublons(self):
        self.assertEqual(
            fetch.cle_doublon("Stage : Stage - Développeur/se Java - Défense et Sécurité - Lille", "Sopra-Steria"),
            fetch.cle_doublon("Stage - Développeur/se Java - Défense et Sécurité - Lille", "Sopra Steria"))
        self.assertNotEqual(fetch.cle_doublon("Stage développeur web", "A"), fetch.cle_doublon("Stage développeur web", "B"))

    def test_duree_debut_de_stage(self):
        r = fetch.analyser_duree("Le stage commencera par 2 mois de formation interne.")
        self.assertEqual(r["categorie"], "non_precisee")
        self.assertEqual(fetch.analyser_duree("stage conventionné de 6 mois")["categorie"], "trop_longue")


class VersionRegles(unittest.TestCase):
    def test_changement_de_regles_retrie(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "offres.json"
            out.write_text(json.dumps({"version_regles": 1, "offres": [
                {"id": "az-1", "source": "Adzuna", "titre": "Front End Power Electronics Engineer", "entreprise": "X",
                 "premiere_vue": "2026-11-20", "derniere_vue": "2026-11-27"}]}), encoding="utf-8")
            with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(fetch, "OUT", out), \
                    mock.patch.object(fetch, "ROOT", Path(d)):
                fetch.main()
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(data["offres"], [])
            self.assertEqual(data["version_regles"], fetch.VERSION_REGLES)


class Lieux(unittest.TestCase):
    def test_departement(self):
        d = fetch.departement_depuis_lieu
        self.assertEqual(d("Lille"), "59")
        self.assertEqual(d("Villeneuve-d'Ascq"), "59")
        self.assertEqual(d("Arras, Hauts-de-France"), "62")
        self.assertEqual(d("Boulogne-sur-Mer"), "62")
        self.assertEqual(d("Marcq-en-Barœul (59)"), "59")
        self.assertEqual(d("62300 Lens"), "62")
        self.assertEqual(d("Pas-de-Calais"), "62")
        self.assertEqual(d("Nord"), "59")
        self.assertEqual(d("Paris"), "")
        self.assertEqual(d("Amiens"), "")
        self.assertEqual(d("Montreuil"), "")  # 62 ou 93 : on ne devine pas
        self.assertEqual(d("Saint-Aubin"), "")  # existe dans le 59 ET le 62


class Jooble(unittest.TestCase):
    def test_lecture(self):
        appels = []

        def faux_post(url, corps):
            appels.append(url)
            if url.startswith("https://fr.jooble.org"):
                b = json.loads(corps)
                if b["keywords"] == "stage développeur" and b["location"] == "Lille" and b["page"] == 1:
                    return {"totalCount": 2, "jobs": [
                        {"id": 1, "title": "Stage <b>Développeur</b> PHP", "location": "Roubaix", "company": "Test SARL",
                         "snippet": "Stage de 14 semaines", "link": "https://fr.jooble.org/desc/1", "updated": "2026-11-26T10:00:00.000"},
                        {"id": 2, "title": "Stage développeur", "location": "Paris", "company": "Ailleurs",
                         "snippet": "", "link": "https://fr.jooble.org/desc/2", "updated": "2026-11-26T10:00:00.000"},
                    ]}
                return {"totalCount": 0, "jobs": []}
            raise fetch.HttpError(404)
        with mock.patch.dict(os.environ, {"JOOBLE_KEY": "cle-test"}), \
                mock.patch.object(fetch, "_post_json", faux_post), mock.patch.object(fetch.time, "sleep", lambda s: None):
            offres, statut = fetch.fetch_jooble()
        self.assertTrue(all(u.startswith("https://fr.jooble.org/api/") for u in appels))
        self.assertLessEqual(len(appels), 70)  # quota gratuit : 100/jour
        self.assertIn("2 offres lues", statut)
        par_id = {o["id"]: o for o in offres}
        self.assertEqual(par_id["jb-1"]["departement"], "59")
        self.assertEqual(par_id["jb-1"]["titre"], "Stage Développeur PHP")
        self.assertEqual(par_id["jb-2"]["departement"], "")
        self.assertTrue(fetch.garder(par_id["jb-1"]))
        self.assertFalse(fetch.garder(par_id["jb-2"]))

    def test_cle_refusee(self):
        def refus(url, corps):
            raise fetch.HttpError(403)
        with mock.patch.dict(os.environ, {"JOOBLE_KEY": "x"}), mock.patch.object(fetch, "_post_json", refus):
            offres, statut = fetch.fetch_jooble()
        self.assertEqual(offres, [])
        self.assertIn("fr.jooble.org", statut)
        self.assertNotIn("x/", statut)


class CasReels2(unittest.TestCase):
    def garde(self, titre, description="", categorie="it-jobs"):
        return fetch.est_stage(titre) and fetch.est_informatique(titre, description, "", categorie)

    def test_developpement_hors_info(self):
        self.assertFalse(self.garde("Stage Assistant Développement Commercial et Evènementiel H/F"))
        self.assertFalse(self.garde("Stage : Ingénieur(e) Agroalimentaire – Transparence de l'offre et développement produit"))
        self.assertTrue(self.garde("Stage développement web PHP"))
        self.assertTrue(self.garde("Stage développement d'applications mobiles"))
        self.assertTrue(self.garde("Stage Développeuse / Développeur fullstack"))

    def test_doublon_ville_en_fin(self):
        self.assertEqual(fetch.cle_doublon("Stage Data Engineer / IA (H/F) – Lille", "IPPON Technologies"),
                         fetch.cle_doublon("Stage Data Engineer / IA (H/F)", "Ippon Technologies"))

    def test_reessai_503(self):
        import io
        import urllib.error
        appels = []

        class Rep:
            status = 200
            def read(self): return b'{"ok": 1}'
            def __enter__(self): return self
            def __exit__(self, *a): return False

        def faux_urlopen(req, timeout=30):
            appels.append(1)
            if len(appels) == 1:
                raise urllib.error.HTTPError("u", 503, "x", {}, io.BytesIO(b""))
            return Rep()
        with mock.patch.object(fetch.urllib.request, "urlopen", faux_urlopen), \
                mock.patch.object(fetch.time, "sleep", lambda s: None):
            self.assertEqual(fetch.http("GET", "https://exemple.invalid"), (200, {"ok": 1}))
        self.assertEqual(len(appels), 2)
