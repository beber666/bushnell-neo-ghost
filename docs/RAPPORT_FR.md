# Bushnell Neo Ghost — Rapport de rétro-ingénierie

*Rédigé par Hermes, 27 → 30 octobre 2026 (mis à jour le 30/10 après validation sur l'appareil). Tout ce qui est affirmé ici a été vérifié par exécution réelle sauf mention « hypothèse ». Les erreurs commises en cours de route sont documentées (section 2) parce qu'elles expliquent une partie des symptômes.*

Version publique du rapport (données personnelles retirées). Outils : dossier `tools/` de ce dépôt. Les noms de fichiers cités (`sda1.img`, `neodb/…`) sont ceux de l'environnement de travail d'origine.

---

## 0. Résumé

| Sujet | État |
|---|---|
| Appareil (erreurs 07 puis 05) | **Réparé** — démarre sans code depuis le 29/10 |
| Disposition du disque / FAT maison | Documentée |
| Base de parcours iGolf (index, parcours, noms) | **Décodée et déchiffrée** — outil `neodb/neodb.py` |
| En-tête maître `idx/ghost.idx` | Décodé sauf 4 octets « magiques » + 116 octets finaux — **non bloquants** (prouvé sur l'appareil) |
| En-tête de fiche (60 o) | **Décodé** : position, copie de `ck`, **nom affiché** (flux global `KH`) |
| Firmware `FW.bin` | **Non désassemblé** — architecture probable PIC24/dsPIC, pistes ci-dessous |
| Ajout du Golf de Saint-Roman (Beaucaire) | **Installé** dans `idx/023[718]` ; écriture et affichage **validés sur l'appareil** (test à domicile) ; reste l'essai sur le parcours |
| Ajout de n'importe quel golf | **Méthode validée** — section 12 |

---

## 1. Matériel

- Bushnell **Neo Ghost** (réf. 368221), GPS de golf de 2015, base iGolf préchargée (~33 000 parcours annoncés, 29 544 réels).
- USB : `04d8:0009` « Microchip Technology Inc. — Microchip Mass Storage Drive », n° de série `123456789999` (valeur générique de la pile USB Microchip).
- Stockage vu par l'hôte : 64 016 blocs logiques de **2048 octets** (131 MB / 125 MiB).
- Le support officiel (bushnell.igolf.com, logiciel de synchronisation) est fermé : plus aucun moyen officiel de mise à jour.

---

## 2. Chronologie de l'incident et réparation

1. **27/10** — Le Neo fonctionne mais ne se met plus à jour (site officiel mort). Il avait aussi été branché sur un Mac (`.fseventsd` daté du 27/10).
2. Je l'ai **monté en lecture-écriture** sous Linux, lu tous les fichiers (`rsync`), puis le Neo a été débranché **sans démontage**. Linux a laissé l'indicateur « volume sale » (bit 0 de l'octet `0x25` du secteur de démarrage : `0xDC` → `0xDD`). → **Erreur 07** au démarrage.
3. Restauration n° 1 de l'image `sda1.img` (prise pendant le montage, donc avec `0xDD`) sur `/dev/sdb1`. Vérification déclarée « 100 % » — **fausse** : elle relisait le cache de Linux (un autre processus gardait le périphérique ouvert), pas la flash. → **Erreur 05 « contact support »**.
4. **28/10** — Plusieurs erreurs de diagnostic de ma part :
   - comparaison et écritures sur **le disque entier `/dev/sdb`** au lieu de la partition `/dev/sdb1` (la partition commence à l'octet 18 432) ; les secteurs 0-8 du disque (MBR + zone vide) ont été pris pour la FAT ;
   - conclusion erronée « le Neo efface sa FAT tout seul / matériel mort », et une lecture fausse « 54 → 460 octets » (c'étaient toujours 54 octets, positions 0 à 459) ;
   - `restore3.py` a écrit l'image de partition sur `/dev/sdb` (décalée de 18 Ko).
5. Entre-temps, sur l'erreur 05, un appui sur un bouton a permis de continuer, et **le Neo a reformaté lui-même sa partition** (FAT vide, racine vide, blocs de données effacés à `0xFF`, secteur de démarrage réécrit selon son propre modèle avec `0xDC`). *Lien de cause à effet avec l'appui : hypothèse forte.*
6. **29/10** — Diagnostic correct : partition seule, lectures `O_DIRECT` (sans cache). Restauration de `sda1.img` avec `0x25` remis à `0xDC`. Le premier bloc de 64 Ko (démarrage + FAT + racine) n'a pas tenu en une seule grosse écriture ; réécrit **secteur par secteur** (`O_DIRECT|O_SYNC`), il tient. Vérification complète sans cache : **0 différence**, `fsck` : 624 fichiers.
7. Résultat : **le Neo démarre sans code d'erreur**. Relecture après démarrage : le Neo n'a rien écrit dans sa zone système.

**Leçons** (aussi consignées dans la compétence `embedded-usb-storage-rescue`) : ne jamais monter le Neo en écriture ; couper l'automontage avant de le brancher ; toujours viser `/dev/sdX1` ; vérifier avec des lectures `O_DIRECT` ; écrire la zone système secteur par secteur ; ne jamais réécrire une image « réparée » par `fsck`.

---

## 3. Disque et système de fichiers

### 3.1 Disposition (secteurs de 2048 octets)

| LBA | Contenu |
|---|---|
| 0 | MBR : une partition, type `0x04`, début LBA **9**, 64 007 secteurs |
| 1-8 | Zone vide : lit `0xFF`, les écritures n'y persistent pas (normal) |
| 9 → 64 015 | Partition FAT (131 086 336 octets = taille exacte de `sda1.img`) ; sysfs `start=36` (unités 512 o) |

### 3.2 Secteur de démarrage « maison » (écrit par le Neo lui-même)

Champs classiques : OEM `MSDOS5.0`, 2048 o/secteur, 16 secteurs/cluster, 1 secteur réservé, **1 seule FAT** de 4 secteurs, 128 entrées racine, 64 007 secteurs, média `0xF8`, 63 secteurs/piste, 255 têtes, *hidden sectors = 8* (alors que la partition commence en LBA 9).

Bloc étendu **décalé de 2 octets** par rapport au standard :

| Offset | Valeur | Remarque |
|---|---|---|
| `0x24` | `0x29` | signature étendue (standard : `0x26`) |
| `0x25-0x28` | `DC CC BB AA` | ID de volume `0xAABBCCDC` ; `0x25` = aussi l'octet « état » vu par Linux/fsck (bit 0 = sale) |
| `0x29` | `L1 NEO` | étiquette — **L1** = L1 Inc., société mère d'iGolf |
| `0x34` | `FAT16   ` | type annoncé, alors que le volume est en FAT12 (4000 clusters) |

`fsck.vfat -a` « corrige » ces champs (`sda1-fixed.img`) → **cette image ne doit pas être utilisée**.

Organisation dans la partition : secteur 0 = démarrage, 1-4 = FAT, 5-6 = racine, données à partir du secteur 7.

### 3.3 Particularité d'écriture observée

Une écriture unique de 64 Ko à l'offset 0 de la partition : le secteur 0 est conservé, les secteurs 1-31 relisent `0xFF`. Le reste du disque accepte les grosses écritures. Des écritures d'un secteur à la fois tiennent. *Une seule observation ; mécanisme exact inconnu.*

---

## 4. Contenu de la partition

| Élément | Taille / nombre | Date | Rôle |
|---|---|---|---|
| `FW.bin` | 101 612 o | 2015-03-10 | Firmware (section 7) |
| `ghost.setup` | 0 o | 2014-09-26 | Inconnu (fichier drapeau ?) |
| `idx/000`…`idx/027` | 28 × 32 768 o | 2014-12-05 | Index, 1024 entrées de 32 o |
| `idx/028` | 27 904 o | 2014-12-05 | Index, 872 entrées |
| `idx/ghost.idx` | 412 o | 2014-12-05 | En-tête maître |
| `name/000`…`name/044` | 45 × 32 750 o | — | Noms, 655 × 50 o |
| `name/045` | 3 450 o | — | Noms, 69 × 50 o |
| `000/`…`003/` | 4 × 100 fichiers | 2015-07-09 | Parcours, 130 176 o = 72 × 1808 o |
| `004/` | 11 fichiers | 2015-07-09 | Parcours (dernier fichier partiel) |
| `.apdisk`, `.Spotlight-V100`, `.TemporaryItems`, `.fseventsd` | — | 2017 / 2026 | Déchets macOS |

Comptes cohérents : 28 × 1024 + 872 = **29 544** entrées d'index = 45 × 655 + 69 noms.

---

## 5. Base de parcours iGolf

### 5.1 En-tête maître `idx/ghost.idx` (412 o)

| Offset | Contenu |
|---|---|
| 0 | `58 EA EA EB` (u32 `0xEBEAEA58`) — **inconnu** ; pas un CRC32 ni une somme simple des index |
| 4 | u16 `29544` — nombre de parcours |
| 6 | u16 `1024` — entrées par fichier d'index |
| 8 | u16 `100` — fichiers par répertoire de données |
| 10 | u16 `72` — parcours par fichier de données |
| 12-63 | zéros |
| 64-295 | 29 × (int32 longitude **première**, int32 longitude **dernière**) de chaque `idx/NNN` — vérifié 29/29 ; sert à trouver le bon fichier par dichotomie |
| 296-411 | 116 octets à haute entropie — **inconnus** (signature ? empreinte ?) |

**Analyse des 116 octets (30/10)** — 116 = 29 × 4, soit une valeur par fichier d'index possible. Résultats :
- **Aucune correspondance** pour CRC32 (et inversé), CRC32 MPEG-2, Adler-32, sommes et XOR sur 8/32 bits.
  - Testés sur chaque `idx/NNN` complet ou sans remplissage, sur les parcours et sur les noms référencés par chaque fichier d'index, en petit et grand boutiste.
- Pas de déchiffrement cohérent avec `KG`, quelle que soit la rotation.
- Ces octets n'apparaissent nulle part ailleurs dans la base.
- Les 4 octets magiques ne sont le CRC32 / Adler / somme d'aucune zone de `ghost.idx`.
- Tous les fichiers datent du 05/12/2014 08:26-08:27 (aucune mise à jour postérieure qui aurait pu servir d'indice).

→ Question **non tranchable par analyse**. **Test réel sur l'appareil (30/10)** :
- Contenu : l'emplacement `idx/023[718]` remplacé par une version provisoire de « St Roman Beaucaire » (position, nom, 9 pars ; greens provisoirement au centre du golf).
- `ghost.idx` inchangé.
- 4 secteurs écrits (8812, 8813 : parcours ; 13922 : index ; 14631 : nom), vérifiés en lecture directe.
- Originaux sauvegardés dans `test_backup_sectors.json`, image de test `sda1-test.img`, script `neodb/build_test.py`.
- Résultat : *en attente du test de l'utilisateur*.
- **Résultat partiel (30/10)** : au domicile de l'utilisateur (≈ 30 km du golf), le Neo démarre sans code et « Play Golf » propose le golf le plus proche, Nîmes Vacquerolles.
  - Vacquerolles est dans le même fichier d'index modifié (`idx/023`), et ce fichier a été lu sans erreur.
  - Saint-Roman est trop loin pour être proposé : le nom et le parcours modifiés restent à tester sur place ou via la liste.

### 5.2 Entrées d'index `idx/NNN` (32 o, en clair)

| Offset | Type | Contenu |
|---|---|---|
| 0 | int32 LE | latitude × 10⁷ (centre du parcours) |
| 4 | int32 LE | longitude × 10⁷ |
| 8 | u32 LE | offset de l'enregistrement dans le fichier de données (multiple de 1808) |
| 12 | u16 LE | **`ck` = graine du chiffrement** (pas une somme de contrôle) |
| 14 | 12 o ASCII | `DDD\0FFF\0NNN\0` : répertoire de données, fichier de données, fichier de noms |
| 26 | u16 LE | numéro de l'enregistrement dans le fichier de noms |
| 28 | 4 o | zéros |

**L'index est trié par longitude sur toute la base** (Hawaï `idx/000[0]` −159,53° → Nouvelle-Zélande `idx/028[871]` +178,30°). L'entrée globale *k* (= n° fichier × 1024 + position) pointe vers l'enregistrement de données *k*.

### 5.3 Enregistrement parcours (1808 o, chiffré)

**Chiffrement :** `clair[p] = chiffré[p] XOR KG[(p + ck + 9) mod 33]`, avec une clé globale de 33 octets :

```
KG = 19909ed9efbd83eb91589f313994f5c0e5c6b27c38c36538eeb8f248f3f48236ca
```

**Structure du clair :**

| Offset | Contenu |
|---|---|
| 0 | int32 latitude × 10⁷, int32 longitude × 10⁷ (identiques à l'index) |
| 8 | u16 LE : **copie de `ck`** (vérifié 29 544/29 544) |
| 10-59 | **nom affiché par le Neo** : `nom[p] = clair[10+p] XOR KH[p]` (flux global de 50 o, section 8) |
| 60 + 96·k | bloc du trou *k* (k = 0…17), 24 × int32 : |
| | paires (lat, lon) × 10⁷ : **green avant, centre, fond**, **4 points perso** (obstacles), **3 départs** |
| | puis 4 × int32 : **codes de type** des 4 points perso (non décodés ; famille `0xA48FF3FC`, `0xA48FF2FC`, `0xA48FF3E2`…) |
| 1788 | u16 nombre de trous (9 ou 18 observés ; un cas à 5) |
| 1790 | 1 octet par trou : le **par** |

Point vide = (2 000 000 000, 0). Trous inutilisés (parcours de 9 trous) remplis de points vides. Départs : tout trou en a au moins 1, ordonnés du plus long au plus court dans 89 % des cas (hypothèse : arrière/milieu/avant).

Exemple vérifié — *Nîmes Campagne Golf Club* (`idx/023[648]`, ck 24197) : 18 trous, pars 4-3-5-4-4-4-3-5-4 / 4-4-4-5-3-4-3-5-4 = **72**, greens avant/centre/fond à ~9 m d'écart, départs à 117 m d'un par 3 et 376 m d'un par 5.

### 5.4 Noms (50 o, chiffrés)

⚠ **Ce n'est pas le nom affiché par le Neo** (voir 5.3, octets 10-59 de la fiche).

`clair[p] = chiffré[p] XOR KS[ck mod 33][p]` — **33 flux différents de 50 octets**, un par valeur de `ck mod 33` (ce ne sont pas des rotations d'une même clé ; l'algorithme qui les génère n'est pas connu). Les 33 flux sont dans `neodb/keys.json`. Le nom est en ASCII terminé par `\0` ; la suite de l'enregistrement est du remplissage aléatoire.

### 5.5 Validation

- 591 parcours échantillonnés : centre déchiffré = centre de l'index **591/591**.
- Rotation de clé = `(ck + 9) mod 33` : vérifiée **268/268**.
- Rechiffrement → octets identiques au fichier : **300/300**.
- Noms ASCII propres : **93-95 %** (le reste : accents, ou caractères tardifs mal estimés).
- Parcours autour de Beaucaire retrouvés : Baux de Provence (9 trous, par 36), Servanes (18, 72), Nîmes Campagne (18, 72), Saint Martinois (9, 31), Avignon Garden (18, 72), Uzès (9, 36), Grand Avignon (18, 72), Nîmes Vacquerolles (18, 72).

---

## 6. Méthode de rétro-ingénierie (et impasses)

1. **Fausses pistes initiales** : enregistrements de noms supposés de 1808 o, hash de l'index pris comme clé XOR, RC4 avec des clés évidentes → échecs.
2. **Index** : les 8 premiers octets, lus comme deux int32/10⁷, tombent sur Kauai, l'Alaska, Vancouver, Dallas, Toronto, Dortmund, la Nouvelle-Zélande → coordonnées en clair. Les longitudes sont croissantes → tri.
3. **Période de clé** : autocorrélation à l'intérieur des enregistrements → pics uniquement à des multiples de **33** ; le plus fort à **264 = 8 × 33** (structures de 8 octets = paires de coordonnées).
4. **Clair connu** : l'octet de poids fort d'une coordonnée est quasi constant dans un parcours et connu grâce à l'index. Sur la grille modulo 264, l'octet le plus fréquent XOR cet octet donne chaque octet de clé.
   - Premier essai décalé d'une constante (`0xD5` = octet fort lat XOR octet fort lon) : j'avais aligné les paires sur l'offset 0, alors que les blocs de trous commencent à 60 (≡ 4 mod 8).
5. **Clé globale + rotation** : une fois les clés estimées, la moitié des enregistrements partageaient exactement la même clé à une rotation près. Tests de corrélation entre la rotation et chaque champ de l'index → `(ck + 9) mod 33` pour 268/268.
6. **Noms** : pas de période → regroupement des 29 544 noms par `ck mod 33` (~895 noms par groupe). Chaque groupe est un « masque jetable réutilisé », cassé statistiquement octet par octet (fréquence des lettres), puis correction de la casse (majuscule en début de mot).
7. **Structure** : nombre de trous et pars repérés en fin d'enregistrement (18 puis 4-3-5…), blocs de 96 octets déduits de l'espacement des coordonnées, sentinelle 2 000 000 000.

---

## 7. Firmware `FW.bin`

| Propriété | Valeur |
|---|---|
| Taille | 101 612 o (`0x18CEC`) |
| Date | 2015-03-10 06:32 |
| SHA-256 | `0d69d5dc602ecc82991e8c334dee36ee5a4513dcd840e5868235f17e4c55400f` |
| Entropie | 6,0-6,8 bits/octet jusqu'à `0x16000` ; puis ~95 % de zéros (remplissage) |

**Observations :**
- Les **48 premiers mots de 32 bits (LE)** valent `0xC080, 0xC084, 0xC088…` (pas de 4) : une table de sauts. C'est cohérent avec une **table de vecteurs d'interruption remappée** d'un microcontrôleur **Microchip PIC24 / dsPIC** (16 bits) placé derrière un chargeur de démarrage, ce qui concorde avec la puce USB Microchip.
- Mots suivants : `0x03344331`, `0x03764331`, puis `0x032A4183` répété (pas des vecteurs).
- Entre `0x2000` et `0x10000`, les octets d'offset impair ne valent presque jamais `0x00` (0,1 %) contre 6,6 % pour les pairs → structure en mots de 16 bits.

**Essais négatifs** (normaux si c'est du PIC24, qu'aucun de ces outils ne gère) :
- Capstone ARM, Thumb, ARM big-endian, MIPS32 LE/BE, x86, ARM64 → aucun code cohérent.
- Recherche de clé XOR périodique, NOT, rotations de bits, échange de quartets → rien (une rotation 7 en Thumb : faux positif).
- radare2 : installation échouée sur le Pi.

**Non déterminé :**
- Si `FW.bin` est en clair ou chiffré (les chargeurs Microchip de type AN1157 chiffrent en AES).
- Si c'est le firmware réellement exécuté ou une image de mise à jour stockée sur le disque.
- La signification des codes d'erreur (07, 05).
- Ce qui calcule ou vérifie les 4 octets magiques et les 116 octets finaux de `ghost.idx`.

**Prochaines étapes possibles :**
1. **Ghidra** (module PIC24/dsPIC), chargement brut en testant les deux formats d'image PIC24 (mots de 24 bits « empaquetés » ou avec octet fantôme), base `0x0000` ou `0xC000`.
2. Dans le désassemblage : la routine de déchiffrement (constante de 33 octets `KG`, modulo 33), la génération des flux de noms, la vérification de `ghost.idx`, les codes d'erreur.
3. Méthode physique (en dernier recours) : identifier le microcontrôleur sur le circuit, lire sa flash interne par ICSP avec un PICkit si la protection n'est pas activée.

---

## 8. Ajout du Golf de Beaucaire Saint-Roman

**Carte de score officielle** (golfsaintroman.fr, départs jaunes) — 9 trous, **par 29, 1 168 m**, 6 bunkers, 1 plan d'eau :

| Trou | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
|---|---|---|---|---|---|---|---|---|---|
| Par | 3 | 3 | 3 | 3 | 3 | 3 | 4 | 3 | 4 |
| Jaune (m) | 100 | 101 | 103 | 139 | 79 | 104 | 193 | 100 | 249 |

(Trou 1 : rouge 83 m, orange 51 m — 3 départs, comme les 3 emplacements de départ du format.)

**Emplacement choisi** (accord de l'utilisateur) : `idx/023[718]` « 9-Chateau de la Bawette Golf Club » (Belgique, 50.7294 / 4.6006). Ses voisins (4.6006 et 4.6120) encadrent Saint-Roman (4.6011) → tri préservé ; c'est une entrée intérieure de `idx/023` → table de `ghost.idx` inchangée.

**Plan d'écriture :**
1. Garder son `ck` (même rotation de clé et même flux de nom).
2. Réécrire latitude/longitude dans l'index.
3. Réécrire le nom « St Roman Beaucaire ».
4. Réécrire l'enregistrement de 1808 o : centre, 52 octets d'en-tête recopiés, 9 blocs de trous sans obstacles, 9 pars.
5. Écrire uniquement les secteurs modifiés, un par un, avec vérification `O_DIRECT`.

**Positions GPS — RÉSOLU (30/10)** : 9 greens validés par l'utilisateur.
- 6 greens viennent de son fichier GeoJSON (« archive », trous 1-6). Ils correspondent aux greens OSM et aux zones satellite à 1-7 m près.
- 3 greens ont été marqués sur la carte satellite : anneaux magenta détectés par couleur → trous 2, 5 et 8.
- Correspondance avec la numérotation actuelle : trou 1 = archive 1, 3 = a2, 4 = a3, 6 = a4, 7 = a5, 9 = a6.

**Avant / fond :**
- Contour OSM recentré sur le point validé : trous 1, 3, 4, 6, 7, 9.
- Profondeur de 16 m (taille des ellipses marquées) : trous 2, 5, 8.
- Profondeurs obtenues : 13 à 25 m.

**Départs (estimés)** :
- Emplacements dans l'ordre de la base : 1 = jaune, 2 = rouge, 3 = orange (ordre « plus long → plus court » dans 89 % des trous de la base).
- Placés aux distances officielles sur l'axe de jeu : vers le départ OSM pour les trous 1, 3, 7, 9 ; vers le green précédent pour les autres.
- Obstacles : aucun.

**Écriture finale :**
- Script `neodb/build_final.py`, image `sda1-final.img`, données `neodb/stroman_course_final.json`.
- Un seul secteur différait de la version de test (8812, la fiche du parcours).
- Écrit en `O_DIRECT|O_SYNC`. La relecture immédiate était encore fausse, la relecture après 30 s conforme : le contrôleur valide l'écriture avec retard, il faut toujours revérifier après un délai.
- `fsck` OK, éjection propre.
- **Reste à tester sur place.**

**Test à domicile (30/10)** — outil générique `neodb/forge_course.py`, écriture `neodb/write_sectors.py` (attend le Neo, vérifie l'état avant d'écrire, revérifie après 30 s, éjecte). Deux copies du parcours final, avec les trous translatés autour du domicile :
- `idx/023[609]` (ex-Dragon Golfschool) → « St Roman TEST », index au domicile (le tri par longitude reste valide). Teste aussi le **déplacement** d'un parcours.
- `idx/023[616]` (ex-Nimes Vacquerolles) → « Beaucaire TEST », index laissé à la position de Vacquerolles. Teste uniquement le nom et la fiche.
- Images `sda1-hometest.img` puis `sda1-hometest2.img`.
- **Restauration** : réécrire depuis `sda1-final.img` les secteurs 8715, 8716, 8721, 8722, 13920, 14629.
- Premier essai de l'utilisateur fait **avant** le branchement : non significatif.
- **Deuxième essai (30/10)** : « Play Golf » affiche **Dragon Golfschool** (en tête, donc à 0 km), puis Nimes Vacquerolles et Nimes Campagne.
  - La nouvelle position est donc bien lue et la recherche fonctionne (pas de blocage par `ghost.idx` ni par les 116 octets).
  - Mais le Neo affiche **les anciens noms** → il existe une 2e copie du nom.

### Découverte : 2e copie du nom dans la fiche (30/10)
Format de l'en-tête déchiffré d'une fiche (60 o) :

| Octets | Contenu | Vérification |
|---|---|---|
| 0-7 | lat/lon int32 ×1e7 | — |
| 8-9 | u16 LE = `ck` (copie) | vérifié sur 29 544/29 544 fiches |
| 10-59 | **nom du parcours** XOR `KH` | voir ci-dessous |

- `KH` est un flux global de 50 o, identique pour tous les groupes (positions 0-29 identiques sur les 33 groupes ck%33).
- Validation : 28 365/29 544 noms identiques à ceux du dossier `name/`. Les écarts ne concernent que la fin des noms longs (> 36 car.), mal décodée côté `name/`.
- **C'est cette copie que le Neo affiche.**
- Clé enregistrée dans `keys.json` (`header_name_keystreams_by_ck_mod33`, tous égaux).
- `neodb.py` gagne `header_name()` ; `near`/`dump` affichent désormais ce nom.
- `forge_course.py` écrit maintenant les deux copies du nom.
- Images reconstruites : `sda1-final2.img` (vrai Beaucaire, slot 718), `sda1-cav-b.img`, `sda1-cav2-b.img`.
- À écrire sur le Neo : secteurs 8715, 8721, 8812.

- **Troisième essai (30/10), après écriture des deux copies du nom** : « Play Golf » affiche **St Roman TEST**, **Beaucaire TEST**, Nimes Campagne.
  - Le parcours s'ouvre, l'utilisateur confirme que « tout fonctionne ».
  - **Conclusion : un golf forgé (position, nom, trous, pars) est accepté par le Neo**, sans toucher à `ghost.idx`.

### État final du Neo (30/10)
- Base d'origine **+ seul** « St Roman Beaucaire » dans `idx/023[718]` (ex-« 9-Chateau de la Bawette », Belgique).
- Secteurs de contenu différents de l'origine : **8812, 8813** (fiche), **13922** (index), **14631** (nom `name/`). Tout le reste est identique à `sda1.img` (avec l'octet `0x25` = `0xDC`).
- Vacquerolles (`023[616]`) et Dragon Golfschool (`023[609]`) restaurés à l'identique.
- Outil : `neodb/finalize.py`. Il attend le Neo, contrôle l'état, écrit, puis **relit les 64 007 secteurs en `O_DIRECT`** et les compare à l'image attendue. Il fait ensuite un `fsck` et éjecte le Neo.
- Image exacte du Neo : `sda1-NEO-FINAL.img`. Journal : `finalize.log`.
- Résultat : **SUCCÈS** — les 6 secteurs de test ont été restaurés (8715, 8716, 8721, 8722, 13920, 14629).
  - Vérification complète en 13,1 min : 0 secteur différent de l'attendu.
  - `fsck` : 624 fichiers. Éjection OK.
  - SHA-256 de l'image : `324381df014ac8d83154f4a316e6bfd0b95d9baeb02558bcc92da7636f2a6a80`.
  - Contrôle de l'image : 023[718] = « St Roman Beaucaire » (les deux copies du nom), 023[609] = Dragon Golfschool, 023[616] = Nimes Vacquerolles Golf Club.

**Historique de la recherche des greens (avant les points de l'utilisateur) :**
- OpenStreetMap : 6 greens et 4 trous (départ → drapeau : 78, 119, 128, 227 m), sans numéros.
- Plan du site (`PLANDUPARCOURS.png`, 1699 × 2156) : 9 greens et 9 départs jaunes repérés par couleur, et ils correspondent aux marqueurs du site. Mais **le plan n'est pas à l'échelle** :
  - calage par similitude : écarts de 69 à 300 m ;
  - calage affine : incohérent avec les longueurs officielles.
- Satellite (Esri, zoom 19, 0,215 m/pixel) : 17 zones d'herbe rase détectées ; les 6 greens OSM sont retrouvés à 2-13 m près.
- **Il reste à savoir quelle zone est le green de quel trou** → image annotée `stroman_greens_candidats.jpg` envoyée à l'utilisateur.
- Risque : l'image satellite peut être antérieure au tracé actuel.

**Risques de l'ajout — levés par les essais :**
- 52 octets d'en-tête : décodés (copie de `ck` + nom).
- 4 octets magiques et 116 octets de `ghost.idx` : laissés intacts, **aucun refus** du Neo.
- Retour arrière toujours possible : `sda1.img` (origine) et `forge_course.py`/`finalize.py`.

---

## 9. Questions ouvertes

1. Signification des codes d'erreur 05 et 07 (hypothèse : 05 = volume marqué sale / FAT invalide, avec proposition de reformatage).
2. `0xEBEAEA58` et les 116 octets finaux de `ghost.idx` — toujours inconnus, mais **pas vérifiés par le Neo** pour les modifications faites (test réel).
3. ~~Les 52 octets inconnus en tête de chaque parcours~~ → **résolu** : `ck` + nom (section 8).
4. Codes de type des obstacles.
5. Algorithme générant les 33 flux de noms du dossier `name/` (le flux `KH` de la fiche est, lui, global).
6. Ordre et couleur des 3 départs (hypothèse forte : jaune, rouge, orange = du plus long au plus court, 89 % de la base).
7. Format et éventuel chiffrement de `FW.bin`, et rôle de `ghost.setup`.

---

## 10. Fichiers

| Fichier | Contenu |
|---|---|
| `sda1.img` | **Image authentique** de la partition (octet `0x25` = `0xDD` ; mettre `0xDC` avant toute restauration) |
| `sda1-NEO-FINAL.img` | **Image exacte du Neo dans son état final** (base d'origine + St Roman Beaucaire). Base pour tout futur ajout |
| `neodb/neodb.py` | Outil : `selftest`, `near LAT LON`, `dump IDX ENTRÉE`. Affiche le nom de la fiche (celui que montre le Neo) |
| `neodb/keys.json` | Clé `KG`, 33 flux du dossier `name/`, flux `KH` du nom dans la fiche |
| `neodb/forge_course.py` | Forge un golf dans un emplacement, sur une **copie** d'image |
| `neodb/write_sectors.py` | Attend le Neo, contrôle, écrit quelques secteurs, revérifie après 30 s, éjecte |
| `neodb/finalize.py` | Comme ci-dessus, avec vérification **complète** de la partition contre l'image attendue |
| `neodb/stroman_course_final.json` | Saint-Roman : 9 trous (avant/centre/fond, 3 départs), pars |
| `neodb/stroman_carte_officielle.json`, `neodb/greens_beaucaire_6_trous.geojson` | Carte de score officielle ; greens fournis par l'utilisateur |
| `stroman_6_greens.jpg` | Carte satellite de travail (points de l'utilisateur) |
| `archives_incident/` | `sda1-fixed.img` et `sdb1-broken.img` (historique de l'incident, **ne pas utiliser**) |
| `neodb/stroman_osm_holes.json`, `osm_*.json` | Données OpenStreetMap |
| `stroman_site.html`, `stroman_plan.png` | Page et plan officiels |
| `sat/` | Tuiles satellite ; `stroman_candidats.json` = 17 zones lettrées |
| `archives_incident/` | Historique de l'incident (`restore*.py`, `verify5.*`, journaux, `neo-formatted-head.bin`). Remplacé par `tools/neo_restore.py` |
| `github-repo/` | Ce dépôt |
| `reddit_post_en.md` | Post Reddit |
| *(supprimés le 30/10)* | Images et scripts de test intermédiaires (`sda1-test/hometest*/final*.img`, `build_*.py`, sauvegardes JSON de secteurs). Reconstructibles avec `forge_course.py` |
| `restore.py`, `restore2.py`, `restore3.py` | Historiques — `restore3.py` vise **le disque entier, à ne pas utiliser** |

**Utilisation de l'outil :**

```
sudo mount -o ro,loop ~/bushnell-neo-backup/sda1.img ~/neoimg
python3 ~/bushnell-neo-backup/neodb/neodb.py near 43.808 4.644
```

---

## 11. Procédure sûre pour toucher au Neo

1. `gsettings set org.gnome.desktop.media-handling automount false` (et `automount-open false`) **avant** de brancher.
2. Ne jamais le monter en écriture. Lecture : sur l'image, montée en lecture seule.
3. Écrire uniquement sur `/dev/sdX1`, en vérifiant d'abord que la taille vaut 131 086 336 octets.
4. Zone système (64 premiers Ko de la partition) : un secteur à la fois, `O_DIRECT|O_SYNC`.
5. Vérifier en relisant avec `O_DIRECT` (ou après `blockdev --flushbufs`).
6. Éjecter avec `udisksctl power-off -b /dev/sdX`.
7. Si le Neo affiche 05 : **ne pas appuyer** pour continuer — l'éteindre.
8. Le contrôleur valide les écritures **avec retard** : une relecture `O_DIRECT` immédiate peut encore être fausse. Toujours revérifier après environ 30 s.

---

## 12. Procédure validée pour ajouter un golf

1. **Données** : 9 ou 18 trous. Pour chacun : green avant, centre et fond, 1 à 3 départs, par. Format JSON identique à `neodb/stroman_course_final.json`.
2. **Choisir un emplacement** (`neodb.py near LAT LON`) : un parcours inutile, **à l'intérieur** d'un fichier idx, dont les voisins encadrent la longitude du nouveau golf. `forge_course.py` vérifie les deux conditions.
3. **Forger sur une copie** :
   `sudo python3 neodb/forge_course.py sda1-NEO-FINAL.img nouveau.img IDX SLOT "Nom" golf.json LAT LON`
   Le script écrit l'index, le nom de `name/`, **le nom de la fiche** (celui qui est affiché), le centre, les trous et les pars. Il affiche ensuite les secteurs modifiés.
4. **Contrôler** la copie montée en lecture seule : `NEO_ROOT=… neodb.py near/dump/selftest` et `fsck.vfat -n`.
5. **Écrire** : `sudo python3 neodb/finalize.py sda1-NEO-FINAL.img nouveau.img`. Le script écrit seulement les secteurs de contenu, en ignorant les secteurs de dates de répertoire, puis vérifie toute la partition et éjecte le Neo. La nouvelle image devient alors la référence (`sda1-NEO-FINAL.img`).
   - ⚠ `finalize.py` réapplique tout le contenu de `FINAL.img` par-dessus `sda1.img`.
6. **Test à domicile possible** : copie temporaire translatée autour de soi (arguments `dLAT dLON`), dans un emplacement voisin en longitude ; restauration ensuite.

**Limites connues** :
- Obstacles et points personnalisés laissés vides (codes non décodés).
- Le Neo propose les golfs proches (environ 15 km) : le test réel se fait sur place ou avec une copie translatée.
