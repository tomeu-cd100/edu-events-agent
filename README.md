# edu-events-agent (filtre per regles, sense IA)

Agent autònom que cada dia busca **cursos, jornades, màsters i postgraus** sobre educació, IA i TIC educativa als feeds RSS configurats, filtra per paraules clau i envia un correu amb les troballes.

**Sense dependències d'API externes**: tot el filtratge és local amb regex i puntuació.

## Arquitectura

```
┌──────┐    ┌──────────┐    ┌──────────────┐    ┌────────┐
│ RSS  │───▶│  Dedup   │───▶│ Filtre regles│───▶│ Email  │
│rss.py│    │storage.py│    │filter_rules.py│    │mailer  │
└──────┘    └──────────┘    └──────────────┘    └────────┘
                  ▲
            events.db (SQLite)
```

## Set-up

### 1. Puja el projecte a GitHub
Crea un repo (privat recomanat) i puja aquests fitxers.

### 2. Secrets a GitHub
*Settings → Secrets and variables → Actions*:

| Secret | Valor |
|---|---|
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | correu remitent |
| `SMTP_PASSWORD` | contrasenya d'aplicació Gmail (16 chars) |
| `SMTP_TO` | destinatari |

> **Gmail**: cal 2FA activat + [contrasenya d'aplicació](https://myaccount.google.com/apppasswords).

### 3. Prova local
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # omple els valors
python main.py
```

### 4. Activa
Fes `git push` a `main`. A la pestanya *Actions* pots llançar-lo manualment (`Run workflow`) per validar.

## Com afinar el filtre

Tot es controla des de `config.yaml`, secció `filter`:

- **`min_score`**: quant ha de puntuar un esdeveniment per ser enviat.
  - Si reps **massa correus amb coses poc rellevants** → puja `min_score` a 3 o 4.
  - Si **gairebé no reps res** → baixa a 1, o afegeix més `positive_terms`.
- **`require_any`**: almenys una d'aquestes paraules ha d'aparèixer. Filtre de primer nivell per descartar tot el que no és educatiu. Si mai cap esdeveniment hi arriba, aquesta llista pot ser massa restrictiva.
- **`positive_terms`**: cada aparició suma punts (al títol, més). Afegeix-hi els teus temes d'interès específics.
- **`negative_terms`**: apareix → descartat immediatament. Útil per excluir etapes (infantil, primària) o temes que no t'interessen.

**Debug**: el correu mostra a cada troballa el **score** i els **motius** (termes que han fet match). Així pots veure per què una troballa ha passat i ajustar.

## Què pot fer i què no (vs la versió amb IA)

| Aspecte | Filtre per regles | Amb IA |
|---|---|---|
| **Filtratge**| Bo amb feeds ben triats | Millor, entén context |
| **Dates**| Regex (detecta dates habituals) | Pot inferir millor |
| **Durada**| No es pot determinar | Pot inferir del text |
| **Resum**| Descripció del feed truncada | Reformulat |
| **Cost** | 0 € | ~0,01–0,03 €/dia amb Haiku 4.5 |
| **Dependències**| Cap externa | Requereix API key |

## Evolució natural

Quan el filtre per regles et sàpiga a poc, els passos següents (sense perdre el que tens) són:

1. **Afegir més fonts**: Eventbrite API, Meetup API, pàgines d'agenda d'universitats.
2. **Scraper per pàgines sense RSS**: si hi ha un calendari d'una institució que et interessa molt.
3. **Afegir Ollama local**: com que ja en tens al servidor del centre, pots enviar els dubtosos (score 1–2) al teu model local perquè faci el desempat. Millor signal/noise sense cost.
4. **Afegir Claude API** per casos difícils, fent l'híbrid complet.

## Troubleshooting

- **No envia correu**: verifica que la contrasenya és d'*aplicació*, no la del compte. Mira els logs a *Actions*.
- **Reps els mateixos cada dia**: `events.db` no s'està commitejant. Revisa els permisos del workflow (`contents: write`).
- **Cap esdeveniment passa mai**: probablement `require_any` és massa estricta. Prova a buidar-la temporalment per veure el flux.
- **Alguns feeds fallen**: feedparser és tolerant però pot fallar amb SSL antic o URLs mortes. Els errors surten al log i no aturen la resta.
